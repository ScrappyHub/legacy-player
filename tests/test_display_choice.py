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
        with mock.patch("launcher.emulators.stop_pid") as stop, mock.patch("launcher.procs.is_alive", return_value=True):
            self.app.running = {"pid": 4242, "title": "T", "emulator": "E"}
            self.assertEqual({"stopped": "T"}, self.app.api_force_quit({}))
            stop.assert_called_once_with(4242)
            self.assertIsNone(self.app.running)
            with self.assertRaises(Exception):
                self.app.api_force_quit({})


class PlayOptionsTests(DisplayChoiceTests):
    """The Play options box: what it offers, what it remembers, and what reaches RetroArch."""
    def _game(self):
        games = Path(self.tmp.name) / "games" / "SNES"
        games.mkdir(parents=True)
        (games / "Alpha (USA) (Rev 1).sfc").write_bytes(b"\0" * 64)
        self.app.catalog.set_roots([str(games.parent)])
        self.app.rescan()
        return next(iter(self.app.games))

    def test_options_list_screens_switches_and_a_recommendation(self):
        gid = self._game()
        fake = {"retroarch": {"name": "RetroArch", "path": "/x/retroarch.exe"}}
        with mock.patch.object(self.app, "_emulators", return_value=fake), mock.patch.object(self.app, "_core_ok", return_value=True), \
             mock.patch("launcher.app.winplace.list_monitors", return_value=[{"index": 1, "label": "Monitor 1", "w": 2560, "h": 1440, "primary": True}]):
            self.app._specs = {"gpus": [{"name": "Intel UHD Graphics"}], "ram_gb": 8, "threads": 4}
            o = self.app.api_play_options({"id": gid})
        self.assertEqual("retroarch", o["emulator_id"])
        self.assertEqual("ask", o["mode"])
        self.assertEqual(["2560x1440", "1920x1080", "1600x900", "1280x720"], o["resolutions"])
        self.assertEqual(set(o["video"]), {"fullscreen", "integer", "keep_shape", "smooth", "vsync"})
        self.assertEqual(sorted(o["applies"]), sorted(o["video"]))
        self.assertTrue(o["recommended"]["choice"]["vsync"])
        self.assertTrue(o["recommended"]["integrated"])
        self.assertTrue(o["recommended"]["why"])

    def test_remembering_keeps_resolution_borderless_and_the_switches(self):
        gid = self._game()
        self.app._display_choice("retroarch", "snes", {"display": {"mode": "fullscreen", "monitor": "", "remember": True, "res": "1920x1080",
                                                                   "borderless": False, "video": {"vsync": False, "smooth": True, "bogus": True}}})
        self.assertEqual({"res": "1920x1080", "borderless": False}, self.app._play_prefs("retroarch"))
        v = self.app._video_for("snes")
        self.assertFalse(v["vsync"])
        self.assertTrue(v["smooth"])
        self.assertNotIn("bogus", self.app.catalog.data["video"]["snes"])
        lines = self.app._retroarch_extra("snes", str(Path(self.tmp.name) / "retroarch.exe"), fullscreen=True, res="1920x1080", borderless=False)
        cfg = Path(lines[1]).read_text()
        self.assertIn('video_fullscreen_x = "1920"', cfg)
        self.assertIn('video_windowed_fullscreen = "false"', cfg)
        self.assertIn('video_vsync = "false"', cfg)
        cfg2 = Path(self.app._retroarch_extra("snes", str(Path(self.tmp.name) / "retroarch.exe"), video={"vsync": True}, borderless=True)[1]).read_text()
        self.assertIn('video_vsync = "true"', cfg2)
        self.assertIn('video_windowed_fullscreen = "true"', cfg2)
        self.assertNotIn("video_fullscreen_x", cfg2)
