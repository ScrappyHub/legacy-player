import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import firewall
from launcher.app import LauncherApp

BLOCKED = {"state": "not_reachable", "external_ip": "100.70.0.1", "kind": "cgnat", "message": "Shared address."}
MAPPED = {"state": "mapped", "external_ip": "93.184.216.34", "kind": "public", "location": "http://r/x", "port": 8765, "message": "Opened."}


class FallbackTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict("os.environ", {"LEGACY_PLAYER_NO_BACKGROUND": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = LauncherApp(Path(self.tmp.name) / "data", roots=[])
        self.connects = []
        self.app.api_server_connect = lambda body: (self.connects.append(body), {"connected": True})[1]

    def test_blocked_router_moves_to_shared_server(self):
        self.app.catalog.set_setting("fallback_server_code", "LP-TEST")
        with mock.patch("launcher.portmap.open_port", return_value=BLOCKED):
            r = self.app._manage_router("start", 0, True, 8765)
        self.assertTrue(r["fallback"])
        self.assertEqual([{"code": "LP-TEST"}], self.connects)
        self.assertTrue(self.app.fallback_active)

    def test_stop_returns_to_own_server(self):
        self.app.fallback_active = True
        self.app._manage_router("stop", 0, True, 8765)
        self.assertEqual([{"local": True}], self.connects)
        self.assertFalse(self.app.fallback_active)

    def test_working_router_never_uses_fallback(self):
        self.app.catalog.set_setting("fallback_server_code", "LP-TEST")
        with mock.patch("launcher.portmap.open_port", return_value=MAPPED):
            r = self.app._manage_router("start", 0, True, 8765)
        self.assertEqual("mapped", r["state"])
        self.assertEqual([], self.connects)

    def test_no_shared_server_set_says_so_plainly(self):
        with mock.patch("launcher.portmap.open_port", return_value=BLOCKED):
            r = self.app._manage_router("start", 0, True, 8765)
        self.assertEqual("not_reachable", r["state"])
        self.assertEqual([], self.connects)

    def test_router_test_closes_what_it_opened(self):
        with mock.patch("launcher.portmap.open_port", return_value=MAPPED), mock.patch("launcher.portmap.close_port") as close:
            self.app.api_router_test({})
        close.assert_called_once()


class FirewallTests(unittest.TestCase):
    def test_rule_is_for_every_network_kind(self):
        args = firewall.rule_args(8765)
        self.assertIn("profile=any", args)
        self.assertIn("localport=8765", args)

    def test_elevates_when_not_admin(self):
        calls = []

        def run(cmd, timeout=15.0):
            calls.append(cmd)
            out = mock.Mock(stdout="Rule Name: Legacy Player server\nAction: Allow\nLocalPort: 8765", stderr="")
            out.returncode = 1 if cmd[0] == "netsh" and "add" in cmd else 0
            return out
        with mock.patch("launcher.firewall.supported", return_value=True):
            r = firewall.allow(8765, run)
        self.assertTrue(r["allowed"])
        self.assertTrue(any(c[0] == "powershell" and "RunAs" in c[-1] for c in calls))


if __name__ == "__main__":
    unittest.main()
