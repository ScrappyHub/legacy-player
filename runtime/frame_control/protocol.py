from __future__ import annotations

import asyncio
import json
import struct


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 64 * 1024
LENGTH = struct.Struct("!I")


class FrameProtocolError(RuntimeError):
    pass


async def read_message(reader: asyncio.StreamReader) -> dict:
    try:
        header = await reader.readexactly(LENGTH.size)
    except asyncio.IncompleteReadError as exc:
        raise EOFError from exc
    size = LENGTH.unpack(header)[0]
    if size == 0 or size > MAX_MESSAGE_BYTES:
        raise FrameProtocolError(f"invalid frame-control message size: {size}")
    try:
        payload = await reader.readexactly(size)
        message = json.loads(payload)
    except asyncio.IncompleteReadError as exc:
        raise EOFError from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrameProtocolError("invalid frame-control JSON") from exc
    if not isinstance(message, dict):
        raise FrameProtocolError("frame-control message must be an object")
    return message


async def write_message(writer: asyncio.StreamWriter, message: dict) -> None:
    payload = json.dumps(message, separators=(",", ":"), sort_keys=True).encode()
    if len(payload) > MAX_MESSAGE_BYTES:
        raise FrameProtocolError("frame-control response is too large")
    writer.write(LENGTH.pack(len(payload)) + payload)
    await writer.drain()
