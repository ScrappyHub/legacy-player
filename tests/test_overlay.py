import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import overlay
from launcher.app import AppError, LauncherApp


class ParseTests(unittest.TestCase):
    def test_hotkey_parses_and_normalises(self):
        flags, vk, text = overlay.parse_hotkey("Shift + CTRL + l")
        self.assertEqual((0x0002 | 0x0004, ord("L"), "ctrl+shift+l"), (flags, vk, text))
        self.assertEqual(0x70, overlay.parse_hotkey("alt+f1")[1])

    def test_bad_hotkeys_are_refused(self):
        for bad in ("l", "ctrl", "ctrl+shift", "ctrl+ctrl+l", "foo+l", "ctrl+escape", "alt+f13"):
            with self.assertRaises(ValueError, msg=bad):
                overlay.parse_hotkey(bad)

    def test_prefs_validation(self):
        cur = dict(overlay.DEFAULTS)
        self.assertEqual("", overlay.validate_prefs({"hotkey": ""}, cur)["hotkey"])
        self.assertEqual(["a", "b"], overlay.validate_prefs({"pad": ["a", "b"]}, cur)["pad"])
        for bad in ({"pad": ["a"]}, {"pad": ["a", "a"]}, {"pad": ["nope", "a"]}, {"hotkey": "x"}):
            with self.assertRaises(ValueError):
                overlay.validate_prefs(bad, cur)
        self.assertEqual(3.0, overlay.validate_prefs({"hold": 99}, cur)["hold"])


class ComboTests(unittest.TestCase):
    def test_fires_once_after_the_hold_and_rearms_on_release(self):
        c = overlay.ComboWatcher(["back", "start"], 0.5)
        both = overlay.PAD_BITS["back"] | overlay.PAD_BITS["start"]
        self.assertFalse(c.feed(both, 0.0))
        self.assertFalse(c.feed(both, 0.3))
        self.assertTrue(c.feed(both, 0.6))
        self.assertFalse(c.feed(both, 5.0))             # held on: no second fire
        self.assertFalse(c.feed(overlay.PAD_BITS["back"], 5.1))
        self.assertFalse(c.feed(both, 6.0))
        self.assertTrue(c.feed(both, 6.6))

    def test_partial_press_never_fires_and_empty_combo_is_off(self):
        c = overlay.ComboWatcher(["back", "start"], 0.1)
        self.assertFalse(c.feed(overlay.PAD_BITS["back"], 0.0))
        self.assertFalse(c.feed(overlay.PAD_BITS["back"], 9.0))
        self.assertFalse(overlay.ComboWatcher([], 0.1).feed(0xFFFF, 9.0))

    def test_names_of(self):
        self.assertEqual(["start", "a"], overlay.names_of(0x0010 | 0x1000))


class AppOverlayTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict("os.environ", {"LEGACY_PLAYER_NO_BACKGROUND": "1"})
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = LauncherApp(Path(self.tmp.name) / "data", roots=[])

    def test_defaults_save_and_validation(self):
        r = self.app.api_overlay({})
        self.assertEqual("ctrl+shift+l", r["hotkey"])
        self.app.api_overlay({"hotkey": "alt+f2", "pad": ["lb", "rb", "start"]})
        again = self.app.api_overlay({})
        self.assertEqual(("alt+f2", ["lb", "rb", "start"]), (again["hotkey"], again["pad"]))
        with self.assertRaises(AppError):
            self.app.api_overlay({"hotkey": "z"})
        self.assertEqual("alt+f2", self.app.api_overlay({})["hotkey"])          # a refused change changes nothing

    def test_saving_restarts_the_listeners(self):
        self.app.overlay_listeners = mock.Mock(error="")
        self.app.api_overlay({"enabled": False})
        self.app.overlay_listeners.start.assert_called_once()
        self.assertFalse(self.app.overlay_listeners.start.call_args[0][0]["enabled"])

    def test_state_shows_game_and_room(self):
        self.assertIsNone(self.app.api_overlay_state({})["game"])
        self.app.running = {"pid": 1, "title": "T", "emulator": "E", "emulator_id": "retroarch"}
        self.app.room = {"game": "T", "role": "host", "invite_code": "ABC"}
        st = self.app.api_overlay_state({})
        self.assertEqual("T", st["game"]["title"])
        self.assertEqual("ABC", st["room"]["invite_code"])

    def test_game_window_needs_a_game_and_a_valid_mode(self):
        with self.assertRaises(AppError):
            self.app.api_game_window({"mode": "windowed"})
        self.app.running = {"pid": 7, "title": "T", "emulator": "E", "emulator_id": "retroarch"}
        with self.assertRaises(AppError):
            self.app.api_game_window({"mode": "sideways"})
        with mock.patch.object(self.app, "_bring_forward") as bf:
            self.app.api_game_window({"mode": "fullscreen"})
            bf.assert_called_once_with(7, "retroarch", "fullscreen")

    def test_open_toggles_closed_when_already_open(self):
        with mock.patch("launcher.winplace.close_titled", return_value=True):
            self.assertEqual({"open": False}, self.app.api_overlay_open({}))
        opened = []
        self.app.overlay_opener = lambda: opened.append(1)
        with mock.patch("launcher.winplace.close_titled", return_value=False), mock.patch("launcher.winplace.pin_titled"):
            self.assertEqual({"open": True}, self.app.api_overlay_open({}))
        self.assertEqual([1], opened)


if __name__ == "__main__":
    unittest.main()
