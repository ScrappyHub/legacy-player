"""Running the friends service from Legacy Player: one call starts it (encrypted, moderator key made by itself), the app
moderates it without typing anything, someone else can help moderate with the key, and it stops cleanly."""
import json
import socket
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from launcher import firewall, friends as friendsmod, privacy
from launcher.app import AppError, LauncherApp


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class HostedService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.port = free_port()
        cls.router = mock.patch("launcher.app.portmap.open_port", return_value={"state": "no_router", "message": "No router answered."})
        cls.router.start()
        cls.host = LauncherApp(base / "host")
        cls.host.catalog.set_setting("display_name", "Host")
        cls.host.catalog.set_setting("friends_host_port", cls.port)
        cls.started = cls.host.api_friends_host({"action": "start"})
        cls.guest = LauncherApp(base / "guest")
        cls.guest.catalog.set_setting("display_name", "Guest")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.host.api_friends_host({"action": "stop"})
        finally:
            cls.router.stop()
            cls.tmp.cleanup()

    def link(self):
        st = self.host.api_friends_host({"action": "status"})
        return st["link"].replace(st["address"], "127.0.0.1") if st["address"] else st["link"]

    def test_1_one_call_runs_it_and_the_host_is_the_moderator(self):
        self.assertTrue(self.started["running"])
        st = self.host.api_friends({"action": "status"})
        self.assertTrue(st["enabled"])
        self.assertTrue(st["hosting"])
        self.assertTrue(st["moderator"])                         # read from the key file: nothing typed
        self.assertTrue(st["me"].get("code"))                    # said hello by itself
        self.assertTrue(self.host.social_host.key().startswith("LPM-"))
        self.assertIn("#pin=", self.host.catalog.settings()["friends_server"])
        self.assertIn("reports", self.host.api_friends_mod({"action": "reports"}))
        items = {i["id"]: i for i in privacy.items(self.host.catalog.settings(), self.host.catalog.data)}
        self.assertTrue(items["friends_host"]["on"])
        self.assertFalse(items["friends_host"]["needs_look"])    # pressing Run (after reading what it does) was the yes
        self.assertFalse(items["friends"]["needs_look"])

    def test_2_a_friend_joins_with_the_link_and_a_helper_moderates_with_the_key(self):
        link = self.link()
        self.assertRegex(link, r"^https://127\.0\.0\.1:\d+/#pin=[0-9a-f]{64}$")
        self.guest.catalog.set_setting("friends_server", link)
        self.guest.api_friends({"action": "hello"})
        guest_st = self.guest.api_friends({"action": "status"})
        self.assertFalse(guest_st["moderator"])
        with self.assertRaises(AppError):
            self.guest.api_friends_mod({"action": "reports"})
        with self.assertRaises(AppError):
            self.guest.api_friends_mod({"action": "set_key", "key": "LPM-this-is-not-the-key-at-all"})
        key = self.host.api_friends_host({"action": "key"})["key"]
        self.guest.api_friends_mod({"action": "set_key", "key": key})
        self.assertTrue(self.guest.api_friends({"action": "status"})["moderator"])
        guest_id = self.guest.friends.identity()["id"]
        self.host.api_friends_mod({"action": "act", "do": "timeout", "player": guest_id, "length": "1h", "reason": "cool down"})
        players = self.guest.api_friends_mod({"action": "players", "q": "Guest"})["players"]
        self.assertTrue(players[0]["muted"])
        self.guest.api_friends_mod({"action": "act", "do": "untimeout", "player": guest_id})
        self.guest.api_friends_mod({"action": "filter", "on": True, "words": "grob"})
        self.assertTrue(self.host.api_friends_mod({"action": "reports"})["filter"]["on"])
        self.host.api_friends_mod({"action": "filter", "on": False, "words": ""})

    def test_3_a_wrong_fingerprint_is_refused(self):
        server, pin = friendsmod.split_link(self.link())
        with self.assertRaises(friendsmod.FriendsError):
            friendsmod.pinned_request(server + "/health", "0" * 64, None, {}, 3, "GET")
        status, raw = friendsmod.pinned_request(server + "/health", pin, None, {}, 3, "GET")
        self.assertEqual(200, status)

    def test_4_the_console_needs_the_key_for_every_answer(self):
        server, pin = friendsmod.split_link(self.link())
        status, raw = friendsmod.pinned_request(server + "/admin", pin, None, {}, 3, "GET")
        self.assertEqual(200, status)                            # the page itself, which asks for the key
        self.assertIn(b"Moderator key", raw)
        status, _ = friendsmod.pinned_request(server + "/admin/reports", pin, None, {}, 3, "GET")
        self.assertEqual(401, status)
        status, _ = friendsmod.pinned_request(server + "/admin/stop", pin, b"{}", {"Content-Type": "application/json"}, 3)
        self.assertEqual(401, status)                            # stopping it needs the key too

    def test_5_an_update_stops_it_and_it_comes_back(self):
        self.host._before_restart()
        self.assertFalse(self.host.social_host.running(self.port))
        self.assertTrue(self.host.catalog.data.get("friends_host_wanted"))    # still wanted: the new version starts it
        again = self.host.api_friends_host({"action": "start"})
        self.assertTrue(again["running"])
        self.assertTrue(self.host.api_friends({"action": "status"})["moderator"])


class StopAndSwitch(unittest.TestCase):
    def test_stopping_clears_the_link_and_switching_services_asks_first(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch("launcher.app.portmap.open_port", return_value={"state": "no_router", "message": ""}):
            app = LauncherApp(Path(d))
            app.catalog.set_setting("friends_host_port", free_port())
            app.catalog.set_setting("friends_server", "https://friends.example.org")
            app.catalog.data["friends"] = {"server": "https://friends.example.org", "id": "x", "secret": "y", "code": "AAA-BBBB"}
            with self.assertRaises(AppError):
                app.api_friends_host({"action": "start"})        # would move them away from their friends: needs a yes
            out = app.api_friends_host({"action": "start", "switch": True})
            self.assertTrue(out["running"])
            out = app.api_friends_host({"action": "stop"})
            self.assertFalse(out["running"])
            self.assertEqual("", app.catalog.settings()["friends_server"])
            self.assertFalse(app.api_friends({"action": "status"})["hosting"])
            with self.assertRaises(AppError):
                app.api_friends_host({"action": "key"})


class FirewallRules(unittest.TestCase):
    def test_the_friends_service_has_its_own_rule(self):
        args = firewall.rule_args(8791, program="", rule=firewall.RULE_FRIENDS)
        self.assertIn(f"name={firewall.RULE_FRIENDS}", args)
        self.assertIn("localport=8791", args)
        self.assertIn(f'name="{firewall.RULE}"', firewall.manual_command(8765))


if __name__ == "__main__":
    unittest.main()
