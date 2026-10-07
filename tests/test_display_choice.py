import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher.app import LauncherApp


class DisplayChoiceTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict("os.environ", {"LEGACY_PLAYER_NO_BACKGROUND": "1"})
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = LauncherApp(Path(self.tmp.name) / "data", roots=[])

    def test_interactive_launch_asks_when_nothing_is_stored(self):
        mode, _, ask = self.app._display_choice("retroarch", "snes", {"interactive": True})
        self.assertTrue(ask)
        self.assertIsNone(mode)

    def test_non_interactive_launch_never_asks(self):
        self.assertFalse(self.app._display_choice("retroarch", "snes", {})[2])

    def test_answer_is_used_and_remembered_only_on_request(self):
        r = self.app._display_choice("retroarch", "snes", {"display": {"mode": "windowed"}})
        self.assertEqual(("windowed", "", False), r)
        self.assertTrue(self.app._display_choice("retroarch", "snes", {"interactive": True})[2])
        self.app._display_choice("retroarch", "snes", {"display": {"mode": "fullscreen", "remember": True}})
        mode, _, ask = self.app._display_choice("retroarch", "snes", {"interactive": True})
        self.assertEqual(("fullscreen", False), (mode, ask))

    def test_setting_back_to_ask_asks_again(self):
        self.app._display_choice("retroarch", "snes", {"display": {"mode": "fullscreen", "remember": True}})
        self.app._display_prefs()["modes"]["retroarch"] = "ask"
        self.assertTrue(self.app._display_choice("retroarch", "snes", {"interactive": True})[2])


if __name__ == "__main__":
    unittest.main()


class ForceQuitTests(DisplayChoiceTests):
    def test_force_quit_stops_the_game(self):
        with mock.patch("launcher.emulators.stop_pid") as stop:
            self.app.running = {"pid": 4242, "title": "T", "emulator": "E"}
            self.assertEqual({"stopped": "T"}, self.app.api_force_quit({}))
            stop.assert_called_once_with(4242)
            self.assertIsNone(self.app.running)
            with self.assertRaises(Exception):
                self.app.api_force_quit({})
