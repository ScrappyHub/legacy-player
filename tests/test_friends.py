"""The friends layer: a separate service with no sign-ups, and Legacy Player's optional page on top of it."""
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from launcher.app import AppError, LauncherApp
from server.social import SocialError, SocialService
from server.social.__main__ import make_handler


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class ServiceRules(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.s = SocialService(None, self.clock)
        self.a = self.s.hello("Alec")
        self.b = self.s.hello("Bea")

    def test_hello_gives_a_code_and_nothing_personal_is_asked(self):
        self.assertRegex(self.a["code"], r"^[A-Z2-9]{3}-[A-Z2-9]{4}$")
        self.assertEqual(set(self.a), {"id", "secret", "code", "name"})
        with self.assertRaises(SocialError):
            self.s.heartbeat(self.a["id"], "wrong secret")

    def test_friend_request_by_code_then_accept_then_see_each_other(self):
        inbox = self.s.request(self.a["id"], self.a["secret"], self.b["code"].lower().replace("-", ""))   # codes are forgiving
        self.assertEqual([self.b["id"]], [x["id"] for x in inbox["sent"]])
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertEqual(["Alec"], [r["name"] for r in bb["requests"]])
        bb = self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)
        self.assertEqual(["Alec"], [f["name"] for f in bb["friends"]])
        self.assertTrue(bb["friends"][0]["online"])
        self.clock.t += 120
        aa = self.s.heartbeat(self.a["id"], self.a["secret"])
        self.assertFalse(aa["friends"][0]["online"])              # Bea's app has not checked in for two minutes
        with self.assertRaises(SocialError):
            self.s.request(self.a["id"], self.a["secret"], "ZZZ-ZZZZ")
        with self.assertRaises(SocialError):
            self.s.request(self.a["id"], self.a["secret"], self.a["code"])

    def test_requests_crossing_become_friends_at_once(self):
        self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        inbox = self.s.request(self.b["id"], self.b["secret"], self.a["code"])
        self.assertEqual(["Alec"], [f["name"] for f in inbox["friends"]])

    def _befriend(self):
        self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)

    def test_room_is_shared_only_while_online_and_invites_carry_the_way_in(self):
        self._befriend()
        self.s.heartbeat(self.a["id"], self.a["secret"], status="in a room",
                         room={"invite_code": "ABCDE-FGH12", "game": "Mario Kart 64", "server_code": "LP-XYZ", "players": 1, "max_players": 4})
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertEqual("ABCDE-FGH12", bb["friends"][0]["room"]["invite_code"])
        self.assertEqual("in a room", bb["friends"][0]["status"])
        self.s.invite(self.a["id"], self.a["secret"], self.b["id"], "ABCDE-FGH12", "Mario Kart 64", "LP-XYZ")
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertEqual(1, len(bb["invites"]))
        self.assertEqual("Alec", bb["invites"][0]["name"])
        bb = self.s.dismiss_invite(self.b["id"], self.b["secret"], self.a["id"])
        self.assertEqual([], bb["invites"])
        self.clock.t += 120
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertIsNone(bb["friends"][0]["room"])                 # gone quiet: nothing to join is shown
        c = self.s.hello("Stranger")
        with self.assertRaises(SocialError):
            self.s.invite(c["id"], c["secret"], self.b["id"], "ABCDE-FGH12", "x")

    def test_messages_go_both_ways_and_count_unread(self):
        self._befriend()
        self.s.message(self.a["id"], self.a["secret"], self.b["id"], "game tonight?")
        bb = self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertEqual(1, bb["friends"][0]["unread"])
        t = self.s.thread(self.b["id"], self.b["secret"], self.a["id"])
        self.assertEqual(["game tonight?"], [m["text"] for m in t["messages"]])
        self.assertFalse(t["messages"][0]["mine"])
        self.assertEqual(0, self.s.heartbeat(self.b["id"], self.b["secret"])["friends"][0]["unread"])
        with self.assertRaises(SocialError):
            self.s.message(self.a["id"], self.a["secret"], self.b["id"], "   ")
        self.s.remove(self.a["id"], self.a["secret"], self.b["id"])
        self.assertEqual([], self.s.heartbeat(self.b["id"], self.b["secret"])["friends"])
        with self.assertRaises(SocialError):
            self.s.message(self.a["id"], self.a["secret"], self.b["id"], "hi")

    def test_goodbye_and_forgetting_the_idle(self):
        self._befriend()
        self.s.goodbye(self.b["id"], self.b["secret"])
        self.assertEqual([], self.s.heartbeat(self.a["id"], self.a["secret"])["friends"])
        self.clock.t += 61 * 86400
        self.s.hello("Someone")                                     # a tidy runs on hello
        self.assertNotIn(self.a["id"], self.s.players)

    def test_state_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            s = SocialService(Path(d), self.clock)
            a = s.hello("Alec")
            again = SocialService(Path(d), self.clock)
            self.assertEqual(a["code"], again.players[a["id"]]["code"])
            self.assertEqual(a["id"], again.codes[a["code"]])


