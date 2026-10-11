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
        (self.tmp / "app").mkdir()
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
        self.assertEqual(str((self.tmp / "app" / "LegacyPlayer.exe").resolve()), plan[plan.index("-Exe") + 1])   # exactly the running file
        self.assertTrue(plan[plan.index("-Result") + 1].endswith("result.json"))
        script = Path(plan[plan.index("-File") + 1]).read_text(encoding="utf-8")
        self.assertIn("Wait-Process", script)
        self.assertIn("Process]::Start", script)

    def test_a_folder_it_cannot_write_to_is_said_before_downloading(self):
        rel, opener = fake_release(self.tmp)
        (self.tmp / "app").mkdir()
        fetched = []
        with mock.patch.object(selfupdate, "_open", lambda *a, **k: fetched.append(a) or opener(*a, **k)), \
             mock.patch.object(selfupdate.sys, "platform", "win32"), \
             mock.patch.object(selfupdate.sys, "executable", str(self.tmp / "app" / "LegacyPlayer.exe")), \
             mock.patch.object(selfupdate, "folder_writable", return_value=False):
            with self.assertRaises(InstallError) as ctx:
                self.up.prepare({"mode": "exe", "newer": True, "latest": rel["tag"], "release": rel, "message": ""})
        self.assertIn("Program Files", str(ctx.exception))
        self.assertEqual([], fetched)                                         # nothing was downloaded
        self.assertEqual("problem", self.up.snapshot()["state"])

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


class ApplyScript(unittest.TestCase):
    """The PowerShell helper that swaps the Windows app's files (only its text can be checked off Windows)."""
    S = selfupdate.APPLY_PS1

    def test_only_the_copied_files_lose_the_download_mark(self):
        self.assertNotIn("Get-ChildItem $Dest -Recurse", self.S)         # never the whole folder (it may be Downloads)
        self.assertNotRegex(self.S, r"Get-ChildItem[^\n]*\$Dest[^\n]*\|\s*Unblock-File")
        self.assertIn("Unblock-File -LiteralPath $f", self.S)
        self.assertIn("$copied += $Exe", self.S)

    def test_paths_are_literal(self):
        for cmd in ("Copy-Item", "Remove-Item", "Set-Content", "Add-Content", "Unblock-File"):
            for line in self.S.splitlines():
                if cmd + " " in line:
                    self.assertIn("-LiteralPath", line, line)
        self.assertNotIn("Start-Process", self.S)                        # -FilePath would treat [ ] as wildcards

    def test_stops_quietly_and_waits_for_every_copy_of_the_exe(self):
        for line in self.S.splitlines():
            if "Stop-Process" in line:
                self.assertIn("-ErrorAction SilentlyContinue", line, line)
        self.assertIn("$_.Path -eq $Exe", self.S)
        self.assertIn("while ((Ours)", self.S)

    def test_replaces_exactly_the_running_exe_and_writes_a_result(self):
        self.assertIn("[string]$Exe", self.S)
        self.assertIn("-Destination $Exe", self.S)
        self.assertIn("if ($inInstalled)", self.S)                       # extra files only in the installer's folder
        self.assertIn("$Result", self.S)
        self.assertIn("ConvertTo-Json", self.S)


