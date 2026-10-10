"""The privacy check: every online feature has its own switch, and anything on that the player never said yes to is flagged."""
import tempfile
import unittest
from pathlib import Path

from launcher import privacy
from launcher.app import AppError, LauncherApp


class PrivacyCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = LauncherApp(Path(self.tmp.name) / "data")

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_send_nothing_but_the_local_network_test(self):
        out = self.app.api_privacy({})
        on = {i["id"] for i in out["items"] if i["on"]}
        self.assertEqual({"network_test"}, on)
        self.assertEqual(0, out["to_look_at"])                     # the network test talks to this computer and your server only
        self.assertIn("does not collect data", out["never"])
        self.assertFalse([i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"])

    def test_downloads_and_game_info_are_separate_switches(self):
        ids = {i["id"]: i["setting"] for i in self.app.api_privacy({})["items"]}
        self.assertEqual("allow_internet", ids["downloads"])
        self.assertEqual("allow_game_info", ids["game_info"])
        self.app.catalog.set_setting("allow_internet", True)
        games = Path(self.tmp.name) / "g" / "NES"
        games.mkdir(parents=True)
        (games / "Alpha (USA).nes").write_bytes(b"NES\x1a" + b"\0" * 32)
        self.app.catalog.set_roots([str(games.parent)])
        self.app.rescan()
        gid = next(iter(self.app.games))
        with self.assertRaises(AppError) as ctx:                     # downloads on does not open up look-ups
            self.app.api_game_card({"id": gid, "action": "lookup", "consent": True})
        self.assertIn("Look up game details", str(ctx.exception))

    def test_something_switched_on_behind_the_players_back_is_flagged_until_kept_or_turned_off(self):
        self.app.catalog.set_setting("allow_direct_connections", True)        # as if an old file or someone else did it
        self.app.catalog.set_setting("friends_server", "https://friends.example.org")
        issues = [i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"]
        self.assertEqual({"privacy:direct", "privacy:friends"}, {i["key"] for i in issues})
        self.assertEqual("worried", self.app.api_doctor({})["mood"] if self.app.games else "worried")
        self.app.api_privacy({"action": "keep", "id": "direct"})
        self.app.api_privacy({"action": "off", "id": "friends"})
        self.assertEqual("", self.app.catalog.settings()["friends_server"])
        self.assertFalse([i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"])
        # a different address is a different thing to say yes to
        self.app.api_settings({"key": "friends_server", "value": "https://a.example.org", "informed": True})
        self.assertFalse([i for i in self.app.api_doctor({})["issues"] if i["kind"] == "privacy"])
        self.app.catalog.set_setting("friends_server", "https://b.example.org")
        self.assertTrue([i for i in self.app.api_doctor({})["issues"] if i["key"] == "privacy:friends"])
        with self.assertRaises(AppError):
            self.app.api_privacy({"action": "keep", "id": "nope"})

    def test_every_item_says_where_it_goes_and_what_it_sends(self):
        for it in privacy.items(self.app.catalog.settings(), self.app.catalog.data):
            for key in ("title", "what", "contacts", "sends", "off_means", "setting"):
                self.assertTrue(it[key], (it["id"], key))
            self.assertIn(it["setting"], privacy.OFF_VALUES)


if __name__ == "__main__":
    unittest.main()
