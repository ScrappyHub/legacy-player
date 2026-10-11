from __future__ import annotations

import asyncio
import json


REQUEST_LIMIT_ERROR = "connection request limit reached"   # what the server says before ending a connection


class CoordinationError(RuntimeError):
    pass


class CoordinationClient:
    """Newline-delimited JSON requests to the coordination server.

    persistent=False (the default) opens a connection per request. persistent=True keeps one connection open and
    reuses it (the server answers many requests per connection); if a reused connection turns out to be dead, or the
    server ends it, the request is sent once more on a fresh connection. Call close() when done."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, *, persistent: bool = False) -> None:
        self.host = host
        self.port = port
        self.persistent = persistent
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.connections_opened = 0

    async def _connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        self.connections_opened += 1
        return reader, writer

    @staticmethod
    async def _exchange(reader, writer, payload: dict) -> dict:
        writer.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        await writer.drain()
        line = await reader.readline()
        if not line:
            raise ConnectionResetError("coordination server closed without a response")
        return json.loads(line)

    @staticmethod
    def _result(response: dict) -> dict:
        if not response.get("ok"):
            raise CoordinationError(response.get("error", "coordination request failed"))
        return response["result"]

    async def request(self, payload: dict) -> dict:
        if not self.persistent:
            reader, writer = await self._connect()
            try:
                try:
                    response = await self._exchange(reader, writer, payload)
                except ConnectionResetError as exc:
                    raise CoordinationError(str(exc)) from exc
                return self._result(response)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (OSError, ConnectionError):
                    pass
        reused = self._writer is not None
        if not reused:
            self._reader, self._writer = await self._connect()
        try:
            response = await self._exchange(self._reader, self._writer, payload)
        except (OSError, ConnectionError, asyncio.IncompleteReadError) as exc:
            await self.close()
            if not reused:
                raise CoordinationError(f"coordination server connection failed: {exc}") from exc
            self._reader, self._writer = await self._connect()          # a stale connection: one fresh try
            try:
                response = await self._exchange(self._reader, self._writer, payload)
            except (OSError, ConnectionError, asyncio.IncompleteReadError) as again:
                await self.close()
                raise CoordinationError(f"coordination server connection failed: {again}") from again
        if not response.get("ok") and response.get("error") == REQUEST_LIMIT_ERROR:
            await self.close()               # the server ends a connection after its request limit; start a new one
            self._reader, self._writer = await self._connect()
            try:
                response = await self._exchange(self._reader, self._writer, payload)
            except (OSError, ConnectionError, asyncio.IncompleteReadError) as exc:
                await self.close()
                raise CoordinationError(f"coordination server connection failed: {exc}") from exc
        return self._result(response)

    async def close(self) -> None:
        writer, self._reader, self._writer = self._writer, None, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ConnectionError):
                pass
