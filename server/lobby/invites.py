from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import deque

# Crockford base32: no I, L, O, U, so codes survive being read aloud or typed.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 10  # 50 bits of entropy, shown as XXXXX-XXXXX
MAX_TTL_SECONDS = 24 * 3600
DEFAULT_TTL_SECONDS = 15 * 60


class InviteError(RuntimeError):
    pass


def normalize(code: str) -> str:
    cleaned = "".join(ch for ch in code.upper() if ch not in "- _")
    return cleaned.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))


def format_code(raw: str) -> str:
    return f"{raw[:5]}-{raw[5:]}"


class InviteBook:
    """Short, expiring invite codes. Only keyed hashes are kept at rest.

    A code is a bearer secret: anyone holding it can request to join until it
    expires, runs out of uses, or is revoked. Wrong guesses are rate limited
    globally so the short code cannot be brute forced online.
    """

    def __init__(
        self,
        *,
        pepper: bytes | None = None,
        clock=time.time,
        max_failures: int = 10,
        failure_window: float = 60.0,
    ) -> None:
        self.pepper = pepper if pepper is not None else secrets.token_bytes(32)
        self.clock = clock
        self.max_failures = max_failures
        self.failure_window = failure_window
        self._records: dict[str, dict] = {}
        self._failures: deque[float] = deque()

    def _digest(self, raw: str) -> str:
        return hmac.new(self.pepper, raw.encode(), hashlib.sha256).hexdigest()

    def create(
        self, session_id: str, *, ttl_seconds: float = DEFAULT_TTL_SECONDS, max_uses: int = 8,
        priority: bool = False,
    ) -> tuple[str, dict]:
        if isinstance(ttl_seconds, bool) or not 0 < ttl_seconds <= MAX_TTL_SECONDS:
            raise InviteError(f"ttl_seconds must be between 1 and {MAX_TTL_SECONDS}")
        if isinstance(max_uses, bool) or not isinstance(max_uses, int) or not 1 <= max_uses <= 16:
            raise InviteError("max_uses must be an integer from 1 to 16")
        raw = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        record = {
            "session_id": session_id,
            "expires_at": self.clock() + ttl_seconds,
            "uses_left": max_uses,
            "priority": bool(priority),
        }
        self._records[self._digest(raw)] = record
        return format_code(raw), {"expires_at": record["expires_at"], "max_uses": max_uses,
                                  "priority": record["priority"]}

    def redeem(self, code: str) -> str:
        """Consume one use of a code and return its session id."""
        return self.redeem_ex(code)[0]

    def redeem_ex(self, code: str) -> tuple[str, bool]:
        """Consume one use; return (session id, whether the code grants queue priority)."""
        now = self.clock()
        while self._failures and now - self._failures[0] > self.failure_window:
            self._failures.popleft()
        if len(self._failures) >= self.max_failures:
            raise InviteError("too many invalid invite attempts; try again shortly")
        record = self._records.get(self._digest(normalize(code))) if isinstance(code, str) else None
        if record is None or record["uses_left"] <= 0 or record["expires_at"] < now:
            self._failures.append(now)
            raise InviteError("invalid or expired invite code")
        record["uses_left"] -= 1
        return record["session_id"], bool(record.get("priority", False))

    def revoke_session(self, session_id: str) -> int:
        doomed = [key for key, rec in self._records.items() if rec["session_id"] == session_id]
        for key in doomed:
            del self._records[key]
        return len(doomed)

    def prune(self) -> None:
        now = self.clock()
        for key in [k for k, r in self._records.items() if r["expires_at"] < now or r["uses_left"] <= 0]:
            del self._records[key]

    def export(self) -> dict:
        return {"records": dict(self._records)}

    def load(self, data: dict) -> None:
        self._records = {key: dict(value) for key, value in data["records"].items()}