class UpdateResult(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, payload, bom=True):
        import json
        folder = self.tmp / "update"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "result.json").write_text(json.dumps(payload), encoding="utf-8-sig" if bom else "utf-8")

    def test_the_result_is_shown_once_by_the_status_call(self):
        self.write({"ok": True, "tag": "v" + selfupdate.VERSION, "error": "", "at": 1})
        app = LauncherApp(self.tmp)
        first = app.api_app_update({"action": "status"})
        self.assertEqual({"ok": True, "tag": "v" + selfupdate.VERSION, "error": ""}, first["last_result"])
        self.assertNotIn("last_result", app.api_app_update({"action": "status"}))
        self.assertFalse((self.tmp / "update" / "result.json").exists())
        for key in ("state", "message", "latest", "done", "total"):
            self.assertIn(key, first)

    def test_a_failed_update_says_why(self):
        self.write({"ok": False, "tag": "v99.0.0", "error": "Access is denied", "at": 1})
        out = LauncherApp(self.tmp).api_app_update({"action": "status"})["last_result"]
        self.assertFalse(out["ok"])
        self.assertIn("Access is denied", out["error"])

    def test_still_the_old_version_is_not_a_success(self):
        self.write({"ok": True, "tag": "v99.0.0", "error": "", "at": 1}, bom=False)
        out = selfupdate.SelfUpdate(self.tmp).take_last_result()
        self.assertFalse(out["ok"])
        self.assertIn(selfupdate.VERSION, out["error"])

    def test_a_git_restart_leaves_a_result_and_starts_the_helper_cleanly(self):
        up = selfupdate.SelfUpdate(self.tmp)
        up.staged = {"mode": "git", "version": selfupdate.VERSION}
        with mock.patch.object(selfupdate.subprocess, "Popen") as popen, \
             mock.patch.dict(os.environ, {"_PYI_APPLICATION_HOME_DIR": "x", "_MEIPASS2": "y"}):
            up.launch_helper()
        kwargs = popen.call_args.kwargs
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", kwargs["env"])
        self.assertNotIn("_MEIPASS2", kwargs["env"])
        self.assertEqual("1", kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"])
        self.assertIn("--log", popen.call_args.args[0])
        self.assertTrue(selfupdate.SelfUpdate(self.tmp).take_last_result()["ok"])

    def test_the_exe_helper_never_runs_in_the_temporary_folder(self):
        up = selfupdate.SelfUpdate(self.tmp)
        up.staged = {"mode": "exe", "version": "v1", "stage": str(self.tmp / "update" / "new"), "dest": str(self.tmp),
                     "exe": str(self.tmp / "x.exe")}
        with mock.patch.object(selfupdate.subprocess, "Popen") as popen:
            up.launch_helper()
        self.assertEqual(str(self.tmp / "update"), popen.call_args.kwargs["cwd"])
        self.assertNotEqual(str(selfupdate.ROOT), popen.call_args.kwargs["cwd"])
        self.assertEqual("1", popen.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"])


class RelaunchEndsAStuckApp(unittest.TestCase):
    def test_a_stuck_old_app_is_ended_and_the_new_one_logs_to_a_file(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            old = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            log = tmp / "launcher.log"
            env = {**os.environ, "LP_RELAUNCH_WAIT": "1"}
            subprocess.Popen([sys.executable, "-c", selfupdate.RELAUNCH_PY, str(old.pid), str(tmp), "--log", str(log),
                              sys.executable, "-c", "print('new one here')"], env=env)
            self.assertIsNotNone(old.wait(timeout=10))                       # ended after the (shortened) wait
            for _ in range(100):
                if log.exists() and "new one here" in log.read_text():
                    break
                time.sleep(0.1)
            self.assertIn("new one here", log.read_text())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class CheckRunsInTheBackground(unittest.TestCase):
    def setUp(self):
        self.app = LauncherApp(Path(tempfile.mkdtemp()))
        self.app.catalog.set_setting("allow_internet", True)

    def wait_done(self):
        for _ in range(100):
            snap = self.app.api_app_update({"action": "status"})
            if snap["state"] != "checking":
                return snap
            time.sleep(0.05)
        return snap

    def test_check_answers_at_once_and_never_holds_the_app_lock(self):
        import threading
        gate = threading.Event()

        def slow_check():
            gate.wait(5)
            return {"mode": "git", "newer": True, "restart_only": False, "latest": "3 new changes", "message": "behind"}
        up = self.app.self_update
        with mock.patch.object(up, "mode", lambda: "git"), mock.patch.object(up, "check", slow_check):
            with self.app.api_lock:
                out = self.app.api_check_update({})
            self.assertEqual("checking", out["state"])
            self.assertTrue(out["ok"])
            got = []
            t = threading.Thread(target=lambda: got.append(self.app.api_lock.acquire(timeout=2)))
            t.start()
            t.join()
            self.assertTrue(got[0])                                           # the lock is free while GitHub/git is slow
            self.assertEqual("checking", self.app.api_app_update({"action": "check"})["state"])   # one check at a time
            gate.set()
            snap = self.wait_done()
        self.assertEqual("idle", snap["state"])
        self.assertTrue(snap["newer"])
        self.assertEqual("3 new changes", snap["latest"])
        self.assertFalse(snap["restart_only"])

    def test_a_failed_check_is_a_problem(self):
        up = self.app.self_update
        with mock.patch.object(up, "mode", lambda: "exe"), \
             mock.patch.object(up, "check", side_effect=InstallError("GitHub did not answer")):
            self.assertEqual("checking", self.app.api_check_update({})["state"])
            snap = self.wait_done()
        self.assertEqual("problem", snap["state"])
        self.assertIn("GitHub did not answer", snap["message"])

    def test_restart_closes_everything_before_saying_quit(self):
        up = self.app.self_update
        up.staged = {"mode": "git", "version": "99.0.0"}
        seen = []
        with mock.patch.object(up, "launch_helper"), \
             mock.patch.object(self.app, "shutdown", lambda: seen.append(self.app.quit_requested)):
            self.app.api_app_update({"action": "restart", "confirm": True})
        self.assertEqual([False], seen)                 # the web server stops on quit_requested: it must come last
        self.assertTrue(self.app.quit_requested)


if __name__ == "__main__":
    unittest.main()
