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


if __name__ == "__main__":
    unittest.main()
