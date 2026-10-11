import unittest

from adapters.dolphin.bridge import DolphinBridgeError, DolphinDsuBridge
from adapters.dolphin.dsu_protocol import DsuServerProtocol


class RecordingProtocol(DsuServerProtocol):
    def __init__(self):
        super().__init__()
        self.broadcasts = []

    def broadcast(self, pad_id):
        self.broadcasts.append(pad_id)


class DolphinBridgeTests(unittest.TestCase):
    def test_applies_complete_bundle_to_virtual_pads(self):
        bridge = DolphinDsuBridge({"host": 0, "peer": 1})
        protocol = RecordingProtocol()
        bridge.apply_bundle(
            {
                "frame": 0,
                "inputs": [
                    {"participant_id": "host", "buttons": 1, "stick_x": 2, "stick_y": 3},
                    {"participant_id": "peer", "buttons": 4, "stick_x": 5, "stick_y": 6},
                ],
            },
            protocol,
        )
        self.assertEqual(0, bridge.last_frame)
        self.assertEqual(1, bridge.pads[0].state.buttons)
        self.assertEqual(4, bridge.pads[1].state.buttons)
        self.assertEqual([0, 1], protocol.broadcasts)
        self.assertFalse(bridge.supports_frame_control)

    def test_rejects_missing_or_non_contiguous_frames(self):
        bridge = DolphinDsuBridge({"host": 0, "peer": 1})
        protocol = RecordingProtocol()
        with self.assertRaisesRegex(DolphinBridgeError, "non-contiguous"):
            bridge.apply_bundle({"frame": 1, "inputs": []}, protocol)
        with self.assertRaisesRegex(DolphinBridgeError, "missing participants"):
            bridge.apply_bundle(
                {"frame": 0, "inputs": [{"participant_id": "host", "buttons": 0}]},
                protocol,
            )


class PersistentClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_polls_share_one_connection_and_reconnect_when_it_drops(self):
        import asyncio
        import json
        from runtime.client import CoordinationClient
        from runtime.client.coordination import REQUEST_LIMIT_ERROR
        seen = {"connections": 0}

        async def handle(reader, writer):
            seen["connections"] += 1
            served = 0
            while line := await reader.readline():
                served += 1
                if served > 3:                               # like the real server: a request limit per connection
                    writer.write(json.dumps({"ok": False, "error": REQUEST_LIMIT_ERROR}).encode() + b"\n")
                    await writer.drain()
                    break
                writer.write(json.dumps({"ok": True, "result": json.loads(line)}).encode() + b"\n")
                await writer.drain()
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        client = CoordinationClient("127.0.0.1", port, persistent=True)
        try:
            for i in range(3):
                self.assertEqual({"i": i}, await client.request({"i": i}))
            self.assertEqual(1, seen["connections"])
            self.assertEqual({"i": 3}, await client.request({"i": 3}))     # limit hit: one fresh connection, same answer
            self.assertEqual(2, seen["connections"])
            await client._writer.drain()
            client._writer.transport.abort()                                # connection dies under us
            self.assertEqual({"i": 4}, await client.request({"i": 4}))
            self.assertEqual(3, seen["connections"])
        finally:
            await client.close()
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
