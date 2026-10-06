from __future__ import annotations

import asyncio
import binascii
import secrets
import struct
from dataclasses import dataclass, field
from enum import IntFlag

from adapters.controller import ControllerState


PROTOCOL_VERSION = 1001
CLIENT_MAGIC = b"DSUC"
SERVER_MAGIC = b"DSUS"
VERSION_TYPE = 0x100000
PORTS_TYPE = 0x100001
PAD_DATA_TYPE = 0x100002
DEFAULT_PORT = 26760

HEADER = struct.Struct("<4sHHII")
PORT_INFO_PAYLOAD = struct.Struct("<IBBBB6sBB")
PAD_PREFIX = struct.Struct("<IBBBB6sBBIBBBBBBBB")


class DsuProtocolError(ValueError):
    pass


class GameCubeButtons(IntFlag):
    A = 1 << 0
    B = 1 << 1
    X = 1 << 2
    Y = 1 << 3
    START = 1 << 4
    DPAD_LEFT = 1 << 5
    DPAD_DOWN = 1 << 6
    DPAD_RIGHT = 1 << 7
    DPAD_UP = 1 << 8
    L = 1 << 9
    R = 1 << 10
    Z = 1 << 11


def _packet(message_type: int, payload: bytes, server_uid: int) -> bytes:
    body = struct.pack("<I", message_type) + payload
    packet = bytearray(
        HEADER.pack(SERVER_MAGIC, PROTOCOL_VERSION, len(body), 0, server_uid) + body
    )
    struct.pack_into("<I", packet, 8, binascii.crc32(packet) & 0xFFFFFFFF)
    return bytes(packet)


def parse_request(data: bytes) -> tuple[int, bytes, int]:
    if len(data) < HEADER.size + 4:
        raise DsuProtocolError("DSU packet is too short")
    magic, version, body_length, expected_crc, client_uid = HEADER.unpack_from(data)
    if magic != CLIENT_MAGIC or version > PROTOCOL_VERSION:
        raise DsuProtocolError("unsupported DSU packet header")
    if body_length + HEADER.size != len(data):
        raise DsuProtocolError("invalid DSU packet length")
    checked = bytearray(data)
    struct.pack_into("<I", checked, 8, 0)
    if binascii.crc32(checked) & 0xFFFFFFFF != expected_crc:
        raise DsuProtocolError("invalid DSU packet CRC")
    return struct.unpack_from("<I", data, HEADER.size)[0], data[HEADER.size + 4 :], client_uid


def port_info_packet(pad_id: int, server_uid: int) -> bytes:
    payload = PORT_INFO_PAYLOAD.pack(
        PORTS_TYPE, pad_id, 2, 3, 1, bytes((2, 0, 0, 0, 0, pad_id)), 5, 0
    )[4:]
    return _packet(PORTS_TYPE, payload, server_uid)


def pad_data_packet(
    pad_id: int, state: ControllerState, packet_counter: int, server_uid: int
) -> bytes:
    buttons = GameCubeButtons(state.buttons)
    states1 = 0x08 if buttons & GameCubeButtons.START else 0
    states2 = 0
    left_x = max(0, min(255, state.stick_x + 128))
    left_y = max(0, min(255, 128 - state.stick_y))
    analog = {
        GameCubeButtons.DPAD_LEFT: 255,
        GameCubeButtons.DPAD_DOWN: 255,
        GameCubeButtons.DPAD_RIGHT: 255,
        GameCubeButtons.DPAD_UP: 255,
        GameCubeButtons.X: 255,
        GameCubeButtons.A: 255,
        GameCubeButtons.B: 255,
        GameCubeButtons.Y: 255,
        GameCubeButtons.R: 255,
        GameCubeButtons.L: 255,
        GameCubeButtons.Z: 255,
    }
    prefix = PAD_PREFIX.pack(
        PAD_DATA_TYPE,
        pad_id,
        2,
        3,
        1,
        bytes((2, 0, 0, 0, 0, pad_id)),
        5,
        1,
        packet_counter,
        states1,
        states2,
        0,
        0,
        left_x,
        left_y,
        128,
        128,
    )[4:]
    ordered = (
        GameCubeButtons.DPAD_LEFT,
        GameCubeButtons.DPAD_DOWN,
        GameCubeButtons.DPAD_RIGHT,
        GameCubeButtons.DPAD_UP,
        GameCubeButtons.X,
        GameCubeButtons.A,
        GameCubeButtons.B,
        GameCubeButtons.Y,
        GameCubeButtons.R,
        GameCubeButtons.L,
        GameCubeButtons.Z,
        GameCubeButtons.Z,
    )
    analog_bytes = bytes(analog.get(button, 0) if buttons & button else 0 for button in ordered)
    touch_and_motion = bytes(12) + bytes(8) + bytes(24)
    return _packet(PAD_DATA_TYPE, prefix + analog_bytes + touch_and_motion, server_uid)


