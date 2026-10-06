"""Relay: pipe bytes between a room's host and its guests so nobody learns anyone's address.

The host parks a few outbound connections here; each guest connection is paired with one
idle host connection and the two are copied byte for byte. What flows through is the
TLS-PSK tunnel the players already use, so this server cannot read the game traffic.
Only authenticated room members can use a room's relay.
"""
from __future__ import annotations

import asyncio
import json
from collections import deque


class Relay:
    def __init__(self, service, max_parked: int = 8, max_streams: int = 256) -> None:
        self.service = service
        self.max_parked = max_parked
        self.parked: dict[str, deque] = {}          # session id -> idle host (reader, writer, paired future)
        self.streams = asyncio.Semaphore(max_streams)
        self.active = 0

    @staticmethod
    def _reply(writer: asyncio.StreamWriter, ok: bool, **payload) -> None:
        body = {"ok": ok, **({"result": payload} if ok else {"error": payload.get("error", "relay error")})}
        writer.write(json.dumps(body, separators=(",", ":")).encode() + b"\n")

    async def handle(self, request: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Called by the lobby server after it read the first JSON line of a connection."""
        try:
            session, participant_id = self.service.relay_authorize(request)
        except Exception as exc:  # LobbyError: wrong room, wrong credential
            self._reply(writer, False, error=str(exc))
            await writer.drain()
            return
        role = request.get("role")
        sid = session.session_id
        if role == "host":
            if participant_id != session.host_id:
                self._reply(writer, False, error="only the host parks relay connections")
                await writer.drain()
                return
            queue = self.parked.setdefault(sid, deque())
            if len(queue) >= self.max_parked:
                self._reply(writer, False, error="enough host connections are parked already")
                await writer.drain()
                return
            paired: asyncio.Future = asyncio.get_running_loop().create_future()
            queue.append((reader, writer, paired))
            self._reply(writer, True, parked=True)
            await writer.drain()
            guest = await paired   # (reader, writer, done) of the guest, or None
            if guest is None:
                return
            try:
                await self._pipe(reader, writer, guest[0], guest[1])
            finally:
                if not guest[2].done():
                    guest[2].set_result(True)
            return
        if role == "guest":
            queue = self.parked.get(sid) or deque()
            while queue:
                h_reader, h_writer, paired = queue.popleft()
                if not paired.done() and not h_writer.is_closing():
                    break
            else:
                self._reply(writer, False, error="the host's relay is not ready; ask them to launch first")
                await writer.drain()
                return
            self._reply(h_writer, True, paired=True)
            self._reply(writer, True, paired=True)
            await asyncio.gather(h_writer.drain(), writer.drain())
            done: asyncio.Future = asyncio.get_running_loop().create_future()
            paired.set_result((reader, writer, done))
            await done   # the host-side coroutine runs the pipe and owns both writers
            return
        self._reply(writer, False, error="role must be host or guest")
        await writer.drain()

    async def _pipe(self, a_r, a_w, b_r, b_w) -> None:
        async with self.streams:
            self.active += 1
            try:
                await asyncio.gather(_copy(a_r, b_w), _copy(b_r, a_w))
            finally:
                self.active -= 1
                for w in (a_w, b_w):
                    try:
                        w.close()
                    except Exception:
                        pass

    def drop_session(self, sid: str) -> None:
        for _, w, paired in self.parked.pop(sid, ()):
            if not paired.done():
                paired.set_result(None)
            w.close()


async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError, OSError):
        pass
    finally:
        try:
            if writer.can_write_eof():
                writer.write_eof()
        except (OSError, RuntimeError):
            pass
