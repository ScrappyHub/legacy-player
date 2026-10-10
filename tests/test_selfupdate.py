"""Legacy Player updating itself: a git copy pulls and restarts; the Windows app downloads, checks and swaps."""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from launcher import selfupdate
from launcher.app import AppError, LauncherApp
from launcher.installer import InstallError

GIT = shutil.which("git")


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


def write_version(folder: Path, v: str):
    (folder / "launcher").mkdir(parents=True, exist_ok=True)
    (folder / "launcher" / "version.py").write_text(f'VERSION = "{v}"\n', encoding="utf-8")


@unittest.skipUnless(GIT, "git is not installed")
class GitCopy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        upstream = self.tmp / "upstream"
        upstream.mkdir()
        git(upstream, "init", "-q", "-b", "main")
        write_version(upstream, selfupdate.VERSION)
        git(upstream, "add", "-A")
        git(upstream, "commit", "-qm", "one")
        git(self.tmp, "clone", "-q", str(upstream), "copy")
        self.upstream, self.copy = upstream, self.tmp / "copy"
        self.patch = mock.patch.object(selfupdate, "ROOT", self.copy)
        self.patch.start()
        self.up = selfupdate.SelfUpdate(self.tmp / "data")

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_up_to_date_then_behind_then_pulled_and_ready(self):
        self.assertEqual("git", selfupdate.mode())
        self.assertFalse(self.up.check()["newer"])
        write_version(self.upstream, "99.0.0")
        git(self.upstream, "commit", "-qam", "two")
        info = self.up.check()
        self.assertTrue(info["newer"])
        self.assertFalse(info["restart_only"])
        snap = self.up.prepare(info)
        self.assertEqual("ready", snap["state"])
        self.assertEqual("99.0.0", selfupdate.version_on_disk())
        plan = self.up.restart_plan()
        self.assertEqual(sys.executable, plan[0])
        self.assertIn("-m", plan)
        self.assertIn("launcher", plan)
        self.assertEqual(str(os.getpid()), plan[3])

    def test_files_already_pulled_only_need_a_restart(self):
        write_version(self.copy, "99.0.0")
        info = self.up.check()
        self.assertTrue(info["newer"])
        self.assertTrue(info["restart_only"])
        self.assertEqual("ready", self.up.prepare(info)["state"])

    def test_local_changes_that_block_the_pull_are_explained(self):
        write_version(self.upstream, "99.0.0")
        git(self.upstream, "commit", "-qam", "two")
        write_version(self.copy, "5.0.0")                     # the player edited the same file
        git(self.copy, "commit", "-qam", "mine")
        with self.assertRaises(InstallError) as ctx:
            self.up.prepare({"mode": "git", "newer": True, "restart_only": False, "latest": "1", "message": ""})
        self.assertIn("folder", str(ctx.exception))
        self.assertEqual("problem", self.up.snapshot()["state"])


def fake_release(tmp: Path, tag="v99.0.0", damage=False):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("LegacyPlayer.exe", b"MZ new program")
        z.writestr("_internal/lib.dll", b"lib")
    data = buf.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    files = {"zip": data, "sum": f"{digest}  LegacyPlayer-99.0.0-win64.zip\n".encode()}
    if damage:
        files["zip"] = data + b"x"
    rel = {"tag": tag, "page": "p", "assets": [
        {"name": "LegacyPlayer-99.0.0-win64.zip", "url": "https://github.com/z", "size": len(data), "sha256": ""},
        {"name": "LegacyPlayer-99.0.0-win64.zip.sha256", "url": "https://github.com/s", "size": 90, "sha256": ""}]}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(url, hosts, allow_http=False, timeout=30):
        return Resp(files["zip"] if url.endswith("/z") else files["sum"])
    return rel, opener


