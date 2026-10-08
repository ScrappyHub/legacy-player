import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher.app import LauncherApp


class OverlayAndNoticeTests(unittest.TestCase):
    def setUp(self):
        self.app = LauncherApp(Path(tempfile.mkdtemp()))

    def test_notices_are_delivered_once(self):
        self.app.notify_ui("Server started.")
        self.assertEqual(["Server started."], [n["text"] for n in self.app.api_notices({})["notices"]])
        self.assertEqual([], self.app.api_notices({})["notices"])

    def test_overlay_view_carries_server_state_and_whether_the_game_can_restart(self):
        (self.app.data_dir / "server").mkdir(exist_ok=True)
        self.app._srv_cache.update(at=9e18, value={"running": True, "shared": False, "players": 1, "rooms": 1})
        view = self.app._overlay_view()
        self.assertEqual(True, view["server"]["running"])
        self.assertFalse(view["can_restart"])

    def test_overlay_server_buttons_run_the_server_and_tell_the_page(self):
        acts = self.app._overlay_actions()
        with mock.patch.object(self.app, "api_server_control", return_value={}) as ctl:
            self.assertIn("on", acts["server_on"]())
            ctl.assert_called_with({"action": "start", "share": False})
            acts["server_off"]()
            self.assertEqual("stop", ctl.call_args[0][0]["action"])
        self.assertTrue(any("turned off" in n["text"] for n in self.app.api_notices({})["notices"]))

    def test_restart_game_needs_a_game_started_from_the_library(self):
        acts = self.app._overlay_actions()
        with self.assertRaises(Exception):
            acts["restart_game"]()

    def test_overlay_buttons_are_the_short_list(self):
        import re
        src = (Path(__file__).resolve().parent.parent / "launcher" / "overlay_window.py").read_text(encoding="utf-8")
        labels = set(re.findall(r'_button\([^,]+, "([^"]+)"', src))
        self.assertFalse({"Full screen", "Windowed", "Back to the game"} & labels)
        self.assertTrue({"Turn on", "Turn off", "Restart", "Restart game"} <= labels)

    def test_tray_hears_about_server_changes_from_anywhere(self):
        from launcher.tray import TrayController
        tray = TrayController(self.app, lambda: None)
        self.assertEqual(tray.poke, self.app.on_server_change)

    def test_background_is_a_choice_with_a_default(self):
        spec = self.app.catalog.settings()
        self.assertEqual("waves", spec["background"])
        self.app.catalog.set_setting("background", "grid")
        self.assertEqual("grid", self.app.catalog.settings()["background"])
        with self.assertRaises(Exception):
            self.app.catalog.set_setting("background", "nonsense")


if __name__ == "__main__":
    unittest.main()
