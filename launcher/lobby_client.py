"""Tiny synchronous client for the Legacy Player coordination server."""
from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl


class LobbyClientError(RuntimeError):
    pass


class LobbyClient:
    def __init__(self, host: str, port: int, *, tls: bool = False, verify: bool = True, timeout: float = 5.0,
                 fingerprint: str = "") -> None:
        self.host, self.port, self.tls, self.verify, self.timeout = host, port, tls, verify, timeout
        # A pinned SHA-256 of the server certificate (what the in-app server shows its owner).
        self.fingerprint = re.sub(r"[^0-9a-f]", "", fingerprint.lower())

    def call(self, request: dict) -> dict:
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            if self.tls:
                context = ssl.create_default_context()
                if self.fingerprint or not self.verify:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE   # pinning below replaces CA verification
                sock = context.wrap_socket(sock, server_hostname=self.host)
                if self.fingerprint:
                    seen = hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
                    if not seen.startswith(self.fingerprint) or len(self.fingerprint) < 16:
                        sock.close()
                        raise LobbyClientError(
                            "The server's certificate does not match the fingerprint you entered. "
                            "Ask the host for the fingerprint shown in their app, or someone may be in the middle.")
            with sock:
                sock.sendall(json.dumps(request).encode() + b"\n")
                line = sock.makefile("rb").readline()
        except (OSError, ssl.SSLError) as exc:
            raise LobbyClientError(
                f"Could not reach the multiplayer server at {self.host}:{self.port} ({exc}). "
                "Is it running? Start it with: python -m server.cli start --detach"
            ) from exc
        response = json.loads(line)
        if not response.get("ok"):
            raise LobbyClientError(response.get("error", "server error"))
        return response["result"]
