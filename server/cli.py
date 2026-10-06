"""Start, stop, restart and inspect a Legacy Player server (Windows, Linux, Raspberry Pi).

    python -m server.cli start   [--detach] [server options]
    python -m server.cli stop
    python -m server.cli restart [server options]
    python -m server.cli status

Stop is graceful: connected clients are notified, lobby state is saved, and the
next start resumes it. Control uses a local admin token in the state folder, so
it works the same on every OS and is refused from other machines.
"""
from __future__ import annotations

import argparse
import json
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

from server.state_store import StateStore


def _admin_call(state_dir: Path, operation: str, timeout: float = 5.0) -> dict:
    store = StateStore(state_dir)
    info = store.read_info()
    if info is None:
        raise ConnectionError("no server info found; is it running?")
    host = "127.0.0.1" if info["host"] in {"0.0.0.0", "::", ""} else info["host"]
    request = {"operation": operation, "admin_token": store.admin_token()}
    sock = socket.create_connection((host, info["port"]), timeout=timeout)
    if info.get("tls"):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # Loopback admin call only: the token already proves we share this machine's state folder.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        sock = context.wrap_socket(sock, server_hostname=host)
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


def _server_command(args: argparse.Namespace) -> list[str]:
    # In the packaged app sys.executable is the app itself, which runs the server for --server-run.
    runner = [sys.executable, "--server-run"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "server.api.json_server"]
    command = runner + [
        "--host", args.host, "--port", str(args.port),
        "--state-dir", str(args.state_dir), "--replay-dir", str(args.replay_dir),
    ]
    for name in ("max_players", "max_rooms", "max_waiting"):
        value = getattr(args, name, None)
        if value is not None:
            command += ["--" + name.replace("_", "-"), str(value)]
    if args.tls_cert:
        command += ["--tls-cert", str(args.tls_cert), "--tls-key", str(args.tls_key)]
    if args.allow_insecure_remote:
        command.append("--allow-insecure-remote")
    return command


def start(args: argparse.Namespace) -> int:
    if _is_running(args.state_dir):
        print("Server is already running.")
        return 0
    command = _server_command(args)
    if not args.detach:
        return subprocess.call(command)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    log = open(args.state_dir / "server.log", "ab")
    kwargs = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)
    for _ in range(50):
        if _is_running(args.state_dir):
            print(f"Server started (log: {args.state_dir / 'server.log'}).")
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
    parser.add_argument("command", choices=["start", "stop", "restart", "status"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", type=Path, default=Path("artifacts/state"))
    parser.add_argument("--replay-dir", type=Path, default=Path("artifacts/replays"))
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    parser.add_argument("--allow-insecure-remote", action="store_true")
    parser.add_argument("--detach", action="store_true", help="run in the background (start)")
    parser.add_argument("--max-players", type=int, help="players per room, 2-8 (default 4)")
    parser.add_argument("--max-rooms", type=int, help="rooms at once (default 128)")
    parser.add_argument("--max-waiting", type=int, help="waiting line per room, 0 turns lines off (default 16)")
    args = parser.parse_args(argv)
    return {"start": start, "stop": stop, "restart": restart, "status": status}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
