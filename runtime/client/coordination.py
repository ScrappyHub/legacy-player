from __future__ import annotations

import asyncio
import json


class CoordinationError(RuntimeError):
    pass


class CoordinationClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port

    async def request(self, payload: dict) -> dict:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            writer.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
            await writer.drain()
            line = await reader.readline()
            if not line:
                raise CoordinationError("coordination server closed without a response")
            response = json.loads(line)
            if not response.get("ok"):
                raise CoordinationError(response.get("error", "coordination request failed"))
            return response["result"]
        finally:
            writer.close()
            await writer.wait_closed()
