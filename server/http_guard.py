"""Shared protection for the small stdlib HTTP services (the friends service and the report receiver).

- A cap on how many requests are handled at once (one thread each): over the cap a connection is closed at once instead
  of starting yet another thread.
- A total deadline per request, not only per read: a sender trickling one byte every few seconds is cut off.
- No client address in any log: socketserver's default error report prints the peer's address and a traceback to stderr
  (which the app keeps in a log file). Here only the kind of error is written.
- A per-address counter for expensive calls, kept only in memory, keyed like the lobby's throttle (an IPv6 household is
  one /64), never stored or logged.
"""
from __future__ import annotations

import sys
import threading
import time
from http.server import ThreadingHTTPServer

from server.lobby.throttle import key_for

MAX_CONCURRENT = 64
REQUEST_DEADLINE = 30.0


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    max_concurrent = MAX_CONCURRENT
    request_deadline = REQUEST_DEADLINE
    label = "service"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._slots = threading.BoundedSemaphore(self.max_concurrent)
        self._live: dict = {}                      # connection -> deadline (monotonic)
        self._live_lock = threading.Lock()
        self._watchdog: threading.Thread | None = None
        self._closing = False

    # --- how many at once -------------------------------------------------------------------------------------
    def process_request(self, request, client_address) -> None:
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)         # full: close at once, no thread, nothing logged
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        self._track(request)
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._untrack(request)
            self._slots.release()

    # --- a total deadline per request ------------------------------------------------------------------------
    def _track(self, request) -> None:
        with self._live_lock:
            self._live[request] = time.monotonic() + self.request_deadline
            if self._watchdog is None:
                self._watchdog = threading.Thread(target=self._watch, name="http-deadline", daemon=True)
                self._watchdog.start()

    def _untrack(self, request) -> None:
        with self._live_lock:
            self._live.pop(request, None)

    def _watch(self) -> None:
        import socket
        while not self._closing:
            time.sleep(min(1.0, max(0.05, self.request_deadline / 4)))
            now = time.monotonic()
            with self._live_lock:
                late = [r for r, until in self._live.items() if until <= now]
                for r in late:
                    self._live.pop(r, None)
            for r in late:
                try:
                    # the plain socket's shutdown (an SSLSocket's own would drop its TLS state under the reading thread):
                    # unblocks the reading thread, which then finishes and closes the connection
                    socket.socket.shutdown(r, socket.SHUT_RDWR)
                except (OSError, TypeError):
                    pass

    def server_close(self) -> None:
        self._closing = True
        super().server_close()

    # --- nothing identifying in the log ----------------------------------------------------------------------
    def handle_error(self, request, client_address) -> None:
        kind = type(sys.exc_info()[1]).__name__ if sys.exc_info()[1] is not None else "unknown"
        try:
            print(f"{self.label}: a request failed ({kind})", file=sys.stderr, flush=True)
        except Exception:
            pass


class AddressWindow:
    """At most `limit` events per `window` seconds per address (an IPv6 /64 counts as one address). This computer
    (loopback) is not limited. Kept only in memory; the table is bounded, and when it is full of live entries new
    addresses are refused rather than letting it grow."""

    def __init__(self, limit: int, window: float, max_tracked: int = 20000, clock=time.monotonic) -> None:
        self.limit, self.window, self.max_tracked, self.clock = limit, window, max_tracked, clock
        self._seen: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, peer: str | None) -> bool:
        key = key_for(peer)
        if key is None:
            return True
        now = self.clock()
        with self._lock:
            if key not in self._seen and len(self._seen) >= self.max_tracked:
                for k in [k for k, ts in self._seen.items() if not ts or now - ts[-1] >= self.window]:
                    del self._seen[k]
                if len(self._seen) >= self.max_tracked:
                    return False
            stamps = [t for t in self._seen.get(key, []) if now - t < self.window]
            if len(stamps) >= self.limit:
                self._seen[key] = stamps
                return False
            stamps.append(now)
            self._seen[key] = stamps
            return True