@dataclass
class DsuVirtualPad:
    pad_id: int = 0
    state: ControllerState = field(default_factory=ControllerState)
    packet_counter: int = 0

    def update(self, state: ControllerState) -> None:
        self.state = state
        self.packet_counter = (self.packet_counter + 1) & 0xFFFFFFFF


class DsuServerProtocol(asyncio.DatagramProtocol):
    def __init__(
        self, pads: dict[int, DsuVirtualPad] | None = None, *, max_subscribers: int = 32
    ) -> None:
        self.pads = pads or {0: DsuVirtualPad()}
        self.server_uid = secrets.randbits(32)
        self.transport: asyncio.DatagramTransport | None = None
        self.subscribers: dict[tuple[str, int], set[int]] = {}
        self.max_subscribers = max_subscribers
        self._closed: asyncio.Future | None = None

    def connection_made(self, transport) -> None:
        self.transport = transport
        self._closed = asyncio.get_running_loop().create_future()

    def connection_lost(self, exc) -> None:
        if self._closed is not None and not self._closed.done():
            self._closed.set_result(None)

    async def wait_closed(self, timeout: float = 1.0) -> None:
        if self._closed is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._closed), timeout)
            except TimeoutError:
                return

    def datagram_received(self, data: bytes, address) -> None:
        try:
            message_type, payload, _ = parse_request(data)
        except DsuProtocolError:
            return
        if self.transport is None:
            return
        if message_type == VERSION_TYPE:
            self.transport.sendto(
                _packet(VERSION_TYPE, struct.pack("<H2x", PROTOCOL_VERSION), self.server_uid),
                address,
            )
        elif message_type == PORTS_TYPE and len(payload) >= 4:
            count = min(struct.unpack_from("<I", payload)[0], 4)
            for pad_id in payload[4 : 4 + count]:
                if pad_id in self.pads:
                    self.transport.sendto(port_info_packet(pad_id, self.server_uid), address)
        elif message_type == PAD_DATA_TYPE and len(payload) >= 8:
            flags, pad_id = struct.unpack_from("<BB", payload)
            if flags in (0, 1) and pad_id in self.pads:
                if address not in self.subscribers and len(self.subscribers) >= self.max_subscribers:
                    return
                self.subscribers.setdefault(address, set()).add(pad_id)
                self.send_pad(address, pad_id)

    def send_pad(self, address, pad_id: int) -> None:
        if self.transport is None:
            return
        pad = self.pads[pad_id]
        self.transport.sendto(
            pad_data_packet(pad_id, pad.state, pad.packet_counter, self.server_uid), address
        )

    def broadcast(self, pad_id: int) -> None:
        for address, pad_ids in tuple(self.subscribers.items()):
            if pad_id in pad_ids:
                self.send_pad(address, pad_id)


async def create_dsu_server(
    host: str = "127.0.0.1", port: int = DEFAULT_PORT
) -> tuple[asyncio.DatagramTransport, DsuServerProtocol]:
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        DsuServerProtocol, local_addr=(host, port)
    )
    return transport, protocol
