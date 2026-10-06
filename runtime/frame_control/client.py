from __future__ import annotations

import asyncio

from adapters.controller import ControllerState
from .protocol import PROTOCOL_VERSION, FrameProtocolError, read_message, write_message


class FrameControlError(RuntimeError):
    pass


class FrameControlClient:
    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        session_id: str,
        *,
        request_timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.session_id = session_id
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.sequence = 0
        self.request_timeout = request_timeout

    async def connect(self) -> dict:
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        return await self._request(
            "hello",
            token=self.token,
            session_id=self.session_id,
            protocol_version=PROTOCOL_VERSION,
        )

    async def close(self) -> None:
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
        self.reader = None
        self.writer = None

    async def pause(self, frame: int) -> dict:
        return await self._request("pause", frame=frame)

    async def inject(self, frame: int, slot: int, state: ControllerState) -> dict:
        return await self._request(
            "inject",
            frame=frame,
            slot=slot,
            buttons=state.buttons,
            stick_x=state.stick_x,
            stick_y=state.stick_y,
        )

    async def advance(self, frame: int) -> dict:
        return await self._request("advance", frame=frame)

    async def state_hash(self, frame: int) -> str:
        return (await self._request("state_hash", frame=frame))["state_hash"]

    async def _request(self, operation: str, **payload) -> dict:
        if self.reader is None or self.writer is None:
            raise FrameControlError("frame-control client is not connected")
        sequence = self.sequence
        self.sequence += 1
        try:
            await write_message(
                self.writer, {"sequence": sequence, "operation": operation, **payload}
            )
            response = await asyncio.wait_for(
                read_message(self.reader), timeout=self.request_timeout
            )
        except (EOFError, TimeoutError, FrameProtocolError, OSError) as exc:
            raise FrameControlError(f"frame-control transport failed: {exc}") from exc
        if response.get("sequence") != sequence:
            raise FrameControlError("frame-control response sequence mismatch")
        if not response.get("ok"):
            raise FrameControlError(response.get("error", "frame-control request failed"))
        return response.get("result", {})
