from __future__ import annotations

from adapters.controller import ControllerState
from runtime.frame_control import FrameControlClient


class DeterministicDolphinBridge:
    def __init__(self, client: FrameControlClient, participant_slots: dict[str, int]) -> None:
        self.client = client
        self.participant_slots = dict(participant_slots)
        self.next_frame = 0

    async def apply_bundle(self, bundle: dict) -> str:
        frame = int(bundle["frame"])
        if frame != self.next_frame:
            raise ValueError(f"expected frame {self.next_frame}, got {frame}")
        inputs = {item["participant_id"]: item for item in bundle.get("inputs", [])}
        if set(inputs) != set(self.participant_slots):
            raise ValueError("bundle participants do not match controller mapping")
        await self.client.pause(frame)
        for participant_id, slot in sorted(self.participant_slots.items(), key=lambda item: item[1]):
            item = inputs[participant_id]
            await self.client.inject(
                frame,
                slot,
                ControllerState(
                    buttons=int(item["buttons"]),
                    stick_x=int(item.get("stick_x", 0)),
                    stick_y=int(item.get("stick_y", 0)),
                ),
            )
        await self.client.advance(frame)
        state_hash = await self.client.state_hash(frame)
        self.next_frame += 1
        return state_hash
