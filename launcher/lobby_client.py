"""Tiny synchronous client for the Legacy Player coordination server."""
from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl

MAX_ANSWER_BYTES = 8 * 1024 * 1024


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

    def _where(self) -> str:
        """How a server is named in messages shown to the player. A friend's address is never printed:
        it ends up in screenshots, toasts and bug reports."""
        return "this computer's server" if self.host in {"127.0.0.1", "localhost", "::1"} else "the server"

    def _connect(self, source_port: int | None = None) -> socket.socket:
        if source_port is None:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        else:
            sock = self._bound_connection(source_port)
        return self._secure(sock)

    def _bound_connection(self, source_port: int) -> socket.socket:
        """Connect from a chosen local port (0 = any) that other sockets may share. The direct
        connection to a friend is made from this same port, so it is the port the router maps."""
        last: Exception | None = None
        for family, kind, proto, _, addr in socket.getaddrinfo(self.host, self.port, 0, socket.SOCK_STREAM):
            sock = socket.socket(family, kind, proto)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if hasattr(socket, "SO_REUSEPORT"):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                sock.bind(("::" if family == socket.AF_INET6 else "", source_port))
                sock.settimeout(self.timeout)
                sock.connect(addr)
                return sock
            except OSError as exc:
                last = exc
                sock.close()
        raise last or OSError("no address to connect to")

    def _secure(self, sock: socket.socket) -> socket.socket:
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

    def open_punch(self, role: str, auth: dict, *, wait: float = 125.0, on_socket=None) -> tuple[int, list]:
        """Ask the server to introduce this player to the other side. Returns (local port the
        server saw us on, [peer address, peer port]). The host waits here until a guest asks."""
        try:
            sock = self._connect(source_port=0)
            if on_socket is not None:
                on_socket(sock)
            port = sock.getsockname()[1]
            sock.sendall(json.dumps({"operation": "punch", "role": role, "consent": True, **auth}).encode() + b"\n")
            first = json.loads(_read_line(sock) or b"{}")
            if not first.get("ok"):
                sock.close()
                raise LobbyClientError(first.get("error", "direct connection refused"))
            reply = first
            if first["result"].get("parked"):
                sock.settimeout(wait)
                reply = json.loads(_read_line(sock) or b"{}")
                if not reply.get("ok"):
                    sock.close()
                    raise LobbyClientError(reply.get("error", "nobody tried to connect directly"))
            sock.close()
            peer = reply["result"]["peer"]
            return port, [str(peer[0]), int(peer[1])]
        except (OSError, ssl.SSLError, ValueError, KeyError) as exc:
            raise LobbyClientError(f"Could not set up a direct connection through {self._where()} ({exc}).") from exc

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
            raise LobbyClientError(f"Could not open a relay through {self._where()} ({exc}).") from exc

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
                line = sock.makefile("rb").readline(MAX_ANSWER_BYTES)     # bounded: a wrong server cannot fill memory
        except (OSError, ssl.SSLError) as exc:
            raise LobbyClientError(
                f"Could not reach the multiplayer server at {self._where()} ({exc}). "
                "The server may not be running, or a firewall or router is blocking it (ask the host to check Windows Firewall and their router), or the server code is out of date."
            ) from exc
        try:
            response = json.loads(line)
        except ValueError as exc:
            raise LobbyClientError(f"Something answered at {self._where()} but it is not a Legacy Player server.") from exc
        if not response.get("ok"):
            raise LobbyClientError(response.get("error", "server error"))
        return response["result"]
