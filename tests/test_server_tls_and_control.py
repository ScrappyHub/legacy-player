import json
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from launcher.app import AppError, LauncherApp
from launcher.lobby_client import LobbyClient, LobbyClientError
from server import selfsigned


class SelfSignedTests(unittest.TestCase):
    def test_certificate_loads_and_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            cert, key, fp = selfsigned.ensure_certificate(Path(tmp) / "tls")
            again = selfsigned.ensure_certificate(Path(tmp) / "tls")
            self.assertEqual(fp, again[2])  # stable across runs
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            self.assertEqual(64, len(fp))
            self.assertRegex(selfsigned.pretty_fingerprint(fp), r"^[0-9A-F]{4}(-[0-9A-F]{4}){7}$")
            if sys.platform != "win32":
                self.assertEqual(0o600, (Path(tmp) / "tls" / "key.pem").stat().st_mode & 0o777)


class InAppServerTests(unittest.TestCase):
    """The server started from the app: plain on loopback, TLS + fingerprint when shared."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = LauncherApp(Path(self.tmp.name) / "data")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.app.catalog.set_setting("server_port", self.port)

    def tearDown(self):
        try:
            self.app.api_server_control({"action": "stop"})
        except AppError:
            pass
        self.tmp.cleanup()

    def test_shared_server_is_tls_with_pinned_fingerprint_and_limits(self):
        self.app.catalog.set_setting("server_max_players", 3)
        self.app.catalog.set_setting("server_max_waiting", 0)
        out = self.app.api_server_control({"action": "start", "share": True})
        self.assertTrue(out["running"], out)
        self.assertRegex(out["fingerprint"], r"^[0-9A-F]{4}(-[0-9A-F]{4}){7}$")
        self.assertTrue(self.app.catalog.settings()["server_tls"])
        self.assertEqual(out["fingerprint"], self.app.catalog.settings()["server_fingerprint"])
        # plaintext client is refused; pinned TLS client works; wrong pin is refused
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as raw:
            raw.sendall(b'{"operation":"browse"}\n')
            self.assertNotIn(b'"ok": true', raw.recv(200) or b"")
        good = LobbyClient("127.0.0.1", self.port, tls=True, fingerprint=out["fingerprint"])
        listing = good.call({"operation": "browse"})
        self.assertEqual(3, listing["limits"]["max_players_per_room"])
        self.assertEqual(0, listing["limits"]["max_waiting_per_room"])
        bad = LobbyClient("127.0.0.1", self.port, tls=True, fingerprint="DEAD-BEEF-DEAD-BEEF-DEAD-BEEF-DEAD-BEEF")
        with self.assertRaisesRegex(LobbyClientError, "does not match"):
            bad.call({"operation": "browse"})
        self.assertTrue(self.app.api_server_status({})["online"])  # the app itself can still talk to it
        status = self.app.api_server_control({"action": "status"})
        self.assertTrue(status["running"])

    def test_window_lifetime_rules(self):
        app = self.app
        self.assertFalse(app.should_exit(100.0, started=50.0))
        self.assertTrue(app.should_exit(300.0, started=50.0))       # nobody ever opened the page
        app.api_ping({})
        self.assertFalse(app.should_exit(time.time() + 60))
        self.assertTrue(app.should_exit(time.time() + 200))           # page stopped pinging
        app.api_bye({})
        self.assertTrue(app.should_exit(time.time() + 10))            # window closed


if __name__ == "__main__":
    unittest.main()
