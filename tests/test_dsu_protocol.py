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


    def test_packet_fields_match_the_dolphin_profile(self):
        """Decode the bytes the way Dolphin's DualShockUDPClient does (PadDataResponse) and check every GameCube button
        lands on the DSU input the managed Dolphin profile reads for it."""
        from adapters.dolphin.configurator import PAD_TEMPLATE
        # Dolphin input name -> byte offset in the packet (header 16 + type 4 + PadDataResponse fields)
        offsets = {"Pad W": 44, "Pad S": 45, "Pad E": 46, "Pad N": 47, "Square": 48, "Cross": 49, "Circle": 50, "Triangle": 51,
                   "R1": 52, "L1": 53, "R2": 54, "L2": 55}
        profile = {}
        for line in PAD_TEMPLATE.format(number=1, index=0).splitlines():
            key, sep, value = line.partition(" = ")
            if sep:
                profile[key] = value.strip("`")
        expected = {
            GameCubeButtons.A: ["Buttons/A"], GameCubeButtons.B: ["Buttons/B"], GameCubeButtons.X: ["Buttons/X"],
            GameCubeButtons.Y: ["Buttons/Y"], GameCubeButtons.Z: ["Buttons/Z"],
            GameCubeButtons.L: ["Triggers/L", "Triggers/L-Analog"], GameCubeButtons.R: ["Triggers/R", "Triggers/R-Analog"],
            GameCubeButtons.DPAD_UP: ["D-Pad/Up"], GameCubeButtons.DPAD_DOWN: ["D-Pad/Down"],
            GameCubeButtons.DPAD_LEFT: ["D-Pad/Left"], GameCubeButtons.DPAD_RIGHT: ["D-Pad/Right"],
        }
        for button, controls in expected.items():
            packet = pad_data_packet(0, ControllerState(buttons=int(button)), 1, 1)
            pressed = {name for name, at in offsets.items() if packet[at] == 255}
            idle = {name for name, at in offsets.items() if packet[at] == 0}
            self.assertEqual(set(offsets), pressed | idle, button)
            for control in controls:
                self.assertEqual({profile[control]}, pressed, f"{button!r} -> {control} reads {profile[control]}")
        start = pad_data_packet(0, ControllerState(buttons=int(GameCubeButtons.START)), 1, 1)
        self.assertEqual("Options", profile["Buttons/Start"])
        self.assertEqual(0x08, start[36])                            # button_states1 Options bit
        z = pad_data_packet(0, ControllerState(buttons=int(GameCubeButtons.Z)), 1, 1)
        self.assertEqual(0x08, z[37])                                # button_states2 R1 bit, for other DSU clients
        idle = pad_data_packet(0, ControllerState(buttons=0), 1, 1)
        self.assertEqual(bytes(12), idle[44:56])
        self.assertEqual((0, 0), (idle[36], idle[37]))
        self.assertEqual((128, 128), (idle[40], idle[41]))           # sticks centred, right before the analog bytes


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
