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
import time

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


class Meter:
    """Counts bytes and messages through the tunnel so the app can show speeds. Numbers only."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.rx = self.tx = self.msgs = 0
        self._last = (time.monotonic(), 0, 0, 0)

    def add(self, direction: str, size: int) -> None:
        with self._lock:
            if direction == "rx":
                self.rx += size
            else:
                self.tx += size
            self.msgs += 1

    def rates(self) -> dict:
        """Kilobits per second and messages per second since the previous call."""
        with self._lock:
            now = time.monotonic()
            t0, rx0, tx0, m0 = self._last
            span = max(now - t0, 0.001)
            out = {"rx_kbps": round((self.rx - rx0) * 8 / 1000 / span, 1),
                   "tx_kbps": round((self.tx - tx0) * 8 / 1000 / span, 1),
                   "updates_per_s": round((self.msgs - m0) / span, 1)}
            self._last = (now, self.rx, self.tx, self.msgs)
            return out


METER = Meter()


def _pipe(a: socket.socket, b: socket.socket, direction: str = "") -> None:
    try:
        while data := a.recv(65536):
            if direction:
                METER.add(direction, len(data))
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

    def __init__(self, mode: str, key: str, listen_host: str, listen_port: int, target_host: str, target_port: int,
                 dial=None) -> None:
        """dial: optional callable returning an already-connected socket to use instead of
        target_host:target_port (relay mode: the lobby server pairs it with the host)."""
        if mode not in {"host", "guest"}:
            raise ValueError("mode must be host or guest")
        self.mode, self.target, self.dial = mode, (target_host, target_port), dial
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
                raw = self.dial() if self.dial else socket.create_connection(self.target, timeout=10)
                upstream = self.context.wrap_socket(raw, server_hostname=None)
            for s in (conn, upstream):
                s.settimeout(None)
                try:
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except (OSError, AttributeError):
                    pass
        except (OSError, ssl.SSLError, RuntimeError):
            for s in (conn, upstream):
                if s:
                    try:
                        s.close()
                    except OSError:
                        pass
            return
        outward = "tx" if self.mode == "guest" else "rx"
        inward = "rx" if self.mode == "guest" else "tx"
        threading.Thread(target=_pipe, args=(conn, upstream, outward), daemon=True).start()
        _pipe(upstream, conn, inward)
        for s in (conn, upstream):
            try:
                s.close()
            except OSError:
                pass


def _wants_tracker(fn) -> bool:
    import inspect
    try:
        return len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        return False


class RelayHost:
    """Host side of relay mode: keep a few connections parked at the lobby server; when the
    server pairs one with a guest, speak TLS-PSK over it and pipe to the local RetroArch."""

    def __init__(self, key: str, dial, local_host: str, local_port: int, slots: int = 4) -> None:
        self.context = _context(True, key)
        self.dial, self.local, self.slots = dial, (local_host, local_port), slots
        self.stopped = threading.Event()
        self.threads: list[threading.Thread] = []
        self.errors: list[str] = []
        self.served = 0
        self.open_sockets: set[socket.socket] = set()
        self._lock = threading.Lock()

    def start(self) -> "RelayHost":
        for _ in range(self.slots):
            t = threading.Thread(target=self._slot, daemon=True)
            t.start()
            self.threads.append(t)
        return self

    def stop(self) -> None:
        self.stopped.set()
        with self._lock:
            for s in list(self.open_sockets):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass
            self.open_sockets.clear()

    def _track(self, sock) -> None:
        with self._lock:
            self.open_sockets.add(sock)

    def _slot(self) -> None:
        while not self.stopped.is_set():
            try:
                raw = self.dial(self._track) if _wants_tracker(self.dial) else self.dial()
            except Exception as exc:         # relay refused / server gone: back off, try again
                if self.stopped.is_set():
                    return
                self.errors.append(str(exc)[:120])
                del self.errors[:-10]
                if self.stopped.wait(2.0):
                    return
                continue
            try:
                conn = self.context.wrap_socket(raw, server_side=True)
                upstream = socket.create_connection(self.local, timeout=10)
                for s in (conn, upstream):
                    s.settimeout(None)
                    try:
                        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    except (OSError, AttributeError):
                        pass
            except (OSError, ssl.SSLError):
                try:
                    raw.close()
                except OSError:
                    pass
                continue
            self.served += 1
            threading.Thread(target=_pipe, args=(conn, upstream, "rx"), daemon=True).start()
            _pipe(upstream, conn, "tx")
            for s in (conn, upstream):
                try:
                    s.close()
                except OSError:
                    pass
