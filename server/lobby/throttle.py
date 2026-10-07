"""Per-address failure throttle: after a few wrong guesses an address is locked out for a while.

Used for invite codes and the server access key so one address cannot guess them, without letting that
address lock everyone else out. The table is bounded so a flood of fake addresses cannot grow it forever.
"""
from __future__ import annotations

import ipaddress
import time

MAX_TRACKED = 4096


def key_for(peer: str | None) -> str | None:
    """The address to count against, or None for this computer / unknown (never throttled per address)."""
    if not peer:
        return None
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return None
    if ip.is_loopback:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address)     # one household holds a whole /64
    return str(ip)


class FailureThrottle:
    def __init__(self, *, max_failures: int = 5, window: float = 60.0, lockout: float = 300.0, clock=time.monotonic) -> None:
        self.max_failures, self.window, self.lockout, self.clock = max_failures, window, lockout, clock
        self._fails: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}

    def blocked(self, peer: str | None) -> float:
        """Seconds left on a lockout (0 when the address may try)."""
        key = key_for(peer)
        if key is None:
            return 0.0
        until = self._locked.get(key, 0.0)
        now = self.clock()
        if until <= now:
            self._locked.pop(key, None)
            return 0.0
        return until - now

    def fail(self, peer: str | None) -> None:
        key = key_for(peer)
        if key is None:
            return
        now = self.clock()
        if len(self._fails) + len(self._locked) > MAX_TRACKED:
            self._sweep(now)
        recent = [t for t in self._fails.get(key, []) if now - t <= self.window]
        recent.append(now)
        if len(recent) >= self.max_failures:
            self._locked[key] = now + self.lockout
            recent = []
        self._fails[key] = recent

    def ok(self, peer: str | None) -> None:
        key = key_for(peer)
        if key is not None:
            self._fails.pop(key, None)

    def _sweep(self, now: float) -> None:
        for k in [k for k, t in self._locked.items() if t <= now]:
            del self._locked[k]
        for k in [k for k, ts in self._fails.items() if not ts or now - ts[-1] > self.window]:
            del self._fails[k]
        while len(self._fails) > MAX_TRACKED:
            self._fails.pop(next(iter(self._fails)))


def wait_text(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    return f"Too many wrong tries from this address. Try again in about {minutes} minute{'s' if minutes != 1 else ''}."
