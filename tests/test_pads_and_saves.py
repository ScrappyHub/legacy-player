import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import pads, savefolders
from launcher.app import AppError, LauncherApp


class PadTests(unittest.TestCase):
    def test_vendor_product_parsing(self):
        self.assertEqual(pads.parse_vendor_product("Xbox 360 Controller (STANDARD GAMEPAD Vendor: 045e Product: 028e)"), ("045e", "028e"))
        self.assertEqual(pads.parse_vendor_product("054c-09cc-Wireless Controller"), ("054c", "09cc"))
        self.assertEqual(pads.parse_vendor_product("Mystery pad"), (None, None))

    def test_validate_profile(self):
        p = pads.validate_profile("Pad  X", {"name": "My pad", "bindings": {"0": {"t": "b", "i": 3}, "6": {"t": "a", "i": 2, "d": 1}}})
        self.assertEqual(p["key"], "pad x")
        self.assertEqual(pads.translate(p, 0), {"t": "b", "i": 3})
        self.assertEqual(pads.translate(p, 4), {"t": "b", "i": 4})  # unmapped falls back to standard
        self.assertIsNone(pads.translate(p, 3))  # raw button 3 was given to control 0
        for bad in ({"99": {"t": "b", "i": 1}}, {"0": {"t": "b", "i": -1}}, {"0": {"t": "a", "i": 1, "d": 0}},
                    {"0": {"t": "b", "i": True}}, {"0": {"t": "b", "i": 1}, "1": {"t": "b", "i": 1}}):
            with self.assertRaises(ValueError):
                pads.validate_profile("x", {"bindings": bad})

    def test_retroarch_config_only_for_standard_pads(self):
        std = pads.validate_profile("p", {"standard": True, "bindings": {"0": {"t": "b", "i": 1}}})
        lines, _ = pads.retroarch_pad_config(std, 1)
        # slot 0 rebound to the east button: RetroArch's xinput driver numbers B as button 1
        self.assertIn('input_player1_b_btn = "1"', lines)
        self.assertFalse(any(l.startswith('input_player1_a_btn') for l in lines))  # its button now belongs to control 0
        other = pads.validate_profile("q", {"standard": False, "bindings": {}})
        self.assertEqual(pads.retroarch_pad_config(other, 1)[0], [])

    def test_retroarch_xinput_numbers_match_its_own_autoconfig(self):
        # RetroArch's XInput autoconfig: a=1 b=0 x=3 y=2 l=4 r=5 start=6 select=7 l3=8 r3=9, d-pad on hat 0
        lines, notes = pads.retroarch_pad_config(pads.validate_profile("x", {"standard": True}), 2)
        got = dict(l.split(" = ") for l in lines)
        want = {"a": "1", "b": "0", "x": "3", "y": "2", "l": "4", "r": "5", "start": "6", "select": "7", "l3": "8", "r3": "9",
                "up": "h0up", "down": "h0down", "left": "h0left", "right": "h0right"}
        for role, value in want.items():
            self.assertEqual(f'"{value}"', got[f"input_player2_{role}_btn"], role)
        self.assertNotIn("input_player2_l2_btn", got)                 # triggers are axes: left to RetroArch
        self.assertEqual('"1"', got["input_player2_joypad_index"])    # no stored index: the player's position
        self.assertEqual([], notes)

    def test_assigned_pad_index_is_used_for_the_device(self):
        profile = pads.validate_profile("x", {"standard": True, "index": 3})
        self.assertEqual(3, profile["index"])
        self.assertIn('input_player1_joypad_index = "3"', pads.retroarch_pad_config(profile, 1)[0])
        self.assertEqual(2, pads.device_index(pads.with_device_index(profile, 2), 1))
        self.assertEqual(0, pads.device_index({"standard": True}, 1))
        for bad in (-1, 16, True, "1"):
            with self.assertRaises(ValueError):
                pads.validate_profile("x", {"index": bad})
        from launcher import dolphinpads
        lines, _ = dolphinpads.pad_section(1, pads.with_device_index(profile, 2))
        self.assertIn("Device = XInput/2/Gamepad", lines)


class SaveMatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.saves_dir = self.root / "saves"
        self.saves_dir.mkdir()

    def write(self, name, data=b"x"):
        (self.saves_dir / name).write_bytes(data)

    def test_a_game_only_gets_its_own_saves(self):
        from launcher import saves
        for name in ("Super Mario Bros.srm", "Super Mario Bros.state1", "Super Mario Bros.state.auto",
                     "Super Mario Bros 3.srm", "Super Mario Bros 3.state", "Super Mario Bros. 3.srm",
                     "Super Mario Bros_1.mcd", "Super Mario Bros (Japan).srm", "New Super Mario Bros.srm"):
            self.write(name)
        found = {p.name for p in saves.find_save_files(self.saves_dir, "Super Mario Bros")}
        self.assertEqual({"Super Mario Bros.srm", "Super Mario Bros.state1", "Super Mario Bros.state.auto",
                          "Super Mario Bros_1.mcd"}, found)
        self.assertEqual({"Super Mario Bros 3.srm", "Super Mario Bros 3.state"},
                         {p.name for p in saves.find_save_files(self.saves_dir, "super mario bros 3")})
        self.assertEqual(9, len(saves.find_save_files(self.saves_dir, "")))     # empty stem: every save file

    def test_restore_does_not_touch_another_games_saves(self):
        from launcher import saves
        data = self.root / "data"
        self.write("Super Mario Bros.srm", b"one-old")
        self.write("Super Mario Bros 3.srm", b"three")
        made = saves.create_backup(data, "nes", "smb", saves.find_save_files(self.saves_dir, "Super Mario Bros"), self.saves_dir)
        self.assertEqual(1, made["files"])
        self.write("Super Mario Bros.srm", b"one-new")
        self.write("Super Mario Bros 3.srm", b"three-progress")
        out = saves.restore_backup(data, "nes", "smb", made["backup"], self.saves_dir, "Super Mario Bros")
        self.assertEqual(1, out["restored"])
        self.assertEqual(b"one-old", (self.saves_dir / "Super Mario Bros.srm").read_bytes())
        self.assertEqual(b"three-progress", (self.saves_dir / "Super Mario Bros 3.srm").read_bytes())
        self.assertFalse(any(self.saves_dir.glob("*.lp-part")))

    def test_locked_file_gives_a_clear_error_and_nothing_half_done(self):
        import os
        from launcher import saves
        data = self.root / "data"
        self.write("Zelda.srm", b"srm-old")
        self.write("Zelda.state1", b"state-old")
        made = saves.create_backup(data, "snes", "z", saves.find_save_files(self.saves_dir, "Zelda"), self.saves_dir)
        self.write("Zelda.srm", b"srm-new")
        self.write("Zelda.state1", b"state-new")
        real_replace = os.replace

        def locked(src, dst, *a, **kw):                      # the emulator still holds the state file open
            if Path(dst).name == "Zelda.state1":
                raise PermissionError(13, "The process cannot access the file", str(dst))
            return real_replace(src, dst, *a, **kw)
        with mock.patch("launcher.saves.os.replace", side_effect=locked):
            with self.assertRaises(ValueError) as caught:
                saves.restore_backup(data, "snes", "z", made["backup"], self.saves_dir, "Zelda")
        self.assertIsInstance(caught.exception, saves.SaveFileBusy)
        self.assertIn("Close the emulator", str(caught.exception))
        self.assertEqual(b"srm-new", (self.saves_dir / "Zelda.srm").read_bytes())      # the one already swapped was put back
        self.assertEqual(b"state-new", (self.saves_dir / "Zelda.state1").read_bytes())
        self.assertFalse(any(self.saves_dir.glob("*.lp-part")))
        with mock.patch("launcher.saves.shutil.copy2", side_effect=PermissionError(13, "locked")):
            with self.assertRaises(saves.SaveFileBusy):
                saves.restore_backup(data, "snes", "z", made["backup"], self.saves_dir, "Zelda")
        self.assertEqual(b"srm-new", (self.saves_dir / "Zelda.srm").read_bytes())

    def test_app_restore_turns_a_locked_file_into_a_message(self):
        app = LauncherApp(self.root / "appdata")
        game = {"path": str(self.root / "Zelda.sfc"), "console": "snes", "compat_id": "z"}
        with mock.patch.object(app, "_save_ctx", return_value=(game, mock.Mock(id="snes"), self.saves_dir)), \
                mock.patch("launcher.saves.restore_backup", side_effect=__import__("launcher.saves", fromlist=["x"]).SaveFileBusy("Close the emulator")):
            with self.assertRaisesRegex(AppError, "Close the emulator"):
                app.api_restore({"id": "x", "backup": "y"})


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = LauncherApp(Path(self.tmp.name) / "data")

    def test_pad_save_assign_delete(self):
        self.app.api_pad_save({"id": "Pad 1", "name": "Pad", "standard": True, "bindings": {"0": {"t": "b", "i": 2}}})
        out = self.app.api_pad_assign({"player": 1, "id": "Pad 1"})
        self.assertEqual(out["players"]["1"], "pad 1")
        out = self.app.api_pad_assign({"player": 2, "id": "Brand new", "name": "New", "standard": False})
        self.assertIn("brand new", out["profiles"])
        out = self.app.api_pad_delete({"id": "pad 1"})
        self.assertNotIn("1", out["players"])
        with self.assertRaises(AppError):
            self.app.api_pad_assign({"player": 9, "id": "x"})
        with self.assertRaises(AppError):
            self.app.api_pad_save({"id": "x", "bindings": {"0": {"t": "b", "i": 999}}})

    def test_save_folders_and_append_config(self):
        root = Path(self.tmp.name) / "saves"
        out = self.app.api_save_folders({"root": str(root), "create": True})
        self.assertTrue((root / "nes" / "saves").is_dir())
        self.assertTrue((root / "snes" / "states").is_dir())
        self.assertEqual(out["root"], str(root))
        exe = Path(self.tmp.name) / "ra" / "retroarch"
        (exe.parent / "info").mkdir(parents=True)
        exe.write_text("x")
        self.app.api_pad_assign({"player": 1, "id": "xpad", "standard": True})
        args = self.app._retroarch_extra("nes", str(exe))
        self.assertEqual(args[0], "--appendconfig")
        text = Path(args[1]).read_text()
        self.assertIn(f'savefile_directory = "{root / "nes" / "saves"}"', text)
        self.assertIn("libretro_info_path", text)
        self.assertIn("input_player1_start_btn", text)
        self.assertNotIn("netplay_public_announce", text)
        net = Path(self.app._retroarch_extra("nes", str(exe), netplay=True)[1]).read_text()
        self.assertIn('netplay_public_announce = "false"', net)
        with self.assertRaises(AppError):
            self.app.api_save_folders({"root": "relative/path"})

    def test_extra_emulator_folder_is_searched(self):
        folder = Path(self.tmp.name) / "Emu" / "Dolphin" / "Dolphin-x64"
        folder.mkdir(parents=True)
        (folder / ("Dolphin.exe" if sys.platform == "win32" else "dolphin-emu")).write_text("x")
        before = {e["id"]: e["path"] for e in self.app.api_emulators({})["emulators"]}.get("dolphin")
        self.assertIsNone(before)
        out = self.app.api_emulators({"folder": str(Path(self.tmp.name) / "Emu")})
        self.assertEqual([str(Path(self.tmp.name) / "Emu")], out["folders"])
        self.assertTrue(next(e for e in out["emulators"] if e["id"] == "dolphin")["path"])
        out = self.app.api_emulators({"folder": str(Path(self.tmp.name) / "Emu"), "remove": True})
        self.assertEqual([], out["folders"])
        with self.assertRaises(AppError):
            self.app.api_emulators({"folder": str(Path(self.tmp.name) / "nope")})

    def test_rejects_quote_in_path(self):
        with self.assertRaises(ValueError):
            savefolders._q('C:\\bad"path')


if __name__ == "__main__":
    unittest.main()
