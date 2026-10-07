import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import selfuninstall


class CreatedFolderTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.data = self.base / "data"
        self.data.mkdir()
        self.saves = self.base / "MySaves"
        (self.saves / "snes" / "saves").mkdir(parents=True)
        (self.saves / "snes" / "states").mkdir()
        (self.saves / "snes" / "saves" / "a.srm").write_bytes(b"1" * 10)
        (self.saves / "notes.txt").write_text("mine")
        (self.saves / "nes" / "photos").mkdir(parents=True)          # same name as a console but not our shape
        self.backups = self.base / "MyBackups"
        self.backups.mkdir()
        (self.backups / "LegacyPlayer-saves-20260101-000000.zip").write_bytes(b"z")
        (self.backups / "holiday.zip").write_bytes(b"z")
        self.ids = ["snes", "nes"]

    def test_lists_only_the_shapes_we_make(self):
        got = selfuninstall.created_folders(str(self.saves), str(self.backups), self.ids, self.data)
        self.assertEqual({"saves", "backups"}, {c["kind"] for c in got})
        paths = [c["path"] for c in got if c["kind"] == "saves"]
        self.assertEqual([str(self.saves / "snes")], paths)
        files = [c for c in got if c["kind"] == "backups"][0]["files"]
        self.assertEqual([str(self.backups / "LegacyPlayer-saves-20260101-000000.zip")], files)

    def test_keeping_removes_nothing_and_deleting_removes_only_ours(self):
        created = selfuninstall.created_folders(str(self.saves), str(self.backups), self.ids, self.data)
        with mock.patch("launcher.selfuninstall._spawn_cleanup", lambda *a: None):
            kept = selfuninstall.execute(self.data, True, False, created=created, delete_created=False)
            self.assertTrue((self.saves / "snes" / "saves" / "a.srm").exists())
            self.assertTrue(kept["kept_created"])
            gone = selfuninstall.execute(self.data, True, False, created=created, delete_created=True)
        self.assertFalse((self.saves / "snes").exists())
        self.assertTrue((self.saves / "notes.txt").exists())
        self.assertTrue((self.saves / "nes" / "photos").exists())
        self.assertTrue((self.backups / "holiday.zip").exists())
        self.assertFalse((self.backups / "LegacyPlayer-saves-20260101-000000.zip").exists())
        self.assertEqual([], gone["problems"])
        self.assertTrue(self.saves.exists() and self.backups.exists())

    def test_folders_inside_the_data_folder_are_not_listed_twice(self):
        inside = self.data / "saves"
        (inside / "snes" / "saves").mkdir(parents=True)
        self.assertEqual([], selfuninstall.created_folders(str(inside), "", self.ids, self.data))


if __name__ == "__main__":
    unittest.main()


class SafetyTests(unittest.TestCase):
    def test_refuses_dangerous_folders(self):
        from pathlib import Path as P
        self.assertIsNotNone(selfuninstall.check_data_dir(P.home()))
        self.assertIsNotNone(selfuninstall.check_data_dir(P("/")))
        base = P(tempfile.mkdtemp())
        (base / "Thesis").mkdir()
        (base / "Thesis" / "a.txt").write_text("x")
        self.assertIsNotNone(selfuninstall.check_data_dir(base))               # someone else's files, no Legacy Player signature
        (base / "user_data.json").write_text("{}")
        self.assertIsNone(selfuninstall.check_data_dir(base))
        with self.assertRaises(ValueError):
            selfuninstall.execute(P.home(), True, False)

    def test_emulator_folder_with_saves_stays_when_keeping_saves(self):
        data = Path(tempfile.mkdtemp())
        (data / "user_data.json").write_text("{}")
        (data / "emulators" / "dolphin" / "User" / "GC").mkdir(parents=True)
        (data / "emulators" / "dolphin" / "User" / "GC" / "card.raw").write_bytes(b"1")
        (data / "emulators" / "retroarch").mkdir(parents=True)
        (data / "emulators" / "retroarch" / "ra.exe").write_bytes(b"1")
        with mock.patch("launcher.selfuninstall._spawn_cleanup", lambda *a: None):
            out = selfuninstall.execute(data, True, False)
        self.assertTrue((data / "emulators" / "dolphin" / "User" / "GC" / "card.raw").exists())
        self.assertFalse((data / "emulators" / "retroarch").exists())
        self.assertEqual(["dolphin"], next(s for s in out["steps"] if s["key"] == "emulators")["kept_with_saves"])
