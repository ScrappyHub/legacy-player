from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from dataclasses import dataclass, field

from adapters.controller import ControllerState
from .protocol import PROTOCOL_VERSION, FrameProtocolError, read_message, write_message


class ConformanceError(RuntimeError):
    pass


@dataclass
class ConformanceEngine:
    required_slots: frozenset[int]
    current_frame: int = 0
    paused_frame: int | None = None
    inputs: dict[int, ControllerState] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)

    def pause(self, frame: int) -> dict:
        if frame != self.current_frame:
            raise ConformanceError(
                f"pause expected frame {self.current_frame}, got {frame}"
            )
        if self.paused_frame is not None:
            raise ConformanceError("emulator is already paused")
        self.paused_frame = frame
        self.inputs = {}
        return {"frame": frame, "paused": True}

    def inject(self, frame: int, slot: int, state: ControllerState) -> dict:
        if self.paused_frame != frame:
            raise ConformanceError(f"frame {frame} is not paused")
        if slot not in self.required_slots:
            raise ConformanceError(f"unconfigured controller slot: {slot}")
        if slot in self.inputs:
            raise ConformanceError(f"duplicate input for slot {slot}")
        self.inputs[slot] = state
        return {"frame": frame, "slot": slot, "accepted": True}

    def advance(self, frame: int) -> dict:
        if self.paused_frame != frame:
            raise ConformanceError(f"frame {frame} is not paused")
        missing = sorted(self.required_slots - set(self.inputs))
        if missing:
            raise ConformanceError(f"cannot advance; missing controller slots: {missing}")
        record = {
            "frame": frame,
            "inputs": {
                str(slot): {
                    "buttons": state.buttons,
                    "stick_x": state.stick_x,
                    "stick_y": state.stick_y,
                }
                for slot, state in sorted(self.inputs.items())
            },
        }
        self.history.append(record)
        self.current_frame += 1
        self.paused_frame = None
        self.inputs = {}
        return {"advanced_frame": frame, "next_frame": self.current_frame}

    def state_hash(self, frame: int) -> str:
        if frame < 0 or frame >= len(self.history):
            raise ConformanceError(f"state hash unavailable for frame {frame}")
        canonical = json.dumps(self.history[: frame + 1], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class ConformanceServer:
    def __init__(self, token: str, session_id: str, engine: ConformanceEngine) -> None:
        self.token = token
        self.session_id = session_id
        self.engine = engine

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        authenticated = False
        expected_sequence = 0
        try:
            while True:
                try:
                    message = await asyncio.wait_for(read_message(reader), timeout=30)
                except (EOFError, TimeoutError):
                    break
                except FrameProtocolError as exc:
                    await write_message(writer, {"sequence": expected_sequence, "ok": False, "error": str(exc)})
                    break
                sequence = message.get("sequence")
                if sequence != expected_sequence:
                    await write_message(writer, {"sequence": sequence, "ok": False, "error": "invalid request sequence"})
                    break
                expected_sequence += 1
                try:
                    operation = message.get("operation")
                    if not authenticated:
                        if operation != "hello":
                            raise ConformanceError("hello must be the first operation")
                        if message.get("protocol_version") != PROTOCOL_VERSION:
                            raise ConformanceError("unsupported protocol version")
                        if not isinstance(message.get("token"), str) or not secrets.compare_digest(
                            message["token"], self.token
                        ):
                            raise ConformanceError("authentication failed")
                        if message.get("session_id") != self.session_id:
                            raise ConformanceError("frame-control session mismatch")
                        authenticated = True
                        result = {
                            "protocol_version": PROTOCOL_VERSION,
                            "capabilities": ["pause", "inject", "advance", "state_hash"],
                            "required_slots": sorted(self.engine.required_slots),
                        }
                    elif operation == "pause":
                        result = self.engine.pause(_integer(message, "frame", 0))
                    elif operation == "inject":
                        result = self.engine.inject(
                            _integer(message, "frame", 0),
                            _integer(message, "slot", 0, 3),
                            ControllerState(
                                buttons=_integer(message, "buttons", 0, 0xFFFFFFFF),
                                stick_x=_integer(message, "stick_x", -128, 127),
                                stick_y=_integer(message, "stick_y", -128, 127),
                            ),
                        )
                    elif operation == "advance":
                        result = self.engine.advance(_integer(message, "frame", 0))
                    elif operation == "state_hash":
                        frame = _integer(message, "frame", 0)
                        result = {"frame": frame, "state_hash": self.engine.state_hash(frame)}
                    else:
                        raise ConformanceError(f"unsupported operation: {operation!r}")
                    response = {"sequence": sequence, "ok": True, "result": result}
                except (ConformanceError, ValueError) as exc:
                    response = {"sequence": sequence, "ok": False, "error": str(exc)}
                await write_message(writer, response)
                if not authenticated:
                    break
        finally:
            writer.close()
            await writer.wait_closed()


def _integer(message: dict, key: str, minimum: int, maximum: int | None = None) -> int:
    value = message.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConformanceError(f"{key} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise ConformanceError(f"{key} must be an integer <= {maximum}")
    return value


async def serve_conformance(
    token: str,
    required_slots: set[int],
    host: str = "127.0.0.1",
    port: int = 0,
    session_id: str = "session",
) -> tuple[asyncio.Server, ConformanceEngine]:
    if not token or len(token) < 32:
        raise ValueError("frame-control token must contain at least 32 characters")
    if not required_slots or any(slot not in range(4) for slot in required_slots):
        raise ValueError("required slots must contain one or more values from 0 through 3")
    engine = ConformanceEngine(frozenset(required_slots))
    if not session_id:
        raise ValueError("frame-control session id is required")
    handler = ConformanceServer(token, session_id, engine)
    server = await asyncio.start_server(handler.handle, host, port, limit=128 * 1024)
    return server, engine
