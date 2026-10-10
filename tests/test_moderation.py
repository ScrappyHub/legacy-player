"""Friends moderation: who can reach whom, reports that can't be faked, timeouts, bans and the word filter."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from launcher.app import AppError, LauncherApp
from server.social import SocialError, SocialService, textfilter
from server.social.__main__ import make_handler


class Clock:
    def __init__(self):
        self.t = 2_000_000.0

    def __call__(self):
        return self.t


def friends(s, a, b):
    s.request(a["id"], a["secret"], b["code"])
    s.decide(b["id"], b["secret"], a["id"], True)


class WhoCanReachWhom(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.s = SocialService(None, self.clock)
        self.a, self.b, self.c = self.s.hello("Alec"), self.s.hello("Bea"), self.s.hello("Cal")

    def test_only_friends_can_message_or_invite(self):
        with self.assertRaises(SocialError):
            self.s.message(self.a["id"], self.a["secret"], self.c["id"], "hi")           # not friends
        self.s.request(self.a["id"], self.a["secret"], self.c["code"])
        with self.assertRaises(SocialError):
            self.s.message(self.a["id"], self.a["secret"], self.c["id"], "hi")           # a request is not friendship
        with self.assertRaises(SocialError):
            self.s.invite(self.a["id"], self.a["secret"], self.c["id"], "ABCDE-FGH12", "x")

    def test_requests_can_be_closed_and_are_rate_limited(self):
        self.s.heartbeat(self.c["id"], self.c["secret"], requests_open=False)
        with self.assertRaises(SocialError) as ctx:
            self.s.request(self.a["id"], self.a["secret"], self.c["code"])
        self.assertIn("isn't taking friend requests", str(ctx.exception))
        self.s.request(self.c["id"], self.c["secret"], self.a["code"])                    # Cal can still add others himself
        others = [self.s.hello(f"P{i}") for i in range(25)]
        sent = 0
        with self.assertRaises(SocialError):
            for o in others:
                self.s.request(self.b["id"], self.b["secret"], o["code"])
                sent += 1
        self.assertEqual(20, sent)

    def test_friend_codes_cant_be_guessed(self):
        with self.assertRaises(SocialError) as ctx:
            for i in range(80):
                try:
                    self.s.request(self.a["id"], self.a["secret"], f"ZZZ-{i:04d}")
                except SocialError as exc:
                    if "tries" in str(exc):
                        raise
        self.assertIn("friend code tries", str(ctx.exception))

    def test_messages_are_rate_limited(self):
        friends(self.s, self.a, self.b)
        with self.assertRaises(SocialError):
            for i in range(25):
                self.s.message(self.a["id"], self.a["secret"], self.b["id"], f"m{i}")
        self.clock.t += 61
        self.s.message(self.a["id"], self.a["secret"], self.b["id"], "later")


class ReportsTimeoutsBans(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.s = SocialService(None, self.clock)
        self.a, self.b, self.c = self.s.hello("Alec"), self.s.hello("Bea"), self.s.hello("Cal")
        friends(self.s, self.a, self.b)

    def test_a_report_quotes_the_services_own_copy_with_context(self):
        for t in ("hi", "how are you", "you are awful"):
            self.s.message(self.b["id"], self.b["secret"], self.a["id"], t)
        msgs = self.s.thread(self.a["id"], self.a["secret"], self.b["id"])["messages"]
        bad = msgs[-1]
        self.assertTrue(bad["id"])
        self.s.report(self.a["id"], self.a["secret"], self.b["id"], "harassment", "keeps doing this", bad["id"])
        rep = self.s.admin_reports()["reports"][0]
        self.assertEqual("you are awful", rep["message"]["text"])
        self.assertEqual(["hi", "how are you"], [c["text"] for c in rep["context"]])
        self.assertEqual("Bea", rep["target"]["name"])
        self.assertEqual("open", rep["status"])
        with self.assertRaises(SocialError):                                              # a message of my own is not theirs
            mine = self.s.message(self.a["id"], self.a["secret"], self.b["id"], "x")["messages"][-1]
            self.s.report(self.a["id"], self.a["secret"], self.b["id"], "harassment", "", mine["id"])
        with self.assertRaises(SocialError):                                              # someone I never came across
            self.s.report(self.a["id"], self.a["secret"], self.c["id"], "spam")
        with self.assertRaises(SocialError):
            self.s.report(self.a["id"], self.a["secret"], self.b["id"], "made-up-category")

    def test_report_and_block_together(self):
        out = self.s.report(self.a["id"], self.a["secret"], self.b["id"], "spam", also_block=True)
        self.assertEqual(["Bea"], [x["name"] for x in out["blocked"]])
        self.s.report(self.a["id"], self.a["secret"], self.b["id"], "spam")              # a blocked player can still be reported

    def test_timeout_pauses_talking_and_tells_them_why(self):
        rid = self.s.report(self.a["id"], self.a["secret"], self.b["id"], "harassment")["report"]
        self.s.admin_act("timeout", report=rid, length="1h", reason="calm down")
        self.assertEqual("resolved", self.s.admin_reports()["reports"][0]["status"])
        with self.assertRaises(SocialError) as ctx:
            self.s.message(self.b["id"], self.b["secret"], self.a["id"], "hey")
        self.assertIn("calm down", str(ctx.exception))
        inbox = self.s.heartbeat(self.b["id"], self.b["secret"])                          # they can still read
        self.assertEqual("calm down", inbox["moderation"]["reason"])
        with self.assertRaises(SocialError):
            self.s.request(self.b["id"], self.b["secret"], self.c["code"])
        self.clock.t += 3601
        self.s.message(self.b["id"], self.b["secret"], self.a["id"], "sorry")
        self.assertIsNone(self.s.heartbeat(self.b["id"], self.b["secret"])["moderation"])
        with self.assertRaises(SocialError):
            self.s.admin_act("timeout", player=self.b["id"], length="forever")

    def test_ban_shuts_them_out_and_unban_lets_them_back(self):
        self.s.admin_act("ban", player=self.b["id"], reason="slurs")
        with self.assertRaises(SocialError) as ctx:
            self.s.heartbeat(self.b["id"], self.b["secret"])
        self.assertIn("banned", str(ctx.exception))
        self.assertIn("slurs", str(ctx.exception))
        self.assertEqual([], self.s.heartbeat(self.a["id"], self.a["secret"])["friends"])  # gone from friends' lists
        with self.assertRaises(SocialError):
            self.s.goodbye(self.b["id"], self.b["secret"])                                # a ban can't be wiped by leaving
        self.clock.t += 90 * 86400
        self.s.hello("x")
        self.assertIn(self.b["id"], self.s.players)                                       # nor by waiting out the idle time
        self.s.admin_act("unban", player=self.b["id"])
        self.s.heartbeat(self.b["id"], self.b["secret"])
        log = self.s.admin_reports()["log"]
        self.assertEqual(["unban", "ban"], [l["action"] for l in log[:2]])

    def test_service_filter_refuses_words_and_names_when_on(self):
        self.s.message(self.a["id"], self.a["secret"], self.b["id"], "what the fuck")       # off by default
        self.s.admin_filter(on=True, words="zorp, blarg")
        with self.assertRaises(SocialError):
            self.s.message(self.a["id"], self.a["secret"], self.b["id"], "what the f.u.c.k")
        with self.assertRaises(SocialError):
            self.s.message(self.a["id"], self.a["secret"], self.b["id"], "you z0rp")
        self.s.message(self.a["id"], self.a["secret"], self.b["id"], "good game, class act")
        with self.assertRaises(SocialError):
            self.s.hello("Blarg")
        self.s.heartbeat(self.a["id"], self.a["secret"], name="sh1t")
        self.assertEqual("Alec", self.s.players[self.a["id"]]["name"])                    # a filtered rename is ignored

    def test_moderation_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            s = SocialService(Path(d), self.clock)
            a, b = s.hello("A"), s.hello("B")
            friends(s, a, b)
            s.report(a["id"], a["secret"], b["id"], "spam")
            s.admin_act("ban", player=b["id"])
            s.admin_filter(on=True, words="zorp")
            again = SocialService(Path(d), self.clock)
            self.assertIn(b["id"], again.mod["bans"])
            self.assertEqual(1, len(again.mod["reports"]))
            self.assertTrue(again.mod["filter"]["on"])


class TextFilter(unittest.TestCase):
    def test_disguises_are_caught_and_innocent_words_are_not(self):
        for bad in ("fuck", "FUCK!", "$h1t", "shiiiiit", "f u c k", "s.h.i.t", "A$$HOLE"):
            self.assertTrue(textfilter.has_bad(bad), bad)
        for fine in ("Scunthorpe", "class", "assassin", "grass", "pass the dickens", "cocktail", "hello"):
            self.assertFalse(textfilter.has_bad(fine), fine)
        self.assertEqual("what the ****", textfilter.mask("what the fuck"))
        self.assertEqual("the **** is here", textfilter.mask("the zorp is here", ["zorp"]))


class ConsoleAndApp(unittest.TestCase):
    def setUp(self):
        self.service = SocialService(None)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service, "m0d"))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.app = LauncherApp(Path(self.tmp.name) / "data")
        self.app.catalog.set_setting("friends_server", self.url)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def _admin(self, path, body=None, token="m0d"):
        req = urllib.request.Request(self.url + path + ("&" if "?" in path else "?") + "token=" + token, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as err:
            return err.code, b""

    def test_report_from_the_app_reaches_the_console_and_the_filter_hides_words(self):
        me = self.app.api_friends({"action": "hello"})["me"]
        bea = self.service.hello("Bea")
        self.service.request(bea["id"], bea["secret"], me["code"])
        self.app.api_friends({"action": "decide", "from": bea["id"], "accept": True})
        self.service.message(bea["id"], bea["secret"], self.app.catalog.data["friends"]["id"], "you are a shit player")
        t = self.app.api_friends({"action": "thread", "friend": bea["id"]})
        self.assertEqual("you are a **** player", t["messages"][0]["text"])               # filtered on screen by default
        self.app.catalog.set_setting("friends_filter", False)
        t = self.app.api_friends({"action": "thread", "friend": bea["id"]})
        self.assertEqual("you are a shit player", t["messages"][0]["text"])
        out = self.app.api_friends({"action": "report", "player": bea["id"], "category": "harassment", "message": t["messages"][0]["id"], "block": True})
        self.assertTrue(out["reported"])
        self.assertEqual(["Bea"], [b["name"] for b in out["inbox"]["blocked"]])
        self.assertEqual(401, self._admin("/admin/reports", token="nope")[0])
        status, body = self._admin("/admin/reports")
        self.assertEqual(200, status)
        rep = json.loads(body)["reports"][0]
        self.assertEqual("you are a shit player", rep["message"]["text"])                 # moderators see the real words
        self.assertEqual(200, self._admin("/admin/act", {"action": "timeout", "report": rep["id"], "length": "24h", "reason": "language"})[0])
        self.assertEqual(400, self._admin("/admin/act", {"action": "explode", "player": bea["id"]})[0])
        self.assertIn(b"Friends service", self._admin("/admin")[1])
        self.app.catalog.set_setting("friends_requests_open", False)
        self.app.api_friends({"action": "poll"})
        self.assertFalse(self.service.players[self.app.catalog.data["friends"]["id"]]["requests_open"])
        with self.assertRaises(AppError):
            self.app.api_friends({"action": "report", "player": "nobody", "category": "spam"})

    def test_no_console_without_a_token(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(SocialService(None)))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/admin?token=", timeout=5)
            self.assertEqual(401, ctx.exception.code)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_console_script_parses(self):
        import shutil
        import subprocess
        from server.social.__main__ import ADMIN_PAGE
        script = ADMIN_PAGE[ADMIN_PAGE.index("<script>") + 8:ADMIN_PAGE.index("</script>")]
        for line in script.splitlines():                   # a Python "\n" inside a JS string would split it in two
            self.assertFalse(line.rstrip().endswith('join("'), line)
        node = shutil.which("node")
        if node:
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
                fh.write(script)
            try:
                self.assertEqual(0, subprocess.run([node, "--check", fh.name], capture_output=True).returncode)
            finally:
                os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main()
