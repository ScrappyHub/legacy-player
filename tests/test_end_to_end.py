import asyncio
import binascii
import json
import socket
import struct
import unittest

from adapters.dolphin.bridge import DolphinDsuBridge
from adapters.dolphin.dsu_protocol import (
    CLIENT_MAGIC,
    HEADER,
    PAD_DATA_TYPE,
    PROTOCOL_VERSION,
    create_dsu_server,
)
from runtime.client import CoordinationClient
from server.api.json_server import handle_client
from server.lobby import LobbyService


def dsu_request(message_type, payload=b""):
    body = struct.pack("<I", message_type) + payload
    packet = bytearray(HEADER.pack(CLIENT_MAGIC, PROTOCOL_VERSION, len(body), 0, 42) + body)
    struct.pack_into("<I", packet, 8, binascii.crc32(packet) & 0xFFFFFFFF)
    return bytes(packet)


class EndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_to_lockstep_to_dolphin_virtual_pad(self):
        service = LobbyService()
        tcp_server = await asyncio.start_server(
            lambda reader, writer: handle_client(reader, writer, service), "127.0.0.1", 0
        )
        tcp_port = tcp_server.sockets[0].getsockname()[1]
        client = CoordinationClient("127.0.0.1", tcp_port)
        dsu_transport = None
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setblocking(False)
        try:
            created = await client.request(
                {
                    "operation": "create",
                    "participant_id": "host",
                    "profile": {"game_id": "GMPE01", "region": "USA"},
                    "adapter_id": "dolphin-dsu",
                    "game_pack_id": "mario_party_4",
                }
            )
            session_id = created["session"]["session_id"]
            joined = await client.request(
                {
                    "operation": "join",
                    "session_id": session_id,
                    "join_code": created["join_code"],
                    "participant_id": "peer",
                    "profile": {"game_id": "GMPE01", "region": "USA"},
                }
            )
            host_auth = {
                "session_id": session_id,
                "participant_id": "host",
                "credential": created["credential"],
            }
            peer_auth = {
                "session_id": session_id,
                "participant_id": "peer",
                "credential": joined["credential"],
            }
            await client.request({"operation": "validate", **host_auth})
            await client.request({"operation": "ready", **host_auth})
            await client.request({"operation": "ready", **peer_auth})
            await client.request(
                {"operation": "input", **host_auth, "frame": 0, "buttons": 1}
            )
            released = await client.request(
                {"operation": "input", **peer_auth, "frame": 0, "buttons": 2}
            )
            self.assertTrue(released["released"])

            bridge = DolphinDsuBridge({"host": 0, "peer": 1})
            dsu_transport, protocol = await create_dsu_server("127.0.0.1", 0)
            protocol.pads = bridge.pads
            dsu_address = dsu_transport.get_extra_info("sockname")
            loop = asyncio.get_running_loop()
            register = struct.pack("<BB6s", 1, 0, bytes(6))
            await loop.sock_sendto(udp, dsu_request(PAD_DATA_TYPE, register), dsu_address)
            await asyncio.wait_for(loop.sock_recvfrom(udp, 1024), 1)

            polled = await client.request({"operation": "poll", **host_auth, "after_frame": -1})
            bridge.apply_bundle(polled["bundles"][0], protocol)
            packet, _ = await asyncio.wait_for(loop.sock_recvfrom(udp, 1024), 1)
            self.assertEqual(PAD_DATA_TYPE, struct.unpack_from("<I", packet, HEADER.size)[0])
            self.assertEqual(1, bridge.pads[0].state.buttons)
            self.assertEqual(2, bridge.pads[1].state.buttons)
        finally:
            udp.close()
            if dsu_transport is not None:
                dsu_transport.abort()
                await protocol.wait_closed()
            tcp_server.close()
            await tcp_server.wait_closed()


if __name__ == "__main__":
    unittest.main()
