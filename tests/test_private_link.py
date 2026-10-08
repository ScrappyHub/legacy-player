import subprocess
import unittest
from unittest import mock

from adapters.dolphin.netplay_guide import steps
from launcher import privatelink
from launcher.app import AppError


class PrivateLinkTests(unittest.TestCase):
    def test_address_range(self):
        self.assertTrue(privatelink.is_private_link_address("100.101.102.103"))
        self.assertFalse(privatelink.is_private_link_address("192.168.1.5"))
        self.assertFalse(privatelink.is_private_link_address("8.8.8.8"))
        self.assertFalse(privatelink.is_private_link_address("not an address"))

    def test_not_installed(self):
        with mock.patch("launcher.privatelink.find_tailscale", return_value=None):
            st = privatelink.status()
        self.assertFalse(st["installed"])
        self.assertIsNone(st["address"])

    def test_running_reads_the_address(self):
        done = subprocess.CompletedProcess([], 0, stdout="100.64.1.2\n", stderr="")
        with mock.patch("launcher.privatelink.find_tailscale", return_value="ts"), mock.patch("subprocess.run", return_value=done):
            st = privatelink.status()
        self.assertEqual((st["installed"], st["running"], st["address"]), (True, True, "100.64.1.2"))

    def test_installed_but_signed_out_or_broken(self):
        bad = subprocess.CompletedProcess([], 1, stdout="", stderr="Logged out")
        with mock.patch("launcher.privatelink.find_tailscale", return_value="ts"), mock.patch("subprocess.run", return_value=bad):
            self.assertFalse(privatelink.status()["running"])
        with mock.patch("launcher.privatelink.find_tailscale", return_value="ts"), mock.patch("subprocess.run", side_effect=OSError):
            self.assertFalse(privatelink.status()["running"])

    def test_steps_mention_tailscale_and_no_port_forward(self):
        host = " ".join(steps("host", mode="direct", address="100.64.1.2", port=2626, private=True))
        self.assertIn("Tailscale", host)
        self.assertNotIn("forwarded", host)
        guest = " ".join(steps("guest", mode="direct", address="100.64.1.2", port=2626, private=True))
        self.assertIn("Tailscale", guest)
        plain = " ".join(steps("guest", mode="direct", address="1.2.3.4", port=2626))
        self.assertNotIn("Tailscale", plain)


class PrivateLaunchTests(unittest.TestCase):
    def test_host_refuses_clearly_without_tailscale(self):
        from tests.test_app_actions import make_app
        app, _ = make_app()
        app.catalog.settings()  # exists
        app.catalog.data["settings"] = {**app.catalog.settings(), "allow_direct_connections": True}
        with mock.patch("launcher.privatelink.find_tailscale", return_value=None):
            with self.assertRaises(AppError) as cm:
                app._launch_dolphin({"role": "host"}, {"path": "x.iso"}, {"exe": "d.exe"}, {"mode": "private", "expose_address": True})
        self.assertIn("Tailscale", str(cm.exception))



class AutomaticChoiceTests(unittest.TestCase):
    def setUp(self):
        from tests.test_app_actions import make_app
        self.app, _ = make_app()
        self.room = {"role": "host", "me": "h", "session": {"participants": {"h": {}, "g": {}}},
                     "stats": {"people": {"g": {"private_address": "100.64.0.9"}}}}
        self.up = {"installed": True, "running": True, "address": "100.64.0.1"}

    def pick(self, on=True, link=None, reach=True, room=None):
        self.app.catalog.data["settings"] = {**self.app.catalog.settings(), "use_private_link": on}
        with mock.patch("launcher.privatelink.status", return_value=link or self.up), \
             mock.patch("launcher.privatelink.can_reach", return_value=reach):
            return self.app._pick_connection(room or self.room)

    def test_everyone_ready_uses_private(self):
        self.assertEqual(self.pick(), ("private", None))

    def test_each_failure_falls_back_with_a_reason(self):
        for kwargs in ({"on": False}, {"link": {"installed": False, "running": False, "address": None}}, {"reach": False},
                       {"room": {**self.room, "stats": {"people": {"g": {}}}}},
                       {"room": {**self.room, "session": {"participants": {"h": {}}}}}):
            mode, note = self.pick(**kwargs)
            self.assertEqual(mode, "traversal", kwargs)
            self.assertTrue(note)

    def test_guest_never_picks(self):
        self.assertEqual(self.app._pick_connection({**self.room, "role": "guest"}), ("traversal", None))

    def test_server_only_accepts_tailscale_addresses(self):
        from server.lobby.service import LobbyError, LobbyService
        svc = LobbyService.__new__(LobbyService)
        svc._authorized = lambda r: (mock.Mock(session_id="s"), "p")
        svc.stats, svc.established, svc.clock = {}, set(), lambda: 1.0
        self.assertTrue(svc.report_stats({"private_address": "100.70.1.1"})["ok"])
        with self.assertRaises(LobbyError):
            svc.report_stats({"private_address": "8.8.8.8"})



