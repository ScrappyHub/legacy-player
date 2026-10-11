import tempfile
import unittest
from pathlib import Path

from launcher import dolphinpads, emulators

STANDARD = {"key": "xbox", "name": "Xbox pad", "standard": True, "vendor": None, "product": None, "bindings": {}}


def dolphin_install():
    base = Path(tempfile.mkdtemp())
    (base / "Dolphin.exe").write_bytes(b"x")
    (base / "portable.txt").write_text("")
    (base / "User" / "Config").mkdir(parents=True)
    return base / "Dolphin.exe", base / "User" / "Config" / "GCPadNew.ini"


class DolphinPadTests(unittest.TestCase):
    def test_nothing_assigned_writes_nothing(self):
        exe, ini = dolphin_install()
        ini.write_text("[GCPad1]\nDevice = mine\n")
        out = dolphinpads.apply(exe, {}, {}, {"layout": "default"})
        self.assertFalse(out["applied"])
        self.assertEqual("[GCPad1]\nDevice = mine\n", ini.read_text())

    def test_pad_is_written_and_original_backed_up_once(self):
        exe, ini = dolphin_install()
        ini.write_text("[GCPad1]\nDevice = mine\n")
        out = dolphinpads.apply(exe, {"1": "xbox"}, {"xbox": STANDARD}, None)
        self.assertTrue(out["applied"])
        text = ini.read_text()
        self.assertIn("Device = XInput/0/Gamepad", text)
        self.assertIn("Buttons/A = `Button A`", text)
        self.assertIn("Buttons/Start = `Start`", text)
        backup = ini.with_name(dolphinpads.BACKUP)
        self.assertEqual("[GCPad1]\nDevice = mine\n", backup.read_text())
        dolphinpads.apply(exe, {"1": "xbox"}, {"xbox": STANDARD}, None)        # a second launch must not back up our own file
        self.assertEqual("[GCPad1]\nDevice = mine\n", backup.read_text())
        self.assertTrue(dolphinpads.restore(exe)["restored"])
        self.assertEqual("[GCPad1]\nDevice = mine\n", ini.read_text())
        self.assertFalse(backup.exists())

    def test_only_the_written_players_sections_are_replaced(self):
        exe, ini = dolphin_install()
        mine = ("[GCPad1]\nDevice = mine/1\nButtons/A = `X`\n"
                "[GCPad2]\nDevice = mine/2\nButtons/A = `Y`\n"
                "[GCPad3]\nDevice = SDL/0/Steam Deck\n")
        ini.write_text(mine)
        out = dolphinpads.apply(exe, {"2": "xbox"}, {"xbox": STANDARD}, None)
        self.assertTrue(out["applied"])
        text = ini.read_text()
        self.assertIn("Device = mine/1", text)                  # player 1, set up in Dolphin, untouched
        self.assertIn("Device = SDL/0/Steam Deck", text)        # player 3 too
        self.assertNotIn("Device = mine/2", text)               # player 2 is ours now
        self.assertEqual(1, text.count("[GCPad2]"))
        self.assertIn("Device = XInput/1/Gamepad", text)
        self.assertLess(text.index("[GCPad1]"), text.index("[GCPad2]"))
        self.assertLess(text.index("[GCPad2]"), text.index("[GCPad3]"))
        # next launch player 2 is unassigned and player 1 is ours: player 2 goes back to the player's own section
        dolphinpads.apply(exe, {"1": "xbox"}, {"xbox": STANDARD}, None)
        text = ini.read_text()
        self.assertIn("Device = mine/2", text)
        self.assertNotIn("Device = mine/1", text)
        self.assertIn("Device = SDL/0/Steam Deck", text)
        self.assertTrue(dolphinpads.restore(exe)["restored"])
        self.assertEqual(mine, ini.read_text())

    def test_new_section_is_added_after_the_players_own(self):
        exe, ini = dolphin_install()
        ini.write_text("[GCPad1]\nDevice = mine/1\n")
        dolphinpads.apply(exe, {"4": "xbox"}, {"xbox": dict(STANDARD, index=2)}, None)
        text = ini.read_text()
        self.assertIn("Device = mine/1", text)
        self.assertIn("[GCPad4]\nDevice = XInput/2/Gamepad", text)

    def test_windows_registry_user_folder_is_honoured(self):
        import sys
        import types
        from unittest import mock
        base = Path(tempfile.mkdtemp())
        exe = base / "Dolphin" / "Dolphin.exe"
        exe.parent.mkdir()
        exe.write_bytes(b"x")
        custom = base / "Elsewhere" / "Dolphin"
        (custom / "Config").mkdir(parents=True)
        values = {"UserConfigPath": str(custom)}

        class Key:
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def query(key, name):
            if name not in values:
                raise FileNotFoundError(name)
            return values[name], 1
        fake = types.SimpleNamespace(HKEY_CURRENT_USER=1, OpenKey=lambda *a: Key(), QueryValueEx=query)
        with mock.patch.dict(sys.modules, {"winreg": fake}), mock.patch.object(dolphinpads.sys, "platform", "win32"), \
                mock.patch.object(dolphinpads, "documents_dir", return_value=base / "OneDrive" / "Documents"):
            self.assertEqual(custom, dolphinpads.find_user_dir(exe))
            self.assertIn(base / "OneDrive" / "Documents" / "Dolphin Emulator", dolphinpads.user_dirs(exe))
            values.clear()
            values["LocalUserConfig"] = 1
            (exe.parent / "User" / "Config").mkdir(parents=True)
            self.assertEqual(exe.parent / "User", dolphinpads.find_user_dir(exe))

    def test_documents_folder_falls_back_to_home(self):
        if dolphinpads.sys.platform != "win32":
            self.assertEqual(Path(dolphinpads.os.path.expanduser("~")) / "Documents", dolphinpads.documents_dir())

    def test_restore_removes_our_file_when_there_was_none(self):
        exe, ini = dolphin_install()
        dolphinpads.apply(exe, {"2": "xbox"}, {"xbox": STANDARD}, None)
        self.assertIn("[GCPad2]", ini.read_text())
        self.assertIn("Device = XInput/1/Gamepad", ini.read_text())
        self.assertTrue(dolphinpads.restore(exe)["restored"])
        self.assertFalse(ini.exists())

    def test_rebound_button_follows_the_profile(self):
        profile = dict(STANDARD, bindings={"0": {"t": "b", "i": 1}, "1": {"t": "b", "i": 0}})      # swap south and east
        text, _ = dolphinpads.build({"1": "p"}, {"p": profile}, None)
        self.assertIn("Buttons/A = `Button B`", text)
        self.assertIn("Buttons/X = `Button A`", text)

    def test_unknown_pad_is_left_to_dolphin(self):
        text, notes = dolphinpads.build({"1": "odd"}, {"odd": dict(STANDARD, standard=False)}, None)
        self.assertEqual("", text)
        self.assertTrue(notes)

    def test_keyboard_layout_for_player_one(self):
        text, _ = dolphinpads.build({}, {}, {"layout": "wasd"})
        self.assertIn("[GCPad1]", text)
        self.assertIn("Main Stick/Up = W", text)
        self.assertIn("Buttons/Start = RETURN", text)
        self.assertNotIn("[GCPad2]", text)

    def test_missing_settings_folder_is_not_an_error(self):
        exe = Path(tempfile.mkdtemp()) / "Dolphin.exe"
        exe.write_bytes(b"x")
        out = dolphinpads.apply(exe, {"1": "xbox"}, {"xbox": STANDARD}, None)
        if dolphinpads.find_user_dir(exe) is None:
            self.assertFalse(out["applied"])


class FullscreenFlagTests(unittest.TestCase):
    def test_every_flag_is_a_list_of_strings_and_status_is_honest(self):
        for eid, spec in emulators.EMULATORS.items():
            flag = spec.get("fullscreen")
            status = emulators.fullscreen_status(eid)
            if flag:
                self.assertTrue(all(isinstance(a, str) and a for a in flag), eid)
                self.assertIn(status, {"documented", "unconfirmed"})
            else:
                self.assertEqual("none", status)

    def test_flag_only_added_when_asked(self):
        self.assertEqual([], emulators.video_args("mgba", False))
        self.assertEqual(["-f"], emulators.video_args("mgba", True))
        self.assertEqual([], emulators.video_args("snes9x", True))
