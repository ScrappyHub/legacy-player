"""Opens the real app in a headless browser and clicks through every page. Skipped when Playwright is not installed
(pip install playwright; playwright install chromium). It catches the kind of break unit tests cannot: a page that
throws while drawing, a menu that no longer opens, a secret link that stops working."""
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:      # pragma: no cover
    sync_playwright = None

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["home", "library", "console", "setup", "together", "servers", "engines", "controllers", "saves",
         "emulators", "settings", "credits", "help", "storage", "profile", "display", "probe"]


@unittest.skipUnless(sync_playwright, "Playwright is not installed")
class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        games = base / "games" / "NES"
        games.mkdir(parents=True)
        for name in ("Alpha Quest (USA).nes", "Beta Blast (USA).nes"):
            (games / name).write_bytes(b"NES\x1a" + b"\0" * 64)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        # a clean environment: other tests change os.environ in this process, and the app must not inherit that
        keep = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "PYTHONPATH", "LOCALAPPDATA", "APPDATA")
        env = {k: os.environ[k] for k in keep if k in os.environ}
        env["LEGACY_PLAYER_NO_BACKGROUND"] = "1"
        cls.proc = subprocess.Popen([sys.executable, "-m", "launcher", "--data-dir", str(base / "data"), "--games", str(base / "games"),
                                     "--port", str(port), "--no-browser"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        line = ""
        deadline = time.time() + 30
        while time.time() < deadline and "http://" not in line:
            line = cls.proc.stdout.readline()
        found = re.search(r"http://\S+", line)
        if not found:
            cls.proc.kill()
            raise RuntimeError("the app did not start: " + line)
        cls.url, cls.port = found.group(0), port

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        cls.proc.wait(5)
        cls.tmp.cleanup()

    def test_page_needs_its_secret_link(self):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/")
            self.fail("the bare address must not serve the page")
        except urllib.error.HTTPError as err:
            self.assertEqual(403, err.code)

    def test_every_page_draws_without_errors(self):
        problems = []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.set_default_timeout(20000)
            page.on("pageerror", lambda e: problems.append("page error: " + str(e)))
            logs = []
            page.on("console", lambda m: (logs.append(m.type + ": " + m.text), problems.append("console: " + m.text) if m.type == "error" else None))
            page.on("requestfailed", lambda r: logs.append("request failed: " + r.url))
            page.on("response", lambda r: logs.append(f"{r.status} {r.url}") if r.status >= 400 else None)
            page.goto(self.url)
            page.wait_for_selector("#nav button, #nav a", state="attached")
            page.wait_for_timeout(1200)
            for name in PAGES:
                page.evaluate(f'nav("{name}")')
                for _ in range(100):      # poll (the page's security policy forbids wait_for_function, which uses eval)
                    if page.evaluate('document.querySelector("#main").children.length') > 0:
                        break
                    page.wait_for_timeout(200)
                page.wait_for_timeout(900)
                self.assertGreater(page.evaluate('document.querySelector("#main").children.length'), 0, f"{name} drew nothing")
                self.assertLess(page.evaluate('document.querySelectorAll("#main > h2").length'), 2, f"{name} drew twice")
            self.assertIn("No pad", page.inner_text("#inpill"))
            page.evaluate('nav("library")')
            page.wait_for_selector(".game")
            page.locator(".game").first.click(button="right")
            try:
                page.wait_for_selector(".ctx", timeout=8000)
            except Exception:
                self.fail("the game menu did not open")
            # clicking the doctor (even double-clicking) must not leave selected text, which pops up the browser's own mini menu
            page.evaluate('nav("home")')
            page.wait_for_selector(".px.doctor")
            page.wait_for_timeout(600)
            page.locator(".px.doctor").first.dblclick(force=True)
            page.locator(".hero, .doc").first.dblclick(force=True)
            self.assertEqual("", page.evaluate("getSelection().toString()"))
            # the Dolphin memory probe page, drawn with a pretend "Dolphin found" answer (the real one is Windows only)
            ready = {"supported": True, "ready": True, "waiting_for_action": False, "label": "", "tracked_pages": 3,
                     "game": {"id": "GMPE01", "region": "USA", "phase": "board"}, "ram": {"base": "0x1000", "size": 33554432},
                     "actions": [{"name": "coin_total_change_once", "confidence": "grounded", "pages": 3}]}
            page.route("**/api/probe_status", lambda route: route.fulfill(status=200, content_type="application/json", body=__import__("json").dumps(ready)))
            page.evaluate('nav("probe")')
            page.wait_for_selector("text=Take baseline")
            self.assertEqual(0, page.locator("#main button:disabled").count())
            # dialogs: Tab stays inside, Esc means Cancel (the link is single-use, so this shares the page above)
            page.evaluate("() => { window.__r = 'unset'; ask('Really?', 'Yes').then(v => { window.__r = v }); }")      # not returned: evaluate would wait for it
            page.wait_for_selector(".modal")
            for _ in range(4):
                page.keyboard.press("Tab")
            self.assertTrue(page.evaluate("!!document.activeElement.closest('.modal')"), "Tab left the dialog")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            self.assertEqual(0, page.locator(".modal").count())
            self.assertIs(False, page.evaluate("window.__r"))
            browser.close()
        self.assertEqual([], problems)


if __name__ == "__main__":
    unittest.main()
