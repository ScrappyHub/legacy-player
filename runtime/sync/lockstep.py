from __future__ import annotations

from dataclasses import dataclass


class LockstepError(RuntimeError):
    pass


@dataclass(frozen=True)
class InputFrame:
    frame: int
    participant_id: str
    buttons: int
    stick_x: int = 0
    stick_y: int = 0

    def __post_init__(self) -> None:
        if self.frame < 0:
            raise ValueError("frame must be non-negative")
        if not -128 <= self.stick_x <= 127 or not -128 <= self.stick_y <= 127:
            raise ValueError("stick axes must be signed bytes")


@dataclass(frozen=True)
class FrameBundle:
    frame: int
    inputs: tuple[InputFrame, ...]


class LockstepCoordinator:
    def __init__(
        self,
        participant_ids: set[str],
        *,
        start_frame: int = 0,
        max_frame_lead: int = 8,
    ) -> None:
        if not participant_ids:
            raise ValueError("at least one participant is required")
        self.participant_ids = frozenset(participant_ids)
        self.next_frame = start_frame
        if max_frame_lead < 0:
            raise ValueError("max_frame_lead must be non-negative")
        self.max_frame_lead = max_frame_lead
        self._pending: dict[int, dict[str, InputFrame]] = {}

    def submit(self, item: InputFrame) -> FrameBundle | None:
        if item.participant_id not in self.participant_ids:
            raise LockstepError(f"unknown participant: {item.participant_id}")
        if item.frame < self.next_frame:
            raise LockstepError(f"stale input frame: {item.frame}")
        if item.frame > self.next_frame + self.max_frame_lead:
            raise LockstepError(
                f"input frame {item.frame} exceeds lead window ending at "
                f"{self.next_frame + self.max_frame_lead}"
            )
        frame_inputs = self._pending.setdefault(item.frame, {})
        if item.participant_id in frame_inputs:
            raise LockstepError(
                f"duplicate input for frame {item.frame}: {item.participant_id}"
            )
        frame_inputs[item.participant_id] = item
        return self.release_next()

    def release_next(self) -> FrameBundle | None:
        frame_inputs = self._pending.get(self.next_frame)
        if frame_inputs is None or set(frame_inputs) != set(self.participant_ids):
            return None
        frame = self.next_frame
        inputs = tuple(frame_inputs[key] for key in sorted(frame_inputs))
        del self._pending[frame]
        self.next_frame += 1
        return FrameBundle(frame=frame, inputs=inputs)
