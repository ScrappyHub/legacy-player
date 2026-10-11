import json
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from launcher import reports
from server import report_receiver


def center(mode="off", url="", name="Player", seen=False):
    data = Path(tempfile.mkdtemp())
    state = {"error_reports": mode, "report_url": url, "display_name": name, "report_prompt_seen": seen}
    center = reports.ReportCenter(data, lambda: state, lambda k, v: state.__setitem__(k, v),
                                  lambda: {"network": {"address_kind": "cgnat"}, "doing": {"playing": False}, "_roots": [r"D:\Games"]})
    return center, state, data


def boom(msg="bad thing"):
    try:
        raise ValueError(msg)
    except ValueError as exc:
        return exc


class ScrubTests(unittest.TestCase):
    def test_personal_details_are_removed(self):
        sc = reports.Scrubber({"alec": "<user>", "MYPC": "<pc>"}, {r"C:\Users\alec": "<home>", r"D:\Games": "<games>"})
        text = (r"Failed at C:\Users\alec\AppData\x.txt and D:\Games\NES\Mario (USA).nes for alec on MYPC "
                "from 192.168.1.20:8765 and 203.0.113.9, mail me@example.com, code LP-ABCDEFGHJKLMNPQRSTUV2345 "
                "invite ABCDE-FGHIJ key a1b2c3d4e5f6a7b8c9d0e1f2a3b4 url https://x.test/a?token=abc")
        out = sc.text(text)
        for leaked in ("alec", "MYPC", "192.168", "203.0.113", "me@example.com", "ABCDEFGHJKLMNPQRSTUV2345", "ABCDE-FGHIJ", "a1b2c3d4e5f6", "token=abc"):
            self.assertNotIn(leaked, out)
        self.assertIn("<games>", out)

    def test_our_own_code_locations_survive(self):
        sc = reports.Scrubber()
        out = sc.text(r'File "C:\Program Files\LegacyPlayer\_internal\launcher\app.py", line 12, in api_launch')
        self.assertIn("launcher/app.py", out)
        self.assertNotIn("Program Files", out)

    def test_loopback_is_not_hidden_other_addresses_are(self):
        sc = reports.Scrubber()
        self.assertIn("127.0.0.1", sc.text("connect 127.0.0.1:8780"))
        self.assertNotIn("10.0.0.5", sc.text("connect 10.0.0.5:8780"))


