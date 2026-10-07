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
            ready = {"supported": True, "ready": True, "waiting_for_action": False, "label": "",
                     "game": {"key": "GTSE01", "name": "GTSE01 (USA)", "region": "USA", "title": "Test Game (GTSE01)"},
                     "ram": {"base": "0x1000", "size": 25165824, "pages": 6144},
                     "learned": [{"name": "roll_dice", "runs": 2, "pages": 5, "confidence": "grounded", "updated": None}]}
            page.route("**/api/probe_status", lambda route: route.fulfill(status=200, content_type="application/json", body=__import__("json").dumps(ready)))
            page.evaluate('nav("probe")')
            page.wait_for_selector("text=Take baseline")
            self.assertEqual(0, page.locator("#main button:disabled").count())
            # hovering a cover splits it into Play and Online; the Online half opens the host/join box
            page.evaluate('nav("library")')
            page.wait_for_selector(".game")
            page.locator(".game").first.hover()
            page.wait_for_selector(".game .qplay")
            self.assertEqual(1, page.locator(".game").first.locator(".qonline").count())
            page.locator(".game").first.locator(".qonline").click(force=True)
            page.wait_for_selector(".modal")
            self.assertIn("Host a room", page.inner_text(".modal"))
            page.get_by_role("button", name="Cancel").click()
            self.assertEqual(0, page.locator(".modal").count())
            # the launch question and the Display page card
            page.evaluate('void displayModal({emulator:"RetroArch",title:"Test",monitor:"",monitors:[{index:1,label:"Screen 1"},{index:2,label:"Screen 2"}]})')
            page.wait_for_selector(".modal select[data-mon]")
            self.assertIn("Full screen", page.inner_text(".modal"))
            page.get_by_role("button", name="Cancel").click()
            # Dolphin online play: the steps and the host-code box come from the room state, so the screen's 2-second refresh keeps them
            shown = page.evaluate("""() => {
                const L = {engine:'dolphin', ready:true, direct_allowed:true, dolphin_steps:['Step A','Step B'], needs_code:true, endpoint_kind:null, default_port:2626, suggested_address:'192.168.1.5', address_is_home_only:true};
                const host = launchBox({role:'host', launch:L, relay_errors:[]}, true);
                const guest = launchBox({role:'guest', launch:{...L, needs_code:false}, relay_errors:[]}, false);
                const guest2 = launchBox({role:'guest', launch:{...L, needs_code:false, endpoint_kind:'code'}, relay_errors:[]}, false);
                const off = launchBox({role:'guest', launch:{...L, direct_allowed:false}, relay_errors:[]}, false);
                const btn = el => [...el.querySelectorAll('button')].find(b => /Open Dolphin/.test(b.textContent));
                return {hostText: host.textContent, codeHidden: host.querySelector('input[aria-label="Dolphin host code"]').parentElement.hidden,
                        guestWaits: btn(guest).disabled, guestReady: btn(guest2).disabled, offText: off.textContent};
            }""")
            self.assertIn("Step A", shown["hostText"])
            self.assertFalse(shown["codeHidden"])
            self.assertIn("home-network", shown["hostText"])
            self.assertTrue(shown["guestWaits"])
            self.assertFalse(shown["guestReady"])
            self.assertIn("Allow direct connections", shown["offText"])
            page.evaluate('nav("display")')
            page.wait_for_selector("text=Where games open")
            page.evaluate('nav("home")')
            # Home: emulators are character cards, and the featured card has an Open button
            page.evaluate('nav("home")')
            page.wait_for_selector("text=Your emulators")
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
            # first-run setup: the doctor hosts it, the path example is neutral, and Skip only skips that one step
            page.evaluate('S.wizStep=1;nav("welcome")')
            page.wait_for_selector("text=Where are your games?")
            self.assertNotIn("Vimm", page.content())
            self.assertEqual(0, page.get_by_text("Skip setup").count())
            page.get_by_role("button", name="Skip this step").click()
            page.wait_for_selector("text=Let me look around")
            self.assertIn("3. Scan my computer", page.inner_text("#main"))
            page.evaluate('S.wizStep=0;nav("welcome")')
            page.wait_for_selector("text=Hi, I'm the doctor.")
            self.assertNotIn("Hi, I'm Martin", page.inner_text("#main"))
            # Martin sits on the doctor's desk; petting him wags the tail and moves the head
            page.evaluate('nav("setup")')
            page.wait_for_selector(".desk .sitcat")
            self.assertEqual(3, page.locator(".sitcat .catpart").count())
            page.locator(".sitcat").click(force=True)
            self.assertTrue(page.evaluate('document.querySelector(".sitcat").classList.contains("petting")'))
            self.assertEqual("", page.evaluate("getSelection().toString()"))
            # clicking the doctor in his office repaints him before the page-wide handlers run; that must not leave a bubble by the logo
            page.evaluate("() => { S.visit = false; document.querySelector('.docspot .px.doctor').dispatchEvent(new MouseEvent('click', {bubbles: true})); }")
            for _ in range(3):
                page.locator(".sitcat").click(force=True)
            top = page.evaluate('(()=>{const b=document.querySelector("#bubble");return b?b.getBoundingClientRect().top:999})()')
            self.assertGreater(top, 100)
            page.evaluate('S.visit=false;S.docVisits=0;S.docLast=0;nav("home")')
            page.wait_for_selector("text=Your emulators")
            # the games-folder box never pre-fills anything from this computer
            page.evaluate('S.wizStep=1;nav("welcome")')
            page.wait_for_selector("text=Where are your games?")
            self.assertEqual("", page.input_value("#main input[type=text]"))
            # a doctor who has never scanned offers to scan on his own computer
            page.evaluate('S.wizStep=0;nav("setup")')
            page.wait_for_selector(".pressstart")
            page.evaluate("() => { startVisit(S.doc); }")
            page.wait_for_selector(".docsay")
            for _ in range(40):      # click through his lines until the one about the blank chart
                if "never scanned this computer" in page.inner_text(".docsay"):
                    break
                page.locator(".office").click(position={"x": 20, "y": 200})
                page.wait_for_timeout(350)
            self.assertIn("never scanned this computer", page.inner_text(".docsay"))
            page.evaluate("() => { S.visit = false; }")
            # he really runs it: terminal on the desk, results spoken afterwards (scan answered by a pretend finished scan)
            page.route("**/api/scan_pc", lambda route: route.fulfill(status=200, content_type="application/json", body='{"state":"done","found":{},"emulators":{},"packages":{},"visited":3,"where":"C:\\\\Program Files\\\\Dolphin"}'))
            page.evaluate("() => { window.__scan = 'running'; S.visit = true; doctorAutoScan(document.querySelector('.docsay')).then(() => { window.__scan = 'finished' }); }")
            page.get_by_role("button", name="Run the scan").click()
            page.wait_for_selector(".docterm")
            self.assertIn("DOC-PC", page.inner_text(".docterm"))
            for _ in range(60):
                if page.evaluate("window.__scan") == "finished":
                    break
                page.wait_for_timeout(500)
            self.assertEqual("finished", page.evaluate("window.__scan"))
            self.assertIn("Done!", page.inner_text(".docsay"))
            # the problem-report question: shows what it is, shows exactly what would be sent, and "Not now" closes it
            page.route("**/api/report_decide", lambda route: route.fulfill(status=200, content_type="application/json", body='{"ok": true}'))
            page.route("**/api/report_preview", lambda route: route.fulfill(status=200, content_type="application/json", body='{"text": "{\\"schema\\": \\"legacy_player.report.v1\\"}"}'))
            page.evaluate("() => { showReport({id: 'abcdef123456', kind: 'launch-failed', message: 'The emulator would not start.', mode: 'off'}); }")
            page.wait_for_selector(".modal")
            self.assertIn("Send this report", page.inner_text(".modal"))
            page.get_by_text("See exactly what would be sent").click()
            page.wait_for_selector(".modal pre:visible")
            self.assertIn("legacy_player.report.v1", page.inner_text(".modal pre"))
            page.get_by_text("Not now").click()
            page.wait_for_timeout(300)
            self.assertEqual(0, page.locator(".modal").count())
            page.evaluate('nav("settings")')
            page.wait_for_selector("text=Problem reports")
            page.wait_for_selector("text=In-game overlay")
            self.assertIn("touch grass", page.evaluate('prescription().textContent').lower())
            # the doctor's uninstall dialog asks about the folders he made, and Esc is "Never mind"
            page.evaluate('void retireClinic()')
            page.wait_for_selector(".retire")
            self.assertIn("Start the clean-up", page.inner_text(".retire"))
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            self.assertEqual(0, page.locator(".retire").count())
            # servers page: compact "Right now" panel, no big code card; the name menu has quick actions
            page.evaluate('nav("servers")')
            page.wait_for_selector("#srvlive")
            self.assertIn("Right now", page.inner_text("#srvlive"))
            self.assertNotIn("Make my server code", page.inner_text("#main"))
            page.click("#who")
            page.wait_for_selector("text=Fast start server")
            self.assertIn("Edit profile", page.inner_text("#menubar"))
            self.assertIn("Exit Legacy Player", page.inner_text("#menubar"))
            page.keyboard.press("Escape")
            # the overlay window's own view (last, because it takes over the page)
            page.evaluate('void overlayInit()')
            page.wait_for_selector(".ovl")
            page.wait_for_selector("text=No game was started")          # the overlay draws after it asks the app for its state
            self.assertIn("No game was started", page.inner_text(".ovl"))
            # closing: Martin waves goodbye like a lucky cat, whoever asked to quit (menu or tray)
            page.evaluate('farewell()')
            page.wait_for_selector(".bye .lpaw")
            self.assertIn("Bye bye", page.inner_text(".bye"))
            self.assertEqual(1, page.locator(".bye .lcoin").count())
            import os
            if os.environ.get("LP_SHOT"):
                page.wait_for_timeout(250)
                page.screenshot(path=os.environ["LP_SHOT"])
            browser.close()
        self.assertEqual([], problems)


if __name__ == "__main__":
    unittest.main()
