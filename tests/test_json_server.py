import asyncio
import json
import unittest

from server.api.json_server import handle_client
from server.lobby import LobbyService


class JsonServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = LobbyService()
        self.server = await asyncio.start_server(
            lambda reader, writer: handle_client(reader, writer, self.service),
            "127.0.0.1",
            0,
        )
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def request(self, payload):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(json.dumps(payload).encode() + b"\n")
        await writer.drain()
        response = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        return response

    async def raw_request(self, data):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        writer.write(data)
        await writer.drain()
        response = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        return response

    async def test_create_session_over_json_lines(self):
        response = await self.request(
            {
                "operation": "create",
                "participant_id": "host",
                "profile": {"game_id": "GMPE01", "region": "USA"},
                "adapter_id": "dolphin",
                "game_pack_id": "mario_party_4",
            }
        )
        self.assertTrue(response["ok"])
        self.assertEqual("created", response["result"]["session"]["state"])
        self.assertIn("credential", response["result"])

    async def test_invalid_operation_returns_structured_error(self):
        response = await self.request({"operation": "destroy-everything"})
        self.assertFalse(response["ok"])
        self.assertIn("unsupported operation", response["error"])

    async def test_malformed_and_oversized_requests_fail_cleanly(self):
        malformed = await self.raw_request(b"not-json\n")
        self.assertFalse(malformed["ok"])
        oversized = await self.raw_request(b'{"padding":"' + (b"x" * 70_000) + b'"}\n')
        self.assertFalse(oversized["ok"])
        self.assertIn("too large", oversized["error"])


if __name__ == "__main__":
    unittest.main()
