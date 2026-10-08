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
        with mock.patch.object(updateall, "latest_release", return_value={"tag": tag, "page": "x", "assets": [], "published_at": ""}), \
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
        self.assertEqual("app_update", needs[0]["action"])          # a newer release comes first
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
        self.assertNotIn("app_update", [n["action"] for n in snap["report"]["needs"]])

    def test_starting_needs_the_internet_setting_and_a_confirmation(self):
        with self.assertRaises(AppError):
            self.app.api_update_all({"action": "start", "confirm": True})      # internet is off by default
        self.app.catalog.set_setting("allow_internet", True)
        with self.assertRaises(AppError):
            self.app.api_update_all({"action": "start"})                        # not confirmed

    def test_updating_the_app_itself_needs_a_confirmation(self):
        with self.assertRaises(AppError):
            self.app.api_app_update({})


if __name__ == "__main__":
    unittest.main()
