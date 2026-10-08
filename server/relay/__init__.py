"""Relay: pipe bytes between a room's host and its guests so nobody learns anyone's address.

The host parks a few outbound connections here; each guest connection is paired with one
idle host connection and the two are copied byte for byte. What flows through is the
TLS-PSK tunnel the players already use, so this server cannot read the game traffic.
Only authenticated room members can use a room's relay.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
from collections import deque


class Relay:
    def __init__(self, service, max_parked: int = 8, max_streams: int = 256, idle_seconds: float = 600.0,
                 per_member: int = 2) -> None:
        self.service = service
        self.max_parked = max_parked
        self.max_streams = max_streams
        self.idle_seconds = idle_seconds
        self.per_member = per_member
        self.parked: dict[str, deque] = {}          # session id -> idle host (reader, writer, paired future)
        self.active = 0
        self.member_streams: dict[tuple[str, str], int] = {}
        self.punch_parked: dict[str, deque] = {}    # session id -> waiting host (endpoint, paired future)
        self.punch_wait_seconds = 120.0

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
        member = (sid, participant_id)
        if self.member_streams.get(member, 0) >= self.per_member or self.active >= self.max_streams:
            self._reply(writer, False, error="too many relay connections; close one first")
            await writer.drain()
            return
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
            watcher = asyncio.ensure_future(self._watch_parked(reader, paired))
            guest = await paired   # (reader, writer, done, member) of the guest, or None
            watcher.cancel()
            if guest is None:
                return
            self.member_streams[member] = self.member_streams.get(member, 0) + 1
            self.member_streams[guest[3]] = self.member_streams.get(guest[3], 0) + 1
            try:
                await self._pipe(reader, writer, guest[0], guest[1])
            finally:
                for m in (member, guest[3]):
                    self.member_streams[m] = max(0, self.member_streams.get(m, 1) - 1)
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
            paired.set_result((reader, writer, done, member))
            await done   # the host-side coroutine runs the pipe and owns both writers
            return
        self._reply(writer, False, error="role must be host or guest")
        await writer.drain()

    @staticmethod
    def _endpoint(writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        if not peer:
            return None
        host = peer[0]
        try:
            ip = ipaddress.ip_address(host)
            if getattr(ip, "ipv4_mapped", None):
                host = str(ip.ipv4_mapped)
        except ValueError:
            return None
        return [host, int(peer[1])]

    async def handle_punch(self, request: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Introduce a room's host and one guest to each other so their computers can connect directly.

        Each side connects here from the local port it will use for the direct connection, so the
        address this server sees is the one the player's router hands out for that port. The server
        tells each side the other's address and then steps out; no game data touches it. Both
        players must have said yes (consent), because the other side learns their address."""
        try:
            session, participant_id = self.service.relay_authorize(request)
        except Exception as exc:
            self._reply(writer, False, error=str(exc))
            await writer.drain()
            return
        if not request.get("consent"):
            self._reply(writer, False, error="direct connections need both players to agree")
            await writer.drain()
            return
        mine = self._endpoint(writer)
        sid = session.session_id
        role = request.get("role")
        if mine is None or role not in {"host", "guest"}:
            self._reply(writer, False, error="could not work out a direct route")
            await writer.drain()
            return
        if role == "host":
            if participant_id != session.host_id:
                self._reply(writer, False, error="only the host waits for direct connections")
                await writer.drain()
                return
            queue = self.punch_parked.setdefault(sid, deque())
            while len(queue) >= self.max_parked:
                old = queue.popleft()
                if not old[1].done():
                    old[1].set_result(None)
            paired: asyncio.Future = asyncio.get_running_loop().create_future()
            queue.append((mine, paired))
            self._reply(writer, True, parked=True)
            await writer.drain()
            watcher = asyncio.ensure_future(self._watch_parked(reader, paired))
            try:
                other = await asyncio.wait_for(asyncio.shield(paired), self.punch_wait_seconds)
            except (asyncio.TimeoutError, TimeoutError):
                other = None
            finally:
                watcher.cancel()
                if not paired.done():
                    paired.set_result(None)
            if other is None:
                self._reply(writer, False, error="nobody tried to connect directly")
            else:
                self._reply(writer, True, peer=other)
            try:
                await writer.drain()
            except OSError:
                pass
            return
        queue = self.punch_parked.get(sid) or deque()
        while queue:
            host_endpoint, paired = queue.popleft()
            if not paired.done():
                break
        else:
            self._reply(writer, False, error="the host is not waiting for a direct connection")
            await writer.drain()
            return
        paired.set_result(mine)
        self._reply(writer, True, peer=host_endpoint)
        await writer.drain()

    async def _watch_parked(self, reader: asyncio.StreamReader, paired: asyncio.Future) -> None:
        """A parked host connection that hangs up (host crashed or relaunched) is dropped at once."""
        try:
            data = await reader.read(1)
        except (OSError, asyncio.CancelledError):
            return
        if not paired.done():
            paired.set_result(None)   # EOF or stray bytes: never hand this slot to a guest

    async def _pipe(self, a_r, a_w, b_r, b_w) -> None:
        self.active += 1
        try:
            await asyncio.gather(_copy(a_r, b_w, self.idle_seconds), _copy(b_r, a_w, self.idle_seconds))
        finally:
            self.active -= 1
            for w in (a_w, b_w):
                try:
                    w.close()
                except Exception:
                    pass

    def drop_session(self, sid: str) -> None:
        for _, paired in self.punch_parked.pop(sid, ()):
            if not paired.done():
                paired.set_result(None)
        for _, w, paired in self.parked.pop(sid, ()):
            if not paired.done():
                paired.set_result(None)
            w.close()


async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, idle_seconds: float = 600.0) -> None:
    try:
        while True:
            data = await asyncio.wait_for(reader.read(65536), idle_seconds)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError, OSError, TimeoutError):
        pass
    finally:
        try:
            if writer.can_write_eof():
                writer.write_eof()
        except (OSError, RuntimeError):
            pass
