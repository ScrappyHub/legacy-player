"""Encrypted tunnel for RetroArch netplay (TLS 1.2 with a pre-shared key).

RetroArch's netplay socket is plain TCP. This wraps it:

    guest RetroArch -> 127.0.0.1:L  [guest tunnel]  ==TLS-PSK==>  [host tunnel] :P -> host RetroArch 127.0.0.1:R

The host tunnel takes the public port the guests dial; RetroArch itself is started on a
different private port. The key is random per match and travels to guests through the
lobby (set it over a TLS lobby for internet play). Needs Python 3.13+ (ssl PSK support);
older Pythons report the tunnel as unavailable and the launcher says so plainly.

Limit: RetroArch still listens on its own private port without a firewall rule of ours, so
keep that port closed at your router/firewall (Windows blocks it unless you allow RetroArch).
"""
from __future__ import annotations

import secrets
import socket
import ssl
import threading

IDENTITY = "legacy-player"
CIPHERS = "PSK-AES256-GCM-SHA384:PSK-CHACHA20-POLY1305:PSK-AES128-GCM-SHA256"


class TunnelUnavailable(RuntimeError):
    pass


def available() -> bool:
    return hasattr(ssl.SSLContext, "set_psk_server_callback") and hasattr(ssl.SSLContext, "set_psk_client_callback")


def new_key() -> str:
    return secrets.token_hex(32)


def _context(server: bool, key: str) -> ssl.SSLContext:
    if not available():
        raise TunnelUnavailable("Encrypted matches need Python 3.13 or newer (the Legacy Player app includes it).")
    secret = bytes.fromhex(key)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
    if not server:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    context.set_ciphers(CIPHERS)
    if server:
        context.set_psk_server_callback(lambda identity: secret if identity == IDENTITY else b"\x00" * 32)
    else:
        context.set_psk_client_callback(lambda hint: (IDENTITY, secret))
    return context


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class Tunnel:
    """mode 'host': TLS in -> plain out to RetroArch. mode 'guest': plain in from RetroArch -> TLS out."""

    def __init__(self, mode: str, key: str, listen_host: str, listen_port: int, target_host: str, target_port: int) -> None:
        if mode not in {"host", "guest"}:
            raise ValueError("mode must be host or guest")
        self.mode, self.target = mode, (target_host, target_port)
        self.context = _context(mode == "host", key)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind((listen_host, listen_port))
        self.listener.listen(8)
        self.port = self.listener.getsockname()[1]
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._accept, daemon=True)

    def start(self) -> "Tunnel":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.stopped.set()
        try:
            self.listener.close()
        except OSError:
            pass

    def _accept(self) -> None:
        while not self.stopped.is_set():
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        upstream = None
        try:
            conn.settimeout(10)
            if self.mode == "host":
                conn = self.context.wrap_socket(conn, server_side=True)  # bad key -> handshake fails -> dropped
                upstream = socket.create_connection(self.target, timeout=10)
            else:
                raw = socket.create_connection(self.target, timeout=10)
                upstream = self.context.wrap_socket(raw, server_hostname=None)
            for s in (conn, upstream):
                s.settimeout(None)
                try:
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except (OSError, AttributeError):
                    pass
        except (OSError, ssl.SSLError):
            for s in (conn, upstream):
                if s:
                    try:
                        s.close()
                    except OSError:
                        pass
            return
        threading.Thread(target=_pipe, args=(conn, upstream), daemon=True).start()
        _pipe(upstream, conn)
        for s in (conn, upstream):
            try:
                s.close()
            except OSError:
                pass
