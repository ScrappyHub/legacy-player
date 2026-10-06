import binascii
import asyncio
import socket
import struct
import unittest

from adapters.controller import ControllerState
from adapters.dolphin.dsu_protocol import (
    CLIENT_MAGIC,
    HEADER,
    PAD_DATA_TYPE,
    PROTOCOL_VERSION,
    SERVER_MAGIC,
    VERSION_TYPE,
    DsuProtocolError,
    GameCubeButtons,
    pad_data_packet,
    parse_request,
    create_dsu_server,
)


def request_packet(message_type, payload=b"", uid=7):
    body = struct.pack("<I", message_type) + payload
    packet = bytearray(HEADER.pack(CLIENT_MAGIC, PROTOCOL_VERSION, len(body), 0, uid) + body)
    struct.pack_into("<I", packet, 8, binascii.crc32(packet) & 0xFFFFFFFF)
    return bytes(packet)


class DsuProtocolTests(unittest.TestCase):
    def test_request_validation_checks_crc(self):
        packet = request_packet(VERSION_TYPE)
        message_type, payload, uid = parse_request(packet)
        self.assertEqual(VERSION_TYPE, message_type)
        self.assertEqual(b"", payload)
        self.assertEqual(7, uid)
        corrupted = bytearray(packet)
        corrupted[-1] ^= 1
        with self.assertRaisesRegex(DsuProtocolError, "CRC"):
            parse_request(bytes(corrupted))

    def test_pad_packet_matches_dolphin_wire_shape(self):
        packet = pad_data_packet(
            0,
            ControllerState(
                buttons=int(GameCubeButtons.A | GameCubeButtons.START),
                stick_x=127,
                stick_y=-128,
            ),
            3,
            9,
        )
        magic, version, body_length, crc, uid = HEADER.unpack_from(packet)
        self.assertEqual(SERVER_MAGIC, magic)
        self.assertEqual(PROTOCOL_VERSION, version)
        self.assertEqual(len(packet) - HEADER.size, body_length)
        self.assertEqual(9, uid)
        checked = bytearray(packet)
        struct.pack_into("<I", checked, 8, 0)
        self.assertEqual(crc, binascii.crc32(checked) & 0xFFFFFFFF)
        self.assertEqual(PAD_DATA_TYPE, struct.unpack_from("<I", packet, HEADER.size)[0])
        self.assertEqual(100, len(packet))


class DsuNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_virtual_pad_server_answers_version_request(self):
        transport, protocol = await create_dsu_server("127.0.0.1", 0)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            address = transport.get_extra_info("sockname")
            loop = asyncio.get_running_loop()
            await loop.sock_sendto(sock, request_packet(VERSION_TYPE), address)
            response, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 1024), 1)
            self.assertEqual(SERVER_MAGIC, response[:4])
            self.assertEqual(VERSION_TYPE, struct.unpack_from("<I", response, HEADER.size)[0])
        finally:
            sock.close()
            transport.abort()
            await protocol.wait_closed()


if __name__ == "__main__":
    unittest.main()