class ServerTailscaleTests(unittest.TestCase):
    def test_sets_public_address_only_when_tailscale_is_up(self):
        from tests.test_app_actions import make_app
        app, _ = make_app()
        with mock.patch("launcher.privatelink.status", return_value={"installed": False, "running": False, "address": None}):
            with self.assertRaises(AppError):
                app.api_server_use_tailscale({})
        with mock.patch("launcher.privatelink.status", return_value={"installed": True, "running": False, "address": None}):
            with self.assertRaises(AppError):
                app.api_server_use_tailscale({})
        with mock.patch("launcher.privatelink.status", return_value={"installed": True, "running": True, "address": "100.64.5.6"}):
            out = app.api_server_use_tailscale({})
        self.assertEqual(out["address"], "100.64.5.6")
        self.assertEqual(app.catalog.settings()["server_public_address"], "100.64.5.6")

    def test_a_tailscale_address_makes_a_short_code(self):
        from launcher import servercode
        code = servercode.encode("100.64.5.6", 8765, "ab" * 32, "cd" * 5)
        self.assertTrue(code.startswith("LP-"))
        self.assertEqual(servercode.decode(code)["host"], "100.64.5.6")


class TailscaleSetupTests(unittest.TestCase):
    def setUp(self):
        from tests.test_app_actions import make_app
        self.app, _ = make_app()

    def test_install_needs_downloads_on_and_a_yes(self):
        with self.assertRaises(AppError):
            self.app.api_tailscale({"action": "install", "confirm": True})            # downloads are off by default
        self.app.catalog.set_setting("allow_internet", True)
        with self.assertRaises(AppError):
            self.app.api_tailscale({"action": "install"})                            # no confirmation
        with mock.patch("launcher.privatelink.start_install", return_value={"state": "installing", "message": ""}) as start, \
             mock.patch("launcher.privatelink.status", return_value={"installed": False, "running": False, "address": None, "download_page": "x"}):
            out = self.app.api_tailscale({"action": "install", "confirm": True})
        start.assert_called_once()
        self.assertIn("install", out)

    def test_login_needs_it_installed(self):
        with mock.patch("launcher.privatelink.find_tailscale", return_value=None):
            with self.assertRaises(AppError):
                self.app.api_tailscale({"action": "login"})
        with self.assertRaises(AppError):
            self.app.api_tailscale({"action": "rm -rf"})

    def test_install_without_winget_explains(self):
        privatelink.INSTALL.update(state="idle", message="")
        with mock.patch("launcher.privatelink.find_tailscale", return_value=None), mock.patch("launcher.privatelink.winget_path", return_value=None):
            out = privatelink.start_install()
        self.assertEqual(out["state"], "error")
        self.assertIn("tailscale.com/download", out["message"])
        privatelink.INSTALL.update(state="idle", message="")

    def test_install_runs_only_the_official_package(self):
        privatelink.INSTALL.update(state="idle", message="")
        seen = {}
        done = subprocess.CompletedProcess([], 0, stdout="", stderr="")

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            return done
        calls = iter([None, "ts"])
        with mock.patch("launcher.privatelink.find_tailscale", side_effect=lambda: next(calls, "ts")), \
             mock.patch("launcher.privatelink.winget_path", return_value="winget"), mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch("threading.Thread") as thread:
            privatelink.start_install()
            thread.call_args.kwargs["target"]()
        self.assertIn("Tailscale.Tailscale", seen["cmd"])
        self.assertEqual(privatelink.INSTALL["state"], "done")
        privatelink.INSTALL.update(state="idle", message="")
