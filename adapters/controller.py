from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ControllerState:
    buttons: int = 0
    stick_x: int = 0
    stick_y: int = 0

    def __post_init__(self) -> None:
        if self.buttons < 0:
            raise ValueError("buttons must be a non-negative bit field")
        if not -128 <= self.stick_x <= 127 or not -128 <= self.stick_y <= 127:
            raise ValueError("stick axes must be signed bytes")


class ControllerAdapter(Protocol):
    """Boundary between the shared runtime and emulator-specific controller I/O."""

    @property
    def adapter_id(self) -> str: ...

    def current_frame(self) -> int: ...

    def capture_local_input(self, slot: int) -> ControllerState: ...

    def inject_remote_input(
        self, frame: int, slot: int, state: ControllerState
    ) -> None: ...

    def pause_at_frame(self, frame: int) -> None: ...

    def resume(self) -> None: ...
