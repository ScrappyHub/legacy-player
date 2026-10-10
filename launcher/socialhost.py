"""Running the friends service from Legacy Player, so nobody has to type a command.

One button starts `server.social` in the background with this app's data folder, the shared server's self-signed
certificate (so friends get HTTPS and check its fingerprint) and a moderator key it makes for itself. The app reads that
key straight from the file, so moderation simply works on this computer. The service keeps running when the window
closes (like the multiplayer server), and starts again with the app if it was on.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from .friends import FriendsError, pinned_request

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DETACHED = 0x00000008 | 0x00000200                    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


class HostError(RuntimeError):
    pass


class SocialHost:
    def __init__(self, data_dir: Path) -> None:
        self.folder = Path(data_dir) / "social"
        self.tls = Path(data_dir) / "server" / "tls"         # the same certificate as the shared multiplayer server

    # --- what it has ---------------------------------------------------------------------------------------------
    def key(self) -> str:
        try:
            return (self.folder / "moderator.key").read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def pin(self) -> str:
        from server.selfsigned import fingerprint_of
        cert = self.tls / "cert.pem"
        return fingerprint_of(cert) if cert.exists() else ""

    def local_link(self, port: int) -> str:
        """What this app itself uses to reach the service it runs."""
        from .friends import make_link
        return make_link("127.0.0.1", port, self.pin())

    def _ask(self, port: int, path: str, body: dict | None = None, timeout: float = 2.0) -> dict:
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "LegacyPlayer"}
        if path.startswith("/admin"):
            headers["X-Admin-Token"] = self.key()
        status, raw = pinned_request(f"https://127.0.0.1:{int(port)}{path}", self.pin(), data, headers, timeout,
                                     "GET" if body is None else "POST")
        out = json.loads(raw or b"{}")
        if status >= 400:
            raise HostError(out.get("error") or f"answered {status}")
        return out

    def running(self, port: int) -> bool:
        """Is *our* service answering on that port? (The pinned certificate makes sure it is not something else.)"""
        if not self.pin():
            return False
        try:
            return self._ask(port, "/health").get("service") == "legacy-player-friends"
        except (OSError, ValueError, HostError, FriendsError):
            return False

    # --- start and stop --------------------------------------------------------------------------------------------
    def command(self, port: int) -> list[str]:
        runner = [sys.executable, "--social-run"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "server.social"]
        return runner + ["--dir", str(self.folder), "--host", "0.0.0.0", "--port", str(int(port)),
                         "--tls-cert", str(self.tls / "cert.pem"), "--tls-key", str(self.tls / "key.pem")]

    def start(self, port: int, wait: float = 15.0) -> None:
        from server.selfsigned import ensure_certificate
        if self.running(port):
            return
        ensure_certificate(self.tls)
        self.folder.mkdir(parents=True, exist_ok=True)
        from server.social.__main__ import moderator_key
        moderator_key(self.folder)                         # made now, so the app can read it the moment the service answers
        kwargs: dict = {"stdin": subprocess.DEVNULL, "cwd": str(Path(__file__).resolve().parent.parent)}
        if sys.platform == "win32":
            kwargs["creationflags"] = _DETACHED | _NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        with open(self.folder / "service.log", "ab") as log:        # the service keeps its own copy of the handle
            process = subprocess.Popen(self.command(port), stdout=log, stderr=log, **kwargs)
        end = time.time() + wait
        while time.time() < end:
            if self.running(port):
                return
            if process.poll() is not None:
                break
            time.sleep(0.25)
        tail = ""
        try:
            tail = (self.folder / "service.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1]
        except (OSError, IndexError):
            pass
        if "in use" in tail.lower() or "address already" in tail.lower() or "10048" in tail:
            raise HostError(f"Port {port} is already used by another program. Pick another port under Settings > Friends.")
        raise HostError("The friends service did not start" + (f": {tail}" if tail else "."))

    def stop(self, port: int) -> bool:
        if not self.running(port):
            return False
        try:
            self._ask(port, "/admin/stop", {})
        except (OSError, ValueError, HostError, FriendsError):
            return False
        for _ in range(40):
            if not self.running(port):
                return True
            time.sleep(0.15)
        return False