class WindowsApp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.up = selfupdate.SelfUpdate(self.tmp / "data")
        self.up.mode = lambda: "exe"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_download_is_checked_unpacked_and_planned(self):
        rel, opener = fake_release(self.tmp)
        with mock.patch.object(selfupdate, "_open", opener), mock.patch.object(selfupdate.sys, "platform", "win32"), \
             mock.patch.object(selfupdate.sys, "executable", str(self.tmp / "app" / "LegacyPlayer.exe")):
            snap = self.up.prepare({"mode": "exe", "newer": True, "latest": rel["tag"], "release": rel, "message": ""})
            self.assertEqual("ready", snap["state"])
            stage = Path(self.up.staged["stage"])
            self.assertTrue((stage / "LegacyPlayer.exe").exists())
            self.assertTrue((stage / "_internal" / "lib.dll").exists())
            self.assertEqual(str((self.tmp / "app").resolve()), self.up.staged["dest"])
            plan = self.up.restart_plan()
        self.assertEqual("powershell", plan[0])
        self.assertIn("-WaitPid", plan)
        self.assertIn(str(os.getpid()), plan)
        self.assertIn("v99.0.0", plan)
        script = Path(plan[plan.index("-File") + 1]).read_text(encoding="utf-8")
        self.assertIn("Wait-Process", script)
        self.assertIn("Start-Process", script)

    def test_a_damaged_download_installs_nothing(self):
        rel, opener = fake_release(self.tmp, damage=True)
        with mock.patch.object(selfupdate, "_open", opener), mock.patch.object(selfupdate.sys, "platform", "win32"):
            with self.assertRaises(InstallError):
                self.up.prepare({"mode": "exe", "newer": True, "latest": rel["tag"], "release": rel, "message": ""})
        self.assertIsNone(self.up.staged)
        self.assertFalse((self.tmp / "data" / "update").exists())

    def test_newer_is_by_number(self):
        with mock.patch.object(selfupdate, "latest_release", return_value={"tag": "v0.0.1", "assets": [], "page": ""}):
            self.assertFalse(self.up.check()["newer"])
        with mock.patch.object(selfupdate, "latest_release", return_value={"tag": "v999.0.0", "assets": [], "page": ""}):
            self.assertTrue(self.up.check()["newer"])


class RelaunchHelper(unittest.TestCase):
    def test_waits_for_the_old_app_then_starts_the_new_one(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            old = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
            marker = tmp / "started.txt"
            started = time.time()
            subprocess.Popen([sys.executable, "-c", selfupdate.RELAUNCH_PY, str(old.pid), str(tmp),
                              sys.executable, "-c", f"open(r'{marker}','w').write('yes')"])
            old.wait()
            for _ in range(80):
                if marker.exists():
                    break
                time.sleep(0.1)
            self.assertTrue(marker.exists())
            self.assertGreater(time.time() - started, 1.4)       # not before the old one was gone
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class AppSide(unittest.TestCase):
    def setUp(self):
        self.app = LauncherApp(Path(tempfile.mkdtemp()))

    def test_checking_needs_the_internet_setting_unless_the_folder_is_already_newer(self):
        with mock.patch.object(self.app.self_update, "mode", lambda: "exe"):
            out = self.app.api_check_update({})
        self.assertFalse(out["ok"])
        with mock.patch.object(self.app.self_update, "mode", lambda: "git"), \
             mock.patch.object(selfupdate, "version_on_disk", return_value="99.0.0"):
            out = self.app.api_check_update({})
        self.assertTrue(out["ok"])
        self.assertTrue(out["newer"])
        self.assertTrue(out["restart_only"])

    def test_restart_hands_off_and_quits(self):
        up = self.app.self_update
        up.staged = {"mode": "git", "version": "99.0.0"}
        with mock.patch.object(up, "launch_helper") as launch:
            out = self.app.api_app_update({"action": "restart", "confirm": True})
        launch.assert_called_once()
        self.assertTrue(out["restarting"])
        self.assertTrue(self.app.quit_requested)


if __name__ == "__main__":
    unittest.main()