class ModeTests(unittest.TestCase):
    def test_off_saves_nothing_to_disk_but_remembers_one_in_memory(self):
        c, state, data = center("off")
        r = c.capture("internal-error", boom(), context={"api": "launch"})
        self.assertIsNotNone(r)
        self.assertFalse((data / "reports").exists())
        self.assertEqual(r["id"], c.held["id"])
        self.assertEqual("off", c.prompt()["mode"])           # the one-time question
        self.assertIsNone(c.prompt())                          # not twice in a row

    def test_after_never_nothing_asks_again(self):
        c, state, _ = center("off")
        r = c.capture("internal-error", boom(), context={"api": "a"})
        c.decide(r["id"], "never")
        self.assertTrue(state["report_prompt_seen"])
        self.assertIsNone(c.held)
        c.capture("internal-error", boom("another"), context={"api": "b"})
        c.last_prompt = 0
        self.assertIsNone(c.prompt())

    def test_ask_mode_keeps_reports_for_the_player_to_approve(self):
        c, state, data = center("ask")
        r = c.capture("launch-failed", boom(), context={"console": "nes"})
        self.assertEqual(1, len(c.pending()))
        self.assertEqual("ask", c.prompt()["mode"])
        self.assertFalse(c.send(r["id"])["sent"])             # no address built in yet: stays local
        self.assertEqual(1, len(c.pending()))

    def test_same_problem_is_counted_not_repeated(self):
        c, _, _ = center("ask")
        c.capture("internal-error", boom(), context={"api": "x"})
        self.assertIsNone(c.capture("internal-error", boom(), context={"api": "x"}))
        self.assertEqual(1, len(c.pending()))
        self.assertEqual(2, c.pending()[0]["occurrences"])

    def test_the_report_holds_no_personal_details(self):
        c, _, _ = center("ask", name="Alec the Great")
        r = c.capture("internal-error", boom("Cannot open Alec the Great's save at C:\\Users\\Someone\\x.sav from 10.1.2.3"), context={"api": "saves"})
        blob = json.dumps(r)
        for leaked in ("Alec the Great", "Someone", "10.1.2.3"):
            self.assertNotIn(leaked, blob)
        self.assertEqual("cgnat", r["network"]["address_kind"])
        self.assertTrue(r["fingerprint"])

    def test_only_https_addresses(self):
        c, _, _ = center("ask", url="http://example.com/r")
        r = c.capture("x", boom(), context={"a": 1})
        self.assertIn("https", c.send(r["id"])["why"])


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.store = report_receiver.Store(self.folder)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), report_receiver.make_handler(self.store, None))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"

    def tearDown(self):
        self.httpd.shutdown()

    def test_auto_mode_sends_and_the_receiver_files_it(self):
        c, _, _ = center("auto", url=self.url)
        r = c.capture("internal-error", boom("it broke"), context={"api": "launch"})
        for _ in range(50):
            if (self.folder / "index.jsonl").exists():
                break
            time.sleep(0.1)
        line = json.loads((self.folder / "index.jsonl").read_text().splitlines()[0])
        self.assertEqual(r["fingerprint"], line["fingerprint"])
        self.assertEqual("ValueError", line["error"])
        self.assertEqual([], c.pending())                     # sent reports are not kept

    def test_receiver_refuses_junk_and_oversize_and_bad_token(self):
        def post(body, headers=None):
            req = urllib.request.Request(self.url, data=body, method="POST", headers={"Content-Type": "application/json", **(headers or {})})
            try:
                return urllib.request.urlopen(req, timeout=5).status
            except urllib.error.HTTPError as err:
                return err.code
        self.assertEqual(400, post(b"{not json"))
        self.assertEqual(400, post(json.dumps({"schema": "other"}).encode()))
        self.assertEqual(413, post(b"x" * (report_receiver.MAX_BODY + 1)))
        locked = ThreadingHTTPServer(("127.0.0.1", 0), report_receiver.make_handler(self.store, "secret"))
        threading.Thread(target=locked.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{locked.server_address[1]}/", data=b"{}", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(401, ctx.exception.code)
        finally:
            locked.shutdown()

    def test_unreachable_receiver_keeps_the_report(self):
        c, _, _ = center("ask", url="http://127.0.0.1:9/")
        r = c.capture("x", boom(), context={"a": 1})
        self.assertFalse(c.send(r["id"])["sent"])
        self.assertEqual(1, len(c.pending()))


class AppHookTests(unittest.TestCase):
    def test_launch_failure_reaches_reports_and_default_is_off(self):
        from tests.test_app_actions import make_app
        app, _ = make_app()
        self.assertEqual("off", app.catalog.settings()["error_reports"])
        app.catalog.set_setting("error_reports", "ask")
        app.reports.capture("launch-failed", boom(), context={"console": "nes"})
        self.assertEqual(1, app.api_report_list({})["pending"])
        text = app.api_report_preview({"id": app.api_report_list({})["reports"][0]["id"]})["text"]
        self.assertIn("launch-failed", text)
        self.assertEqual(1, app.api_report_clear({})["removed"])

    def test_ping_carries_the_question(self):
        from tests.test_app_actions import make_app
        app, _ = make_app()
        app.reports.capture("internal-error", boom(), context={"api": "x"})
        self.assertEqual("off", app.api_ping({})["report_prompt"]["mode"])
        self.assertIsNone(app.api_ping({})["report_prompt"])


class ScrubberExtraTests(unittest.TestCase):
    def test_forward_slash_unc_and_host_names_do_not_leak(self):
        from launcher.reports import Scrubber
        s = Scrubber({"al": "<user>"})
        for raw, leak in (("C:/Games/Secret Dir/foo.iso", "Secret"), ("\\\\NAS01\\roms\\x.iso", "NAS01"), ("bob-home.duckdns.org:8780", "duckdns")):
            self.assertNotIn(leak, s.text("failed: " + raw))
        self.assertNotIn("example.com", s.text("https://example.com/a?b=1"))      # a link may point at a friend's server: whole link goes
        self.assertIn("github.com", s.text("see https://github.com/Alpallyoop/legacy-player/issues?q=1"))


class WrittenReportsAndAdminConsole(unittest.TestCase):
    """'See a problem?' reports reach the receiver with their category, and the admin console can read and triage them."""
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.store = report_receiver.Store(self.folder)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), report_receiver.make_handler(self.store, None, "adm1n"))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"

    def tearDown(self):
        self.httpd.shutdown()

    def _get(self, path, token="adm1n", body=None):
        req = urllib.request.Request(self.url.rstrip("/") + path + ("&" if "?" in path else "?") + "token=" + token,
                                     data=json.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as err:
            return err.code, b""

    def test_player_written_report_is_sent_even_when_reports_are_off_and_is_scrubbed(self):
        c, state, _ = center("off", url=self.url, name="alec")
        with self.assertRaises(ValueError):
            c.file("other", "   ")
        out = c.file("online-play", r"alec could not join from C:\Users\alec\Desktop, code LP-ABCDEFGHJKLMNPQRSTUV2345")
        self.assertTrue(out["sent"], out)
        self.assertEqual("off", state["error_reports"])            # their mode is not touched
        self.assertEqual([], c.pending())
        rows = self.store.index()
        self.assertEqual(1, len(rows))
        self.assertEqual("user-report", rows[0]["kind"])
        self.assertEqual("online-play", rows[0]["category"])
        rep = self.store.read(rows[0]["id"])
        text = json.dumps(rep)
        self.assertNotIn("alec", text)
        self.assertNotIn("ABCDEFGHJKLMNPQRSTUV2345", text)
        self.assertIn("could not join", rep["context"]["description"])
        two = c.file("other", "second one")
        self.assertNotEqual(out["id"], two["id"])
        self.assertEqual(2, len(self.store.index()))               # written reports are never folded together

    def test_admin_console_needs_its_token_and_keeps_triage(self):
        c, _, _ = center("auto", url=self.url)
        c.file("display", "the picture tears")
        self.assertEqual(401, self._get("/admin", token="wrong")[0])
        self.assertEqual(401, self._get("/admin/list", token="")[0])
        status, body = self._get("/admin")
        self.assertEqual(200, status)
        self.assertIn(b"<title>Legacy Player reports</title>", body)
        status, body = self._get("/admin/list")
        rows = json.loads(body)["reports"]
        self.assertEqual(1, len(rows))
        self.assertEqual("new", rows[0]["status"])
        status, body = self._get("/admin/triage", body={"key": rows[0]["key"], "status": "looking", "note": "on it"})
        self.assertEqual(200, status)
        self.assertEqual(400, self._get("/admin/triage", body={"key": rows[0]["key"], "status": "bogus"})[0])
        again = report_receiver.Store(self.folder).index()[0]    # triage survives a restart
        self.assertEqual(("looking", "on it"), (again["status"], again["note"]))
        status, body = self._get("/admin/report?id=" + rows[0]["id"])
        self.assertEqual("user-report", json.loads(body)["kind"])
        # the admin token never lets a report in through the front door, and reports never need it
        req = urllib.request.Request(self.url, data=b"{}", method="POST", headers={"Content-Type": "application/json", "X-Admin-Token": "adm1n"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(400, ctx.exception.code)
