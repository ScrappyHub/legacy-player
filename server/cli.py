"""Start, stop, restart and inspect a Legacy Player server (Windows, Linux, Raspberry Pi).

    python -m server.cli start   [--detach] [server options]
    python -m server.cli stop
    python -m server.cli restart [server options]
    python -m server.cli status
    python -m server.cli code --address play.example.com     (print the server code friends type)

`start --share` listens on every address with an encrypted connection: it makes its own certificate on first run and
keeps it in the state folder, so the server code stays the same across restarts.

Stop is graceful: connected clients are notified, lobby state is saved, and the
next start resumes it. Control uses a local admin token in the state folder, so
it works the same on every OS and is refused from other machines.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

from server.state_store import StateStore


def _admin_hosts(info_host: str) -> list[str]:
    """Where to reach the server's admin channel: always loopback first (the server only accepts admin calls from this
    machine, and listens on loopback too when bound to one address). Its own address is the last resort, for a server
    that could not also listen on loopback; it accepts a call from itself there."""
    host = str(info_host or "")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    # one loopback try only: on Windows a refused loopback connection takes about two seconds
    hosts = ["::1"] if ip is not None and ip.version == 6 else ["127.0.0.1"]
    if ip is not None and not ip.is_loopback and not ip.is_unspecified:
        hosts.append(host)
    return hosts


def _connect_admin(info: dict, timeout: float) -> socket.socket:
    last: Exception | None = None
    for host in _admin_hosts(info.get("host", "")):
        try:
            return socket.create_connection((host, info["port"]), timeout=timeout)
        except OSError as exc:
            last = exc
    raise last or ConnectionError("server not reachable")


def _admin_call(state_dir: Path, operation: str, timeout: float = 5.0) -> dict:
    store = StateStore(state_dir)
    info = store.read_info()
    if info is None:
        raise ConnectionError("no server info found; is it running?")
    request = {"operation": operation, "admin_token": store.admin_token()}
    sock = _connect_admin(info, timeout)
    if info.get("tls"):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # Admin call to this machine only: the token already proves we share this machine's state folder.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        try:
            sock = context.wrap_socket(sock, server_hostname="localhost")
        except (OSError, ssl.SSLError):
            sock.close()
            raise
    with sock:
        sock.sendall(json.dumps(request).encode() + b"\n")
        data = sock.makefile("rb").readline()
    response = json.loads(data)
    if not response.get("ok"):
        raise ConnectionError(response.get("error", "admin call failed"))
    return response["result"]


def _is_running(state_dir: Path) -> bool:
    try:
        _admin_call(state_dir, "admin_status", timeout=2.0)
        return True
    except (OSError, ConnectionError, ValueError):
        return False


def _child_env() -> dict:
    """The environment for the server process. A PyInstaller one-file app unpacks itself into a temporary _MEI folder
    and tells its children about it through the environment; a long-running child that inherited that would reuse
    (and keep locked) the parent's temporary folder, which the parent deletes when it exits or updates itself."""
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        for key in [k for k in env if k.startswith("_PYI_") or k == "_MEIPASS2"]:
            del env[key]
    return env


