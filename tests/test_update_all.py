import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import updateall
from launcher.app import AppError, LauncherApp


class UpdateAllTests(unittest.TestCase):
    def setUp(self):
        self.app = LauncherApp(Path(tempfile.mkdtemp()))
        self.ua = self.app.update_all

    def _run(self, tag="v9.9.9", ours=("dolphin",), job_state="done"):
        newer = tag == "v9.9.9"
        info = {"mode": "exe", "newer": newer, "latest": tag, "message": "Version x is available." if newer else "You have the latest version."}

        def prepared(i):
            self.app.self_update.staged = {"mode": "exe", "version": tag, "stage": "s", "dest": "d"}
        with mock.patch.object(self.app, "_update_check", return_value=info), \
             mock.patch.object(self.app.self_update, "prepare", side_effect=prepared), \
             mock.patch.object(self.ua, "_ours", return_value=list(ours)), \
             mock.patch.object(self.app.installer, "start_many", return_value={"state": job_state, "error": "boom" if job_state == "error" else None}) as many, \
             mock.patch.object(updateall.privatelink, "find_tailscale", return_value=None):
            self.ua._run()
        return many

    def test_runs_every_step_and_lists_what_is_needed(self):
        many = self._run()
        snap = self.ua.snapshot()
        self.assertEqual("done", snap["state"])
        states = {s["id"]: s["state"] for s in snap["steps"]}
        self.assertEqual({"app": "done", "engines": "done", "tailscale": "skipped", "games": "done", "checkup": "done"}, states)
        many.assert_called_once()
        self.assertEqual(["dolphin"], many.call_args[0][0])
        needs = snap["report"]["needs"]
        self.assertEqual("app_restart", needs[0]["action"])         # a newer release is downloaded, then a restart comes first
        self.assertEqual("v9.9.9", snap["report"]["restart"])
        self.assertIn("ready", next(s for s in snap["steps"] if s["id"] == "app")["detail"])
        self.assertIn("Legacy Player checkup", snap["report"]["text"])

    def test_a_failing_step_does_not_stop_the_rest(self):
        many = self._run(job_state="error")
        snap = self.ua.snapshot()
        self.assertEqual("problem", next(s for s in snap["steps"] if s["id"] == "engines")["state"])
        self.assertEqual("done", next(s for s in snap["steps"] if s["id"] == "games")["state"])
        self.assertEqual("done", snap["state"])

    def test_nothing_installed_by_us_means_engines_are_skipped(self):
        many = self._run(tag="v0.0.1", ours=())
        many.assert_not_called()
        snap = self.ua.snapshot()
        self.assertEqual("skipped", next(s for s in snap["steps"] if s["id"] == "engines")["state"])
        self.assertNotIn("app_restart", [n["action"] for n in snap["report"]["needs"]])
        self.assertEqual("", snap["report"]["restart"])

    def test_starting_needs_the_internet_setting_and_a_confirmation(self):
        with self.assertRaises(AppError):
            self.app.api_update_all({"action": "start", "confirm": True})      # internet is off by default
        self.app.catalog.set_setting("allow_internet", True)
        with self.assertRaises(AppError):
            self.app.api_update_all({"action": "start"})                        # not confirmed

    def test_updating_the_app_itself_needs_a_confirmation(self):
        with self.assertRaises(AppError):
            self.app.api_app_update({})
        with self.assertRaises(AppError):
            self.app.api_app_update({"action": "restart"})
        with self.assertRaises(AppError):                                       # nothing downloaded yet
            self.app.api_app_update({"action": "restart", "confirm": True})
        self.assertFalse(self.app.quit_requested)

    def test_a_failed_download_is_a_problem_not_a_restart(self):
        info = {"mode": "exe", "newer": True, "latest": "v9.9.9", "message": "Version v9.9.9 is available."}
        with mock.patch.object(self.app, "_update_check", return_value=info), \
             mock.patch.object(self.app.self_update, "prepare", side_effect=RuntimeError("checksum mismatch")), \
             mock.patch.object(self.ua, "_ours", return_value=[]), \
             mock.patch.object(updateall.privatelink, "find_tailscale", return_value=None):
            self.ua._run()
        snap = self.ua.snapshot()
        self.assertEqual("problem", next(s for s in snap["steps"] if s["id"] == "app")["state"])
        self.assertEqual("", snap["report"]["restart"])


if __name__ == "__main__":
    unittest.main()
