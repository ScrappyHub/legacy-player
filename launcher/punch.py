"""Direct player-to-player connections (TCP hole punching), with the lobby server only as the introducer.

Both players connect to the server from a local port; the server tells each the address it saw for the
other; then both connect to each other from that same port at the same moment. Most home routers let that
through, giving a plain TCP socket between the two computers with no server in the middle (lower delay, and
the server carries no game traffic). When the routers refuse, or one side is not waiting, the caller falls
back to the relay. Everything that crosses the socket is still wrapped in the match's TLS-PSK tunnel.
"""
from __future__ import annotations

import ipaddress
import socket
import threading
import time


def _shared(sock: socket.socket) -> None:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)


def _same(a: str, b: str) -> bool:
    try:
        x, y = ipaddress.ip_address(a), ipaddress.ip_address(b)
    except ValueError:
        return False
    x = getattr(x, "ipv4_mapped", None) or x
    y = getattr(y, "ipv4_mapped", None) or y
    return x == y


def hole_connect(local_port: int, peer: list, total: float = 9.0, interval: float = 0.35) -> socket.socket:
    """Connect to peer from local_port while also accepting the peer's own attempt. Returns the first
    socket that works; raises OSError when the time is up."""
    host, port = peer[0], int(peer[1])
    family = socket.AF_INET6 if ipaddress.ip_address(host).version == 6 else socket.AF_INET
    bind = ("::" if family == socket.AF_INET6 else "", local_port)
    won: list[socket.socket] = []
    lock = threading.Lock()
    done = threading.Event()
    listener = socket.socket(family, socket.SOCK_STREAM)
    try:
        _shared(listener)
        listener.bind(bind)
        listener.listen(2)
        listener.settimeout(0.3)
    except OSError:
        listener.close()
        listener = None

    def keep(sock: socket.socket) -> None:
        with lock:
            if won:
                sock.close()
            else:
                won.append(sock)
                done.set()

    def accept_loop() -> None:
        while not done.is_set():
            try:
                conn, addr = listener.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            if _same(addr[0], host):   # only the friend we were introduced to
                keep(conn)
            else:
                conn.close()

    if listener is not None:
        threading.Thread(target=accept_loop, daemon=True).start()
    deadline = time.monotonic() + total
    try:
        while not done.is_set() and time.monotonic() < deadline:
            s = socket.socket(family, socket.SOCK_STREAM)
            try:
                _shared(s)
                s.bind(bind)
                s.settimeout(min(interval * 3, max(0.2, deadline - time.monotonic())))
                s.connect((host, port))
                keep(s)
                s = None
            except OSError:
                pass
            finally:
                if s is not None:
                    s.close()
            if not done.is_set():
                done.wait(interval)
    finally:
        done.set()
        if listener is not None:
            listener.close()
    if not won:
        raise OSError("the routers did not let a direct connection through")
    sock = won[0]
    sock.settimeout(None)
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    return sock


def dial(client, role: str, auth: dict, on_socket=None, total: float = 9.0) -> socket.socket:
    """Get introduced by the lobby server, then punch through. Returns a connected socket."""
    port, peer = client.open_punch(role, auth, on_socket=on_socket)
    return hole_connect(port, peer, total=total)


class GuestDialer:
    """Dial for the guest's tunnel: try a direct connection first and use the relay if it fails.
    After one failure the relay is used straight away, so a blocked route costs one short wait."""

    def __init__(self, direct, relay) -> None:
        self.direct, self.relay = direct, relay
        self.use_direct = direct is not None
        self.path = ""
        self.errors: list[str] = []

    def __call__(self) -> socket.socket:
        if self.use_direct:
            try:
                sock = self.direct()
                self.path = "direct"
                return sock
            except Exception as exc:
                self.use_direct = False
                self.errors.append(f"direct: {str(exc)[:100]}")
        sock = self.relay()
        self.path = "relay"
        return sock
