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

REAL_WHICH = shutil.which                                  # setUp below replaces shutil.which for the whole process
SEVENZ = REAL_WHICH("7z") or REAL_WHICH("7za")

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
        with mock.patch("launcher.setup.shutil.which", side_effect=REAL_WHICH):
            extract_7z(archive, out)
        self.assertTrue(any(out.rglob("retroarch.exe")))

    def test_https_redirect_to_http_on_same_host_is_refused(self):
        from launcher.setup import _SameHostOnly
        import urllib.request
        req = urllib.request.Request("https://buildbot.libretro.com/a.zip")
        with self.assertRaisesRegex(SetupError, "away from https"):
            _SameHostOnly("buildbot.libretro.com").redirect_request(req, None, 302, "Found", {}, "http://buildbot.libretro.com/a.zip")
        ok = _SameHostOnly("buildbot.libretro.com").redirect_request(req, None, 302, "Found", {}, "https://buildbot.libretro.com/b.zip")
        self.assertEqual("https://buildbot.libretro.com/b.zip", ok.full_url)
        allowed = _SameHostOnly("127.0.0.1", allow_http=True).redirect_request(
            urllib.request.Request("http://127.0.0.1/a"), None, 302, "Found", {}, "http://127.0.0.1/b")
        self.assertEqual("http://127.0.0.1/b", allowed.full_url)

    def _fake_tool(self, listing: str, extract_rc: int = 0, list_rc: int = 0, stderr: str = ""):
        import subprocess
        calls = []

        def run(command):
            calls.append(command)
            if command[1] == "l":
                return subprocess.CompletedProcess(command, list_rc, listing, stderr)
            if command[1] == "x":
                if extract_rc == 0:
                    out = Path(command[-1][2:])
                    (out / "RetroArch-Win64").mkdir(parents=True, exist_ok=True)
                    (out / "RetroArch-Win64" / "retroarch.exe").write_text("x")
                return subprocess.CompletedProcess(command, extract_rc, "", stderr)
            raise AssertionError(command)
        return calls, run

    SLT = ("Path = a.7z\nType = 7z\n\n----------\n"
           "Path = RetroArch-Win64\nFolder = +\nAttributes = D\n\n"
           "Path = RetroArch-Win64/retroarch.exe\nFolder = -\nAttributes = A -rwxr-xr-x\n\n")

    def test_7z_is_listed_and_checked_before_anything_is_extracted(self):
        for evil in ("Path = ../../evil.dll\nAttributes = A\n\n", "Path = C:\\Windows\\evil.dll\nAttributes = A\n\n",
                     "Path = /etc/evil\nAttributes = A\n\n", "Path = RetroArch-Win64/link\nAttributes = A lrwxrwxrwx\n\n",
                     "Path = RetroArch-Win64/link2\nSymbolic Link = /etc\n\n"):
            calls, run = self._fake_tool(self.SLT + evil)
            with mock.patch("launcher.setup._seven_zip_tools", return_value=[("7z", "7z")]), \
                    mock.patch("launcher.setup._run_tool", side_effect=run):
                with self.assertRaisesRegex(SetupError, "refused"):
                    extract_7z(self.root / "a.7z", self.root / "out-evil", "RetroArch")
            self.assertEqual(["l"], [c[1] for c in calls], evil)            # never got as far as extracting
        calls, run = self._fake_tool(self.SLT)
        with mock.patch("launcher.setup._seven_zip_tools", return_value=[("7z", "7z")]), \
                mock.patch("launcher.setup._run_tool", side_effect=run):
            extract_7z(self.root / "a.7z", self.root / "out-ok", "RetroArch")
        self.assertTrue((self.root / "out-ok" / "RetroArch-Win64" / "retroarch.exe").is_file())

    def test_7z_tool_failure_reports_its_own_words_and_tar_only_says_7zip_is_needed(self):
        calls, run = self._fake_tool(self.SLT, extract_rc=2, stderr="ERROR: Data Error : retroarch.exe")
        with mock.patch("launcher.setup._seven_zip_tools", return_value=[("7z", "7z")]), \
                mock.patch("launcher.setup._run_tool", side_effect=run):
            with self.assertRaisesRegex(SetupError, "Data Error"):
                extract_7z(self.root / "a.7z", self.root / "out1", "RetroArch")
        import subprocess
        tar_fails = lambda c: subprocess.CompletedProcess(c, 1, "", "tar: Unrecognized archive format")
        with mock.patch("launcher.setup._seven_zip_tools", return_value=[("tar", "tar")]), \
                mock.patch("launcher.setup._run_tool", side_effect=tar_fails):
            with self.assertRaisesRegex(SetupError, "7-Zip is needed to install RetroArch.*Unrecognized archive format"):
                extract_7z(self.root / "a.7z", self.root / "out2", "RetroArch")
        with mock.patch("launcher.setup._seven_zip_tools", return_value=[]):
            with self.assertRaisesRegex(SetupError, "No tool to unpack"):
                extract_7z(self.root / "a.7z", self.root / "out3", "PCSX2")

    @unittest.skipUnless(REAL_WHICH("tar"), "needs tar")
    def test_real_tar_listing_refuses_links_and_escapes(self):
        import io as _io
        import tarfile
        def make(name, members):
            path = self.root / name
            with tarfile.open(path, "w") as t:
                for member, kind in members:
                    info = tarfile.TarInfo(member)
                    if kind == "link":
                        info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                        t.addfile(info)
                    else:
                        info.size = 1
                        t.addfile(info, _io.BytesIO(b"x"))
            return path
        tools = [("tar", REAL_WHICH("tar"))]
        with mock.patch("launcher.setup._seven_zip_tools", return_value=tools):
            for bad in (make("l.tar", [("ok.txt", "f"), ("pw", "link")]), make("e.tar", [("../escape.txt", "f")])):
                out = self.root / ("out-" + bad.stem)
                with self.assertRaisesRegex(SetupError, "refused"):
                    extract_7z(bad, out, "Test")
                self.assertFalse(any(out.rglob("*")), bad)
            good = make("g.tar", [("dir/ok.txt", "f")])
            extract_7z(good, self.root / "out-good", "Test")
            self.assertTrue((self.root / "out-good" / "dir" / "ok.txt").is_file())

    def test_reinstalling_retroarch_keeps_settings_saves_and_bios(self):
        root = self.setup.install_root
        (root / "system").mkdir(parents=True)
        (root / "system" / "scph5501.bin").write_bytes(b"bios")
        (root / "saves").mkdir()
        (root / "saves" / "Game.srm").write_bytes(b"save")
        (root / "retroarch.cfg").write_text("mine")
        (root / "cores").mkdir()
        (root / "cores" / "snes9x_libretro.dll").write_bytes(b"core")           # retroarch.exe itself is gone (quarantined)

        def fake_download(url, dest, **kw):
            Path(dest).write_text('<a href="1.22.2/">' if url.endswith("/stable/") else "7z")

        def fake_extract(archive, staging, what=""):
            (staging / "RetroArch-Win64").mkdir(parents=True)
            (staging / "RetroArch-Win64" / "retroarch.exe").write_text("new")
            (staging / "RetroArch-Win64" / "retroarch.cfg").write_text("default")

        with mock.patch("launcher.setup.platform_key", return_value="windows"), \
                mock.patch("launcher.setup.download", side_effect=fake_download), \
                mock.patch("launcher.setup.extract_7z", side_effect=fake_extract):
            exe = self.setup._install_retroarch()
        self.assertEqual("new", Path(exe).read_text())
        self.assertEqual("mine", (root / "retroarch.cfg").read_text())
        self.assertEqual(b"bios", (root / "system" / "scph5501.bin").read_bytes())
        self.assertEqual(b"save", (root / "saves" / "Game.srm").read_bytes())
        self.assertEqual(b"core", (root / "cores" / "snes9x_libretro.dll").read_bytes())
        self.assertFalse(root.with_name("retroarch.old").exists())

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
