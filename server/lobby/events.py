from __future__ import annotations

from datetime import UTC, datetime

# Event kinds a client may be notified about. Kept explicit so the UI can
# render each one with a clear, plain-language message.
EVENT_KINDS = frozenset(
    {
        "session_created",
        "join_requested",
        "join_denied",
        "participant_joined",
        "participant_left",
        "participant_kicked",
        "participant_disconnected",
        "participant_reconnected",
        "invite_created",
        "invites_revoked",
        "session_resumed",
        "server_stopping",
        "endpoint_published",
        "waitlist_joined",
        "waitlist_priority",
        "waitlist_dropped",
        "slot_opened",
        "capacity_changed",
    }
)


class EventLog:
    """Bounded, sequence-numbered notification log for one session."""

    def __init__(self, limit: int = 512) -> None:
        self.limit = limit
        self._events: list[dict] = []
        self._next_seq = 1

    def emit(self, kind: str, *, audience: str = "all", **data) -> dict:
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind: {kind}")
        if audience not in {"all", "host"}:
            raise ValueError("audience must be 'all' or 'host'")
        event = {
            "seq": self._next_seq,
            "kind": kind,
            "audience": audience,
            "at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "data": data,
        }
        self._next_seq += 1
        self._events.append(event)
        del self._events[: -self.limit]
        return event

    def since(self, after_seq: int, *, is_host: bool) -> list[dict]:
        return [
            event
            for event in self._events
            if event["seq"] > after_seq and (is_host or event["audience"] == "all")
        ]

    def export(self) -> dict:
        return {"next_seq": self._next_seq, "events": list(self._events)}

    @classmethod
    def restore(cls, data: dict, limit: int = 512) -> "EventLog":
        log = cls(limit)
        log._next_seq = int(data["next_seq"])
        log._events = list(data["events"])[-limit:]
        return log
