import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from launcher import engines, installer
from launcher.app import AppError, LauncherApp
from launcher.installer import EngineInstaller, InstallError, extract_zip_safe


class FakeGitHub(BaseHTTPRequestHandler):
    asset_name = "melonDS-windows-x86_64.zip"
    redirect_offsite = False
    contents = "normal"          # "normal" | "empty" (only folder entries) | "with_ini" (also ships a default melonDS.ini)
    tag = "1.0"
    downloads = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        host = self.headers.get("Host")
        if self.path.startswith("/repos/"):
            body = json.dumps({"tag_name": FakeGitHub.tag, "html_url": "x", "assets": [
                {"name": FakeGitHub.asset_name, "browser_download_url": f"http://{host}/dl/{FakeGitHub.asset_name}", "size": 0}]}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path.startswith("/dl/"):
            if FakeGitHub.redirect_offsite:
                self.send_response(302); self.send_header("Location", "http://evil.invalid/x.zip"); self.end_headers(); return
            FakeGitHub.downloads += 1
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                if FakeGitHub.contents == "empty":
                    z.writestr("melonDS/", b"")
                    z.writestr("melonDS/docs/", b"")
                else:
                    z.writestr("melonDS/melonDS.exe", b"exe")
                    z.writestr("melonDS/readme.txt", b"hi")
                    if FakeGitHub.contents == "with_ini":
                        z.writestr("melonDS/melonDS.ini", b"default")
                        z.writestr("melonDS/saves/", b"")
            data = buf.getvalue()
            self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_response(404); self.end_headers()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        FakeGitHub.redirect_offsite = False
        FakeGitHub.contents, FakeGitHub.tag, FakeGitHub.downloads = "normal", "1.0", 0
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.inst = EngineInstaller(Path(self.tmp.name) / "emulators", api_base=self.base, hosts={"127.0.0.1"}, allow_http=True)

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.tmp.cleanup()

    def test_requires_consent(self):
        with self.assertRaisesRegex(InstallError, "Downloads are off"):
            self.inst.start("melonds", consent=False)
        with self.assertRaisesRegex(InstallError, "official page"):
            self.inst.start("dolphin", consent=True)

    def test_downloads_and_unpacks_into_own_folder(self):
        self.inst.start("melonds", consent=True, run_inline=True)
        snap = self.inst.snapshot()
        self.assertEqual("done", snap["state"], snap)
        self.assertTrue((Path(self.tmp.name) / "emulators" / "melonds" / "melonDS.exe").is_file())

    def test_refuses_offsite_redirect_and_unknown_asset(self):
        FakeGitHub.redirect_offsite = True
        self.inst.start("melonds", consent=True, run_inline=True)
        self.assertEqual("error", self.inst.snapshot()["state"])
        self.assertIn("refused", self.inst.snapshot()["error"])
        FakeGitHub.redirect_offsite = False
        FakeGitHub.asset_name = "something-else.zip"
        try:
            self.inst.start("melonds", consent=True, run_inline=True)
            self.assertIn("no Windows package", self.inst.snapshot()["error"])
        finally:
            FakeGitHub.asset_name = "melonDS-windows-x86_64.zip"

    def test_install_all_fetches_each_missing_engine_in_turn(self):
        self.inst.start_many(["melonds", "dolphin", "nope"], consent=True, run_inline=True)
        snap = self.inst.snapshot()
        self.assertEqual("done", snap["state"], snap)
        self.assertTrue((Path(self.tmp.name) / "emulators" / "melonds" / "melonDS.exe").is_file())
        with self.assertRaisesRegex(InstallError, "Nothing to fetch"):
            self.inst.start_many(["dolphin"], consent=True)

    # --- updates keep what the player has in the engine's folder --------------------------------------------
    def _old_install(self):
        dest = Path(self.tmp.name) / "emulators" / "melonds"
        (dest / "saves").mkdir(parents=True)
        (dest / "melonDS.exe").write_bytes(b"old exe")
        (dest / "readme.txt").write_bytes(b"old readme")
        (dest / "melonDS.ini").write_bytes(b"mine")                       # settings (keep-list)
        (dest / "saves" / "game.sav").write_bytes(b"progress")            # a folder the package also ships (empty)
        (dest / "firmware.bin").write_bytes(b"fw")                         # not in the package at all
        (dest / "dev_hdd0" / "game" / "BLUS1").mkdir(parents=True)         # RPCS3-style installed game: not in the package
        (dest / "dev_hdd0" / "game" / "BLUS1" / "EBOOT.BIN").write_bytes(b"game")
        return dest

    def test_update_carries_over_everything_the_package_does_not_ship(self):
        FakeGitHub.contents = "with_ini"
        dest = self._old_install()
        self.inst.start("melonds", consent=True, run_inline=True)
        snap = self.inst.snapshot()
        self.assertEqual("done", snap["state"], snap)
        self.assertEqual(b"exe", (dest / "melonDS.exe").read_bytes())             # program files come from the package
        self.assertEqual(b"hi", (dest / "readme.txt").read_bytes())
        self.assertEqual(b"mine", (dest / "melonDS.ini").read_bytes())            # the player's settings win
        self.assertEqual(b"progress", (dest / "saves" / "game.sav").read_bytes())
        self.assertEqual(b"fw", (dest / "firmware.bin").read_bytes())
        self.assertEqual(b"game", (dest / "dev_hdd0" / "game" / "BLUS1" / "EBOOT.BIN").read_bytes())
        self.assertFalse(dest.with_name("melonds.old").exists())
        self.assertFalse(any(dest.rglob("*.lp-new")))
        self.assertEqual("1.0", installer.installed_version(dest))
        self.assertEqual({"melonds": "installed"}, snap["results"])

    def test_update_everything_skips_an_engine_already_on_the_latest_release(self):
        self.inst.start("melonds", consent=True, run_inline=True)
        self.assertEqual(1, FakeGitHub.downloads)
        job = self.inst.start_many(["melonds"], consent=True, run_inline=True)
        self.assertEqual("done", job["state"], job)
        self.assertEqual(["melonds"], job["up_to_date"])
        self.assertEqual({"melonds": "up_to_date"}, job["results"])
        self.assertEqual("Already up to date", job["step"])
        self.assertEqual(1, FakeGitHub.downloads)                                 # nothing downloaded again
        FakeGitHub.tag = "1.1"
        job = self.inst.start_many(["melonds"], consent=True, run_inline=True)
        self.assertEqual({"melonds": "installed"}, job["results"])
        self.assertEqual(2, FakeGitHub.downloads)
        self.assertEqual("1.1", installer.installed_version(Path(self.tmp.name) / "emulators" / "melonds"))

    def test_archive_that_unpacks_to_nothing_leaves_the_install_alone(self):
        FakeGitHub.contents = "empty"
        dest = self._old_install()
        before = sorted(str(p.relative_to(dest)) for p in dest.rglob("*"))
        self.inst.start("melonds", consent=True, run_inline=True)
        snap = self.inst.snapshot()
        self.assertEqual("error", snap["state"])
        self.assertIn("unpacked to nothing", snap["error"])
        self.assertEqual(before, sorted(str(p.relative_to(dest)) for p in dest.rglob("*")))
        self.assertEqual(b"old exe", (dest / "melonDS.exe").read_bytes())
        self.assertFalse(dest.with_name("melonds.old").exists())

    def test_running_emulator_gets_a_close_it_first_message(self):
        dest = self._old_install()
        real_rename = os.rename

        def locked(src, dst, *a, **kw):
            if Path(src) == dest:
                raise PermissionError(13, "Access is denied", str(src))
            return real_rename(src, dst, *a, **kw)
        with mock.patch("launcher.setup.os.rename", side_effect=locked):
            self.inst.start("melonds", consent=True, run_inline=True)
        snap = self.inst.snapshot()
        self.assertEqual("error", snap["state"])
        self.assertIn("Close melonDS first", snap["error"])
        self.assertEqual(b"old exe", (dest / "melonDS.exe").read_bytes())

    def test_failure_after_moving_aside_puts_the_old_folder_back(self):
        dest = self._old_install()
        before = {str(p.relative_to(dest)): p.read_bytes() for p in dest.rglob("*") if p.is_file()}
        real_rename = os.rename
        calls = {"n": 0}

        def flaky(src, dst, *a, **kw):                   # the carry-over fails part-way through
            if Path(src).parent == dest.with_name("melonds.old"):
                calls["n"] += 1
                if calls["n"] == 3:
                    raise OSError(28, "No space left on device")
            return real_rename(src, dst, *a, **kw)
        with mock.patch("launcher.setup.os.rename", side_effect=flaky):
            self.inst.start("melonds", consent=True, run_inline=True)
        snap = self.inst.snapshot()
        self.assertEqual("error", snap["state"], snap)
        self.assertEqual(before, {str(p.relative_to(dest)): p.read_bytes() for p in dest.rglob("*") if p.is_file()})
        self.assertFalse(dest.with_name("melonds.old").exists())

    def test_leftover_old_folder_is_merged_back_not_deleted(self):
        dest = Path(self.tmp.name) / "emulators" / "melonds"
        old = dest.with_name("melonds.old")
        (old / "saves").mkdir(parents=True)
        (old / "saves" / "only-here.sav").write_bytes(b"precious")
        dest.mkdir(parents=True)
        (dest / "melonDS.exe").write_bytes(b"x")
        self.inst.start("melonds", consent=True, run_inline=True)
        self.assertEqual("done", self.inst.snapshot()["state"], self.inst.snapshot())
        self.assertEqual(b"precious", (dest / "saves" / "only-here.sav").read_bytes())
        self.assertFalse(old.exists())
        # an .old with no install beside it is put back as the install before anything else happens
        shutil.rmtree(dest)
        (old / "keep.txt").parent.mkdir(parents=True)
        (old / "keep.txt").write_bytes(b"k")
        self.inst.start("melonds", consent=True, run_inline=True)
        self.assertEqual(b"k", (dest / "keep.txt").read_bytes())

    def test_zip_path_escape_refused(self):
        archive = Path(self.tmp.name) / "bad.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("../escape.txt", b"x")
        with self.assertRaises(InstallError):
            extract_zip_safe(archive, Path(self.tmp.name) / "out")


@unittest.skipIf(sys.platform == "win32", "POSIX signals")
class CloseTests(unittest.TestCase):
    def test_a_game_that_ignores_the_polite_close_is_killed_and_collected(self):
        import subprocess
        import time
        from launcher import emulators
        child = subprocess.Popen([sys.executable, "-c", "import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                                  "print('ready', flush=True)\ntime.sleep(60)"], stdout=subprocess.PIPE)
        self.addCleanup(lambda: child.poll() is None and child.kill())
        child.stdout.readline()                                # SIGTERM is ignored from here on
        child.stdout.close()
        started = time.time()
        emulators.close_pid(child.pid, grace=0.5)
        self.assertLess(time.time() - started, 5)
        self.assertFalse(emulators._alive(child.pid))
        with self.assertRaises(ChildProcessError):             # already collected: no zombie left behind
            os.waitpid(child.pid, os.WNOHANG)
        child.poll()

    def test_zombie_does_not_count_as_running(self):
        import subprocess
        import time
        from launcher import emulators
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        time.sleep(0.5)                                        # it has exited but nobody collected it yet
        self.assertFalse(emulators._alive(child.pid))
        child.poll()


class ScanTests(unittest.TestCase):
    def test_scan_finds_exe_in_extra_root_and_bios_by_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "PCSX2 2.4").mkdir()
            (root / "PCSX2 2.4" / "pcsx2-qt.exe").write_text("x")
            found = engines.scan_computer({"pcsx2": ["pcsx2-qt.exe"]}, [root])
            self.assertEqual(str(root / "PCSX2 2.4" / "pcsx2-qt.exe"), found["pcsx2"])
            (root / "bios").mkdir()
            (root / "bios" / "scph39001.bin").write_bytes(b"\0" * (4 * 1024 * 1024))
            (root / "bios" / "wrongsize.bin").write_bytes(b"\0" * 100)
            hits = engines.find_bios("ps2", [root])
            self.assertEqual([str(root / "bios" / "scph39001.bin")], [h["path"] for h in hits])

    def test_app_gates_internet_and_scan_on_consent(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp) / "data")
            with self.assertRaisesRegex(AppError, "Please confirm"):
                app.api_engines_scan({})
            with self.assertRaisesRegex(AppError, "downloads are off"):
                app.api_engines_install({"engine": "melonds", "confirm": True})
            with self.assertRaisesRegex(AppError, "downloads are off"):
                app.api_setup_install({"what": "all", "confirm": True})
            app.catalog.set_setting("allow_internet", True)
            with self.assertRaisesRegex(AppError, "confirm"):
                app.api_engines_install({"engine": "melonds"})
            payload = app.api_engines({})
            self.assertEqual(len(engines.ENGINES), len(payload["engines"]))
            credits = app.api_credits({})
            self.assertTrue(all(r["homepage"].startswith("https://") for r in credits["engines"]))
            self.assertFalse(next(r for r in credits["engines"] if r["id"] == "duckstation")["redistributable"])
            self.assertTrue(all(b["how"] for b in payload["bios"]))


if __name__ == "__main__":
    unittest.main()