def _child_cwd(args: argparse.Namespace) -> str | None:
    """Packaged app: start the server in its state folder, never inside the parent's temporary _MEI folder."""
    if not getattr(sys, "frozen", False):
        return None
    folder = Path(args.state_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def _server_command(args: argparse.Namespace) -> list[str]:
    # In the packaged app sys.executable is the app itself, which runs the server for --server-run.
    runner = [sys.executable, "--server-run"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "server.api.json_server"]
    # absolute paths: the packaged server starts in another folder (see _child_cwd)
    command = runner + [
        "--host", args.host, "--port", str(args.port),
        "--state-dir", str(Path(args.state_dir).resolve()), "--replay-dir", str(Path(args.replay_dir).resolve()),
    ]
    for name in ("max_players", "max_rooms", "max_waiting"):
        value = getattr(args, name, None)
        if value is not None:
            command += ["--" + name.replace("_", "-"), str(value)]
    if args.tls_cert:
        command += ["--tls-cert", str(Path(args.tls_cert).resolve()), "--tls-key", str(Path(args.tls_key).resolve())]
    if args.allow_insecure_remote:
        command.append("--allow-insecure-remote")
    return command


def _apply_share(args: argparse.Namespace) -> None:
    if not getattr(args, "share", False):
        return
    from server.selfsigned import ensure_certificate
    if args.host == "127.0.0.1":
        args.host = "0.0.0.0"
    if not args.tls_cert:
        args.tls_cert, args.tls_key, _ = ensure_certificate(args.state_dir / "tls")


def code(args: argparse.Namespace) -> int:
    """Print the server code for this server (needs --address: the public name or number friends reach it at)."""
    from launcher import servercode
    from server.selfsigned import ensure_certificate, fingerprint_of
    if not args.address:
        print("Give the public address friends use, e.g.  --address play.example.com  (a name or an IP number).", file=sys.stderr)
        return 2
    cert, _, _ = ensure_certificate(args.state_dir / "tls")
    try:
        text = servercode.encode(args.address, args.port, fingerprint_of(cert), StateStore(args.state_dir).access_key())
    except servercode.CodeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(text)
    return 0


def start(args: argparse.Namespace) -> int:
    _apply_share(args)
    if _is_running(args.state_dir):
        print("Server is already running.")
        return 0
    command = _server_command(args)
    if not args.detach:
        return subprocess.call(command, env=_child_env(), cwd=_child_cwd(args))
    args.state_dir.mkdir(parents=True, exist_ok=True)
    kwargs = {"stdin": subprocess.DEVNULL, "env": _child_env(), "cwd": _child_cwd(args)}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    with open(args.state_dir / "server.log", "ab") as log:     # the child keeps its own copy of the handle
        subprocess.Popen(command, stdout=log, stderr=log, **kwargs)
    for _ in range(50):
        if _is_running(args.state_dir):
            print("Server started.")
            return 0
        time.sleep(0.2)
    print("Server did not come up; check the log.", file=sys.stderr)
    return 1


def stop(args: argparse.Namespace) -> int:
    if not _is_running(args.state_dir):
        print("Server is not running.")
        return 0
    _admin_call(args.state_dir, "admin_shutdown")
    for _ in range(100):
        if not _is_running(args.state_dir):
            print("Server stopped. Lobby state saved; `start` will resume it.")
            return 0
        time.sleep(0.2)
    print("Server did not stop in time.", file=sys.stderr)
    return 1


def restart(args: argparse.Namespace) -> int:
    code = stop(args)
    if code:
        return code
    args.detach = True
    return start(args)


def status(args: argparse.Namespace) -> int:
    try:
        result = _admin_call(args.state_dir, "admin_status")
    except (OSError, ConnectionError, ValueError):
        print("Server is not running.")
        return 1
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["start", "stop", "restart", "status", "code"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", type=Path, default=Path("artifacts/state"))
    parser.add_argument("--replay-dir", type=Path, default=Path("artifacts/replays"))
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    parser.add_argument("--share", action="store_true", help="listen for friends over an encrypted connection (start)")
    parser.add_argument("--address", help="the public name or IP number friends reach this server at (code)")
    parser.add_argument("--allow-insecure-remote", action="store_true")
    parser.add_argument("--detach", action="store_true", help="run in the background (start)")
    parser.add_argument("--max-players", type=int, help="players per room, 2-8 (default 4)")
    parser.add_argument("--max-rooms", type=int, help="rooms at once (default 128)")
    parser.add_argument("--max-waiting", type=int, help="waiting line per room, 0 turns lines off (default 16)")
    args = parser.parse_args(argv)
    return {"start": start, "stop": stop, "restart": restart, "status": status, "code": code}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
