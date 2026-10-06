import unittest

from adapters.controller import ControllerState
from adapters.dolphin.deterministic_bridge import DeterministicDolphinBridge
from runtime.frame_control import ConformanceEngine, FrameControlClient, FrameControlError, serve_conformance


TOKEN = "t" * 48


class FrameControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server, self.engine = await serve_conformance(TOKEN, {0, 1})
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def test_authentication_and_capabilities(self):
        bad = FrameControlClient("127.0.0.1", self.port, "x" * 48, "session")
        with self.assertRaisesRegex(FrameControlError, "authentication"):
            await bad.connect()
        await bad.close()
        wrong_session = FrameControlClient("127.0.0.1", self.port, TOKEN, "wrong")
        with self.assertRaisesRegex(FrameControlError, "session mismatch"):
            await wrong_session.connect()
        await wrong_session.close()
        client = FrameControlClient("127.0.0.1", self.port, TOKEN, "session")
        hello = await client.connect()
        self.assertEqual([0, 1], hello["required_slots"])
        self.assertIn("pause", hello["capabilities"])
        await client.close()

    async def test_pause_inject_advance_order_is_enforced(self):
        client = FrameControlClient("127.0.0.1", self.port, TOKEN, "session")
        await client.connect()
        try:
            await client.pause(0)
            await client.inject(0, 0, ControllerState())
            with self.assertRaisesRegex(FrameControlError, "missing controller slots"):
                await client.advance(0)
            with self.assertRaisesRegex(FrameControlError, "duplicate input"):
                await client.inject(0, 0, ControllerState())
        finally:
            await client.close()

    async def test_deterministic_bridge_runs_contiguous_frames(self):
        client = FrameControlClient("127.0.0.1", self.port, TOKEN, "session")
        await client.connect()
        bridge = DeterministicDolphinBridge(client, {"host": 0, "peer": 1})
        try:
            hashes = []
            for frame in range(30):
                hashes.append(
                    await bridge.apply_bundle(
                        {
                            "frame": frame,
                            "inputs": [
                                {"participant_id": "host", "buttons": frame & 1},
                                {"participant_id": "peer", "buttons": (frame + 1) & 1},
                            ],
                        }
                    )
                )
            self.assertEqual(30, self.engine.current_frame)
            self.assertEqual(30, len(set(hashes)))
        finally:
            await client.close()

    def test_engine_survives_long_contiguous_run(self):
        engine = ConformanceEngine(frozenset({0, 1}))
        for frame in range(5_000):
            engine.pause(frame)
            engine.inject(frame, 0, ControllerState(buttons=frame & 1))
            engine.inject(frame, 1, ControllerState(buttons=(frame + 1) & 1))
            engine.advance(frame)
        self.assertEqual(5_000, engine.current_frame)
        self.assertEqual(64, len(engine.state_hash(4_999)))


if __name__ == "__main__":
    unittest.main()
