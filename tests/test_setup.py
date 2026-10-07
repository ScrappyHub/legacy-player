import io
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SEVENZ = shutil.which("7z") or shutil.which("7za")      # found once, at import: another test may change PATH later

from launcher.app import LauncherApp
from launcher.setup import (
    Setup, SetupError, core_filename, core_url, download, extract_7z, latest_stable, platform_key,
)


class FakeBuildbot(BaseHTTPRequestHandler):
    mode = "ok"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.endswith("/redirect.zip"):
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/evil.zip")
            self.end_headers()
            return
        if self.path.endswith(".zip"):
            stem = self.path.rsplit("/", 1)[-1][:-4]
            name = stem if "." in stem else stem
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                if name == "info":
                    z.writestr("nestopia_libretro.info", 'savestate = "true"\nsavestate_features = "deterministic"\n')
                    z.writestr("evil/../x.txt", b"ignored")
                else:
                    member = "wrong.bin" if FakeBuildbot.mode == "wrong" else name
                    z.writestr(member, b"core-bytes")
            data = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(404)
        self.end_headers()


class SetupTests(unittest.TestCase):
    def setUp(self):
        _p = mock.patch("launcher.emulators.shutil.which", return_value=None)   # a RetroArch installed on this computer must not change the result
        _p.start()
        self.addCleanup(_p.stop)
        FakeBuildbot.mode = "ok"
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeBuildbot)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exe = self.root / "ra" / ("retroarch.exe" if sys.platform == "win32" else "retroarch")
        self.exe.parent.mkdir(parents=True)
        self.exe.write_text("x")
        self.paths = []
        self.setup = Setup(self.root / "data", lambda: str(self.exe), self.paths.append,
                           base=self.base, allowed_host="127.0.0.1", allow_http=True)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def test_url_and_filename_patterns(self):
        self.assertEqual("https://buildbot.libretro.com/nightly/windows/x86_64/latest/snes9x_libretro.dll.zip", core_url("snes9x_libretro", plat="windows"))
        self.assertTrue(core_url("mgba_libretro", plat="linux").endswith("/nightly/linux/x86_64/latest/mgba_libretro.so.zip"))
        self.assertEqual("mgba_libretro.dll", core_filename("mgba_libretro", "windows"))
        with self.assertRaises(SetupError):
            core_url("x", plat="mac")

    def test_check_reports_missing_cores(self):
        report = self.setup.check(None)
        self.assertTrue(report["retroarch"]["installed"])
        self.assertIn("snes9x_libretro", report["cores_missing"])
        self.assertFalse(report["dolphin"]["installed"])

    def test_installs_missing_cores_into_cores_folder(self):
        job = self.setup.start("cores", run_inline=True)
        self.assertEqual("done", job["state"], job)
        cores = self.exe.parent / "cores"
        self.assertTrue((cores / core_filename("snes9x_libretro")).is_file())
        self.assertEqual([], self.setup.check(None)["cores_missing"])
        self.assertEqual(b"core-bytes", (cores / core_filename("mgba_libretro")).read_bytes())

    def test_wrong_archive_contents_are_refused(self):
        FakeBuildbot.mode = "wrong"
        job = self.setup.start("cores", run_inline=True)
        self.assertEqual("error", job["state"])
        self.assertIn("did not contain", job["error"])
        self.assertFalse((self.exe.parent / "cores").exists() and any((self.exe.parent / "cores").iterdir()))

    def test_download_rules(self):
        dest = self.root / "f"
        with self.assertRaisesRegex(SetupError, "only allowed"):
            download("https://evil.example/x.zip", dest, max_bytes=10)
        with self.assertRaisesRegex(SetupError, "only allowed"):
            download(f"{self.base}/x.zip", dest, max_bytes=10)  # http without opt-in, wrong host
        with self.assertRaisesRegex(SetupError, "larger than expected"):
            download(f"{self.base}/a/big.zip", dest, max_bytes=5, allowed_host="127.0.0.1", allow_http=True)
        with self.assertRaisesRegex(SetupError, "different site"):
            download(f"{self.base}/a/redirect.zip", dest, max_bytes=1000, allowed_host="127.0.0.1", allow_http=True)

    def test_latest_stable_parsing(self):
        html = '<a href="1.9.0/">1.9.0/</a><a href="1.22.2/">x</a><a href="1.10.3/">y</a>'
        self.assertEqual("1.22.2", latest_stable(html))
        self.assertEqual("1.22.2", latest_stable(None))

    def test_only_one_install_at_a_time(self):
        self.setup.job["state"] = "running"
        with self.assertRaisesRegex(SetupError, "already running"):
            self.setup.start("cores")

    @unittest.skipUnless(SEVENZ, "needs a 7-Zip tool")
    def test_extract_7z_round_trip(self):
        import subprocess
        src = self.root / "src"; src.mkdir()
        (src / "retroarch.exe").write_text("x")
        archive = self.root / "a.7z"
        subprocess.run([SEVENZ, "a", str(archive), str(src / "retroarch.exe")], check=True, capture_output=True)
        out = self.root / "out"
        extract_7z(archive, out)
        self.assertTrue(any(out.rglob("retroarch.exe")))

    def test_app_reports_setup_status_without_downloading(self):
        with tempfile.TemporaryDirectory() as d:
            app = LauncherApp(Path(d))
            status = app.api_setup_status({})
            self.assertFalse(status["retroarch"]["installed"])
            self.assertEqual(platform_key(), status["platform"])
            self.assertEqual("idle", status["job"]["state"])


    def test_install_cores_also_installs_info_and_reports_netplay_ready(self):
        self.setup.start("cores", run_inline=True)
        self.assertEqual(self.setup.snapshot()["state"], "done", self.setup.snapshot())
        status = self.setup.check(None)
        self.assertTrue(status["info_installed"])
        nes = next(c for c in status["cores"] if c["wanted"] == "nestopia_libretro")
        self.assertTrue(nes["netplay_ready"])
        self.assertFalse((self.exe.parent / "info" / "x.txt").exists())


if __name__ == "__main__":
    unittest.main()
