"""Tiny synchronous client for the Legacy Player coordination server."""
from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl


class LobbyClientError(RuntimeError):
    pass


def _read_line(sock: socket.socket, limit: int = 4096) -> bytes:
    out = bytearray()
    while len(out) < limit:
        ch = sock.recv(1)
        if not ch:
            break
        out += ch
        if ch == b"\n":
            break
    return bytes(out)


class LobbyClient:
    def __init__(self, host: str, port: int, *, tls: bool = False, verify: bool = True, timeout: float = 5.0,
                 fingerprint: str = "", access_key: str = "") -> None:
        self.access_key = re.sub(r"[^0-9a-f]", "", access_key.lower())
        self.host, self.port, self.tls, self.verify, self.timeout = host, port, tls, verify, timeout
        # A pinned SHA-256 of the server certificate (what the in-app server shows its owner).
        self.fingerprint = re.sub(r"[^0-9a-f]", "", fingerprint.lower())

    def _connect(self) -> socket.socket:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.tls:
            context = ssl.create_default_context()
            if self.fingerprint or not self.verify:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE   # pinning below replaces CA verification
            sock = context.wrap_socket(sock, server_hostname=self.host)
            if self.fingerprint:
                seen = hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
                if not seen.startswith(self.fingerprint) or len(self.fingerprint) < 10:
                    sock.close()
                    raise LobbyClientError(
                        "The server's certificate does not match the fingerprint you entered. "
                        "Ask the host for the fingerprint shown in their app, or someone may be in the middle.")
        return sock

    def open_relay(self, role: str, auth: dict, *, wait_paired: bool, on_socket=None) -> socket.socket:
        """Open a relay connection through the lobby server. Returns the raw socket once the
        server has parked it (host) or paired it (guest); the caller then speaks TLS-PSK over it."""
        try:
            sock = self._connect()
            if on_socket is not None:
                on_socket(sock)
            sock.sendall(json.dumps({"operation": "relay", "role": role, **auth}).encode() + b"\n")
            # Read exactly one line at a time, unbuffered: the bytes right after the last
            # line are the other player's TLS handshake and must stay in the socket.
            first = json.loads(_read_line(sock) or b"{}")
            if not first.get("ok"):
                sock.close()
                raise LobbyClientError(first.get("error", "relay refused"))
            if wait_paired and not first["result"].get("paired"):
                sock.settimeout(None)
                second = json.loads(_read_line(sock) or b"{}")
                if not second.get("ok") or not second["result"].get("paired"):
                    sock.close()
                    raise LobbyClientError("relay connection ended before a player arrived")
            sock.settimeout(None)
            return sock
        except (OSError, ssl.SSLError, ValueError) as exc:
            raise LobbyClientError(f"Could not open a relay through {self.host}:{self.port} ({exc}).") from exc

    def call(self, request: dict) -> dict:
        if self.access_key and "access_key" not in request:
            request = {**request, "access_key": self.access_key}
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
                    if not seen.startswith(self.fingerprint) or len(self.fingerprint) < 10:
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
                "The server may not be running, or a firewall or router is blocking it (ask the host to check Windows Firewall and their router), or the server code is out of date."
            ) from exc
        try:
            response = json.loads(line)
        except ValueError as exc:
            raise LobbyClientError(f"Something answered at {self.host}:{self.port} but it is not a Legacy Player server.") from exc
        if not response.get("ok"):
            raise LobbyClientError(response.get("error", "server error"))
        return response["result"]
