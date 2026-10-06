from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class ReplayRecorder:
    session_id: str
    metadata: dict
    max_events: int = 100_000
    events: list[dict] = field(default_factory=list)
    started_at_utc: str = field(default_factory=utc_now)

    def record(self, event: str, payload: dict | None = None) -> None:
        if len(self.events) >= self.max_events:
            raise RuntimeError("replay event limit reached")
        self.events.append(
            {"sequence": len(self.events), "at_utc": utc_now(), "event": event, "payload": payload or {}}
        )

    def package(self) -> dict:
        return {
            "schema": "legacy_player.replay.v1",
            "session_id": self.session_id,
            "started_at_utc": self.started_at_utc,
            "finalized_at_utc": utc_now(),
            "metadata": self.metadata,
            "event_count": len(self.events),
            "events": list(self.events),
        }


class ReplayStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, package: dict) -> Path:
        session_id = package.get("session_id", "")
        if not isinstance(session_id, str) or not session_id or any(
            char not in "0123456789abcdef-" for char in session_id.lower()
        ):
            raise ValueError("unsafe replay session id")
        target = (self.root / f"{session_id}.json").resolve()
        if target.parent != self.root:
            raise ValueError("replay path escapes storage root")
        data = json.dumps(package, indent=2, sort_keys=True) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=".replay-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return target
