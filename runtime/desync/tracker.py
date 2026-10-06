from __future__ import annotations

import re
from dataclasses import dataclass


HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CheckpointResult:
    frame: int
    complete: bool
    matched: bool | None
    hashes: dict[str, str]


class DesyncTracker:
    def __init__(self, participant_ids: set[str], *, max_pending: int = 32) -> None:
        self.participant_ids = frozenset(participant_ids)
        self.max_pending = max_pending
        self.pending: dict[int, dict[str, str]] = {}

    def submit(self, frame: int, participant_id: str, state_hash: str) -> CheckpointResult:
        if participant_id not in self.participant_ids:
            raise ValueError(f"unknown participant: {participant_id}")
        if frame < 0:
            raise ValueError("checkpoint frame must be non-negative")
        normalized = state_hash.lower()
        if not HASH_PATTERN.fullmatch(normalized):
            raise ValueError("state_hash must be a 64-character SHA-256 hex digest")
        values = self.pending.setdefault(frame, {})
        if participant_id in values:
            raise ValueError(f"duplicate checkpoint for frame {frame}: {participant_id}")
        values[participant_id] = normalized
        if len(self.pending) > self.max_pending:
            oldest = min(self.pending)
            del self.pending[oldest]
            raise RuntimeError(f"checkpoint window exceeded; dropped frame {oldest}")
        complete = set(values) == set(self.participant_ids)
        result = CheckpointResult(
            frame=frame,
            complete=complete,
            matched=len(set(values.values())) == 1 if complete else None,
            hashes=dict(values),
        )
        if complete:
            del self.pending[frame]
        return result
