import pathlib
import unittest

from launcher.lobby_client import LobbyClient, LobbyClientError

UI = pathlib.Path(__file__).resolve().parent.parent / "launcher" / "ui" / "index.html"


class AddressPrivacyTests(unittest.TestCase):
    def test_errors_about_a_friends_server_never_print_its_address(self):
        client = LobbyClient("203.0.113.9", 9, timeout=0.2)
        with self.assertRaises(LobbyClientError) as cm:
            client.call({"operation": "browse"})
        self.assertNotIn("203.0.113.9", str(cm.exception))
        for call in (lambda: client.open_relay("guest", {}, wait_paired=True), lambda: client.open_punch("guest", {})):
            with self.assertRaises(LobbyClientError) as cm:
                call()
            self.assertNotIn("203.0.113.9", str(cm.exception))

    def test_the_page_masks_the_servers_address_behind_the_eye(self):
        src = UI.read_text(encoding="utf-8")
        self.assertNotIn('+V.server_host', src)

    def test_connecting_by_code_does_not_hand_the_host_back_to_the_page(self):
        src = (pathlib.Path(__file__).resolve().parent.parent / "launcher" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn('"host": found["host"]', src)


if __name__ == "__main__":
    unittest.main()
