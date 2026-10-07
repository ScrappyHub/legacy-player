"""Backend actions that had no direct test: doctor, specs, scans, update check, covers, save folders,
the network-test state, and that starting/stopping the server no longer freezes everything else."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from launcher.app import AppError, LauncherApp


def make_app():
    base = Path(tempfile.mkdtemp())
    (base / "games" / "NES").mkdir(parents=True)
    (base / "games" / "NES" / "Test Game (USA).nes").write_bytes(b"NES\x1a" + b"0" * 64)
    app = LauncherApp(base / "data")
    app.api_roots({"roots": [str(base / "games")]})
    app.rescan()
    return app, base


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.app, self.base = make_app()

    def test_doctor_reports_and_dismiss_round_trips(self):
        report = self.app.api_doctor({})
        self.assertIsInstance(report, dict)
        self.assertIn("issues", report)
        issues = report["issues"]
        if issues:
            key = issues[0]["key"]
            after = self.app.api_doctor_dismiss({"key": key})
            self.assertIn(key, self.app.catalog.data["doctor_dismissed"])
            self.app.api_doctor_dismiss({"key": key, "undo": True})
            self.assertNotIn(key, self.app.catalog.data["doctor_dismissed"])
            self.assertIsInstance(after, dict)

    def test_dismiss_key_is_clipped(self):
        self.app.api_doctor_dismiss({"key": "x" * 500})
        self.assertTrue(all(len(k) <= 40 for k in self.app.catalog.data["doctor_dismissed"]))


class SpecsAndNetworkTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()

    def test_specs_are_cached_until_refresh(self):
        first = self.app.api_specs({})
        self.assertTrue(first["os"])
        self.assertIs(first, self.app.api_specs({}))
        self.assertIsNot(first, self.app.api_specs({"refresh": True}))

    def test_network_last_before_any_test(self):
        got = self.app.api_network_last({})
        self.assertIsNone(got["at"])
        self.assertFalse(got["running"])


class UpdateAndCoverTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = make_app()
        self.game = next(iter(self.app.games.values()))

    def test_update_check_needs_internet_permission(self):
        self.app.catalog.set_setting("allow_internet", False)
        with self.assertRaises(AppError):
            self.app.api_check_update({})

    def test_cover_lookup_needs_internet_and_consent(self):
        self.app.catalog.set_setting("allow_internet", False)
        with self.assertRaises(AppError):
            self.app.api_game_fetch_cover({"id": self.game["id"], "consent": True})
        self.app.catalog.set_setting("allow_internet", True)
        with self.assertRaises(AppError):
            self.app.api_game_fetch_cover({"id": self.game["id"]})          # no consent: nothing is sent

    def test_engine_install_all_needs_internet_permission(self):
        self.app.catalog.set_setting("allow_internet", False)
        with self.assertRaises(AppError):
            self.app.api_engines_install_all({})


class FilesAndSavesTests(unittest.TestCase):
    def setUp(self):
        self.app, self.base = make_app()
        self.game = next(iter(self.app.games.values()))

    def test_game_files_refuses_missing_save_folder_and_missing_game(self):
        self.app.catalog.data["save_sources"][self.game["console"]] = str(self.base / "no-such-save-folder")
        with self.assertRaises(AppError):
            self.app.api_game_files({"id": self.game["id"], "what": "saves"})
        with self.assertRaises(AppError):
            self.app.api_game_files({"id": "nope"})

    def test_save_source_validates(self):
        with self.assertRaises(AppError):
            self.app.api_save_source({"console": "not-a-console", "path": str(self.base)})
        with self.assertRaises(AppError):
            self.app.api_save_source({"console": "nes", "path": str(self.base / "missing")})
        self.assertEqual(str(self.base), self.app.api_save_source({"console": "nes", "path": str(self.base)})["save_source"])
        self.assertIsNone(self.app.api_save_source({"console": "nes"})["save_source"])

    def test_scan_everything_rescans_and_makes_save_folders(self):
        out = self.app.api_scan_everything({})
        self.assertIn("rescan", out)
        self.assertIn("saves", out)

    def test_scan_apply_never_overrides_a_chosen_program(self):
        chosen = self.base / "mine.exe"
        chosen.write_bytes(b"x")
        self.app.catalog.set_mapping("emulator_paths", "retroarch", str(chosen))
        self.app.api_scan_apply({})
        self.assertEqual(str(chosen), self.app.catalog.data["emulator_paths"]["retroarch"])


class RoomActionsNeedARoomTests(unittest.TestCase):
    def test_host_only_actions_refuse_outside_a_room(self):
        app, _ = make_app()
        for call in (app.api_mp_game, app.api_mp_ready, app.api_mp_capacity, app.api_mp_open, app.api_mp_invite):
            with self.assertRaises(Exception):
                call({"id": "x"})
        self.assertIn("room", app.api_mp_cancel_wait({"session_id": "nothing"}))


class ServerControlDoesNotFreezeTests(unittest.TestCase):
    def test_slow_server_call_does_not_hold_the_big_lock(self):
        from launcher import app as appmod
        app, _ = make_app()
        self.assertIn("server_control", LauncherApp.UNLOCKED)
        gate, entered = threading.Event(), threading.Event()
        from server import cli

        def slow(args):
            entered.set()
            gate.wait(5)
            return 0
        real = cli.status
        cli.status = slow
        try:
            t = threading.Thread(target=lambda: app.api_server_control({"action": "status"}))
            t.start()
            self.assertTrue(entered.wait(3))
            got = []
            def probe():
                ok = app.api_lock.acquire(timeout=1)
                got.append(ok)
                if ok:
                    app.api_lock.release()
            u = threading.Thread(target=probe)
            u.start(); u.join(2)
            self.assertEqual([True], got)          # the big lock was free while the server call was busy
        finally:
            gate.set()
            cli.status = real
            t.join(5)


class RescanDoesNotFreezeTests(unittest.TestCase):
    def test_the_disk_walk_runs_without_the_big_lock(self):
        from launcher import app as appmod
        app, _ = make_app()
        self.assertIn("rescan", LauncherApp.UNLOCKED)
        gate, entered = threading.Event(), threading.Event()
        real = appmod.scan

        def slow(roots, excludes):
            entered.set()
            gate.wait(5)
            return real(roots, excludes)
        appmod.scan = slow
        try:
            t = threading.Thread(target=app.rescan)
            t.start()
            self.assertTrue(entered.wait(3))
            got = []

            def probe():
                ok = app.api_lock.acquire(timeout=1)
                got.append(ok)
                if ok:
                    app.api_lock.release()
            u = threading.Thread(target=probe)
            u.start(); u.join(2)
            self.assertEqual([True], got)
        finally:
            gate.set()
            appmod.scan = real
            t.join(5)
        self.assertEqual(1, len(app.games))

    def test_dolphin_pads_action_needs_dolphin(self):
        app, _ = make_app()
        with self.assertRaises(AppError):
            app.api_dolphin_pads({})
