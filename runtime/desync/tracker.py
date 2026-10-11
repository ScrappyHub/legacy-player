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
        # per participant: the highest frame whose checkpoint was completed (compared) with this participant in it.
        # Anything at or below it is a resubmission of a settled frame and is refused.
        self.completed_through: dict[str, int] = {}

    def submit(self, frame: int, participant_id: str, state_hash: str) -> CheckpointResult:
        if participant_id not in self.participant_ids:
            raise ValueError(f"unknown participant: {participant_id}")
        if isinstance(frame, bool) or not isinstance(frame, int):
            raise ValueError("checkpoint frame must be a whole number")
        if frame < 0:
            raise ValueError("checkpoint frame must be non-negative")
        if not isinstance(state_hash, str):
            raise ValueError("state_hash must be a 64-character SHA-256 hex digest")
        normalized = state_hash.lower()
        if not HASH_PATTERN.fullmatch(normalized):
            raise ValueError("state_hash must be a 64-character SHA-256 hex digest")
        settled = self.completed_through.get(participant_id, -1)
        if frame <= settled:
            raise ValueError(f"checkpoint for frame {frame} is already settled (through frame {settled}): {participant_id}")
        existing = self.pending.get(frame)
        if existing is not None and participant_id in existing:
            raise ValueError(f"duplicate checkpoint for frame {frame}: {participant_id}")
        if existing is None and len(self.pending) >= self.max_pending:
            # checked before anything is stored, so a refused submission leaves no trace
            raise RuntimeError(
                f"checkpoint window exceeded ({self.max_pending} frames waiting, oldest {min(self.pending)}); "
                f"frame {frame} was not recorded"
            )
        values = self.pending.setdefault(frame, {})
        values[participant_id] = normalized
        complete = set(values) == set(self.participant_ids)
        if complete:
            for member in self.participant_ids:
                self.completed_through[member] = max(self.completed_through.get(member, -1), frame)
        result = CheckpointResult(
            frame=frame,
            complete=complete,
            matched=len(set(values.values())) == 1 if complete else None,
            hashes=dict(values),
        )
        if complete:
            # this frame and any older one still waiting are settled now (an older one can no longer be completed)
            for old in [f for f in self.pending if f <= frame]:
                del self.pending[old]
        return result