class OverHttpAndInTheApp(unittest.TestCase):
    def setUp(self):
        self.service = SocialService(None)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.app = LauncherApp(Path(self.tmp.name) / "data")

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def test_page_is_off_until_an_address_is_set_then_hello_poll_and_invite(self):
        st = self.app.api_friends({"action": "status"})
        self.assertFalse(st["enabled"])
        with self.assertRaises(AppError):
            self.app.api_friends({"action": "hello"})
        self.app.catalog.set_setting("friends_server", "http://example.com/")           # plain http to a stranger is refused
        self.assertFalse(self.app.api_friends({})["enabled"])
        self.app.catalog.set_setting("friends_server", self.url)
        self.assertTrue(self.app.api_friends({})["enabled"])
        out = self.app.api_friends({"action": "hello"})
        self.assertRegex(out["me"]["code"], r"^[A-Z2-9]{3}-[A-Z2-9]{4}$")
        self.assertNotIn("secret", out["me"])
        self.assertIn("secret", self.app.catalog.data["friends"])
        other = self.service.hello("Bea")
        inbox = self.app.api_friends({"action": "request", "code": other["code"]})["inbox"]
        self.assertEqual(["Bea"], [x["name"] for x in inbox["sent"]])
        self.service.decide(other["id"], other["secret"], self.app.catalog.data["friends"]["id"], True)
        inbox = self.app.api_friends({"action": "poll"})["inbox"]
        self.assertEqual(["Bea"], [f["name"] for f in inbox["friends"]])
        with self.assertRaises(AppError):
            self.app.api_friends({"action": "invite", "to": other["id"]})                 # no room yet
        self.app.room = {"invite_code": "ABCDE-FGH12", "game": "Tetris", "role": "host", "members": [{"name": "me"}], "max_players": 2, "session": {}}
        self.app.api_friends({"action": "invite", "to": other["id"]})
        self.app.api_friends({"action": "poll"})                                          # the page's regular check-in shares the room
        bb = self.service.heartbeat(other["id"], other["secret"])
        self.assertEqual("ABCDE-FGH12", bb["invites"][0]["invite_code"])
        self.assertEqual("Tetris", bb["friends"][0]["room"]["game"])
        self.app.catalog.set_setting("friends_share_room", False)
        self.app.api_friends({"action": "poll"})
        self.assertIsNone(self.service.heartbeat(other["id"], other["secret"])["friends"][0]["room"])
        self.app.api_friends({"action": "message", "to": other["id"], "text": "hello"})
        self.assertEqual(["hello"], [m["text"] for m in self.app.api_friends({"action": "thread", "friend": other["id"]})["messages"]])
        self.app.api_friends({"action": "goodbye"})
        self.assertEqual({}, self.app.catalog.data["friends"])

    def test_http_front_refuses_junk(self):
        def post(body):
            req = urllib.request.Request(self.url + "/", data=body, method="POST", headers={"Content-Type": "application/json"})
            try:
                return urllib.request.urlopen(req, timeout=5).status
            except urllib.error.HTTPError as err:
                return err.code
        self.assertEqual(400, post(b"{nope"))
        self.assertEqual(400, post(json.dumps({"op": "fly"}).encode()))
        self.assertEqual(413, post(b"x" * 20000))
        self.assertEqual(200, urllib.request.urlopen(self.url + "/health", timeout=5).status)


if __name__ == "__main__":
    unittest.main()
