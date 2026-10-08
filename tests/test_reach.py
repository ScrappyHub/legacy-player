import asyncio
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import reach, servercode
from launcher.app import AppError
from tests.test_app_actions import make_app


class ReachTests(unittest.TestCase):
    def test_only_public_ipv6_counts(self):
        self.assertTrue(reach._global("2001:4860:4860::8888"))
        self.assertFalse(reach._global("fe80::1"))
        self.assertFalse(reach._global("fd12:3456::1"))
        self.assertFalse(reach._global("::1"))
        self.assertFalse(reach._global("192.168.1.2"))

    def test_stable_address_preferred_over_the_outgoing_temporary_one(self):
        with mock.patch("launcher.reach._outbound_ipv6", return_value="2a00:1450:4001:81a::aaaa"), \
                mock.patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("2a00:1450:4001:81a::aaaa", 0, 0, 0)), (0, 0, 0, "", ("2a00:1450:4001:81a::5", 0, 0, 0))]):
            out = reach.global_ipv6()
        self.assertEqual((out["available"], out["address"], out["stable"]), (True, "2a00:1450:4001:81a::5", True))

    def test_no_ipv6(self):
        with mock.patch("launcher.reach._outbound_ipv6", return_value=""):
            self.assertFalse(reach.global_ipv6()["available"])

    def test_plan_lists_every_route(self):
        routes = reach.plan({"available": True, "address": "2001:db8::1", "stable": True}, "not_reachable", False)
        self.assertEqual(["shared", "ipv6", "router"], [r["key"] for r in routes])
        self.assertEqual([False, True, False], [r["ok"] for r in routes])

    def test_use_ipv6_sets_the_address_and_makes_a_long_code(self):
        app, _ = make_app()
        with mock.patch("launcher.reach.global_ipv6", return_value={"available": False, "address": "", "stable": False}):
            with self.assertRaises(AppError):
                app.api_server_use_ipv6({})
        with mock.patch("launcher.reach.global_ipv6", return_value={"available": True, "address": "2001:db8::5", "stable": True}):
            out = app.api_server_use_ipv6({})
            info = app.api_reach({})
        self.assertEqual(out["address"], "2001:db8::5")
        self.assertEqual(app.catalog.settings()["server_public_address"], "2001:db8::5")
        self.assertTrue(info["using_ipv6"])
        code = servercode.encode("2001:db8::5", 8765, "ab" * 32, "cd" * 5)
        self.assertEqual(servercode.decode(code)["host"], "2001:db8::5")

    def test_vps_script_and_docs(self):
        root = Path(__file__).resolve().parent.parent
        script = (root / "deploy" / "setup-vps.sh").read_text(encoding="utf-8")
        for needle in ("set -euo pipefail", "systemctl enable", "server.cli code", "8765"):
            self.assertIn(needle, script)

    def test_shared_server_listens_on_ipv6_too(self):
        try:
            probe = socket.socket(socket.AF_INET6)
            probe.bind(("::1", 0))
            probe.close()
        except OSError:
            self.skipTest("IPv6 loopback unavailable")
        from server.api import json_server
        state = Path(tempfile.mkdtemp())
        free = socket.socket()
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()

        async def run():
            task = asyncio.create_task(json_server.serve("0.0.0.0", port, state / "replays", state_dir=state))
            reached = []
            for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
                for _ in range(40):
                    try:
                        _, writer = await asyncio.open_connection(host, port)
                        writer.close()
                        reached.append(host)
                        break
                    except OSError:
                        await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except BaseException:
                pass
            return reached

        self.assertEqual(["127.0.0.1", "::1"], asyncio.run(run()))

if __name__ == "__main__":
    unittest.main()
