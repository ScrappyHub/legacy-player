import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from launcher import engines
from launcher.app import AppError, LauncherApp
from launcher.installer import EngineInstaller, InstallError, extract_zip_safe


class FakeGitHub(BaseHTTPRequestHandler):
    asset_name = "melonDS-windows-x86_64.zip"
    redirect_offsite = False

    def log_message(self, *a):
        pass

    def do_GET(self):
        host = self.headers.get("Host")
        if self.path.startswith("/repos/"):
            body = json.dumps({"tag_name": "1.0", "html_url": "x", "assets": [
                {"name": FakeGitHub.asset_name, "browser_download_url": f"http://{host}/dl/{FakeGitHub.asset_name}", "size": 0}]}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path.startswith("/dl/"):
            if FakeGitHub.redirect_offsite:
                self.send_response(302); self.send_header("Location", "http://evil.invalid/x.zip"); self.end_headers(); return
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("melonDS/melonDS.exe", b"exe")
                z.writestr("melonDS/readme.txt", b"hi")
            data = buf.getvalue()
            self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_response(404); self.end_headers()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        FakeGitHub.redirect_offsite = False
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

    def test_zip_path_escape_refused(self):
        archive = Path(self.tmp.name) / "bad.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("../escape.txt", b"x")
        with self.assertRaises(InstallError):
            extract_zip_safe(archive, Path(self.tmp.name) / "out")


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
