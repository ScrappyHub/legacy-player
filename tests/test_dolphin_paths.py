import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import dolphinpaths


class DolphinPathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.user = Path(self.tmp.name) / "User"
        (self.user / "Config").mkdir(parents=True)
        self.ini = self.user / "Config" / "Dolphin.ini"
        p = mock.patch("launcher.dolphinpaths.find_user_dir", return_value=self.user)
        p.start()
        self.addCleanup(p.stop)

    def add(self, folder="C:/Games/GC"):
        return dolphinpaths.add_game_folder("dolphin.exe", folder)

    def test_adds_to_empty_file(self):
        self.assertTrue(self.add()["added"])
        text = self.ini.read_text()
        self.assertIn("[General]", text)
        self.assertIn("ISOPaths = 1", text)
        self.assertIn("ISOPath0 = C:/Games/GC", text)

    def test_appends_and_keeps_everything_else(self):
        self.ini.write_text("[General]\nISOPaths = 1\nISOPath0 = D:/Roms\nOther = 5\n[Core]\nSkipIPL = True\n")
        self.assertTrue(self.add()["added"])
        text = self.ini.read_text()
        self.assertIn("ISOPaths = 2", text)
        self.assertIn("ISOPath0 = D:/Roms", text)
        self.assertIn("ISOPath1 = C:/Games/GC", text)
        self.assertIn("Other = 5", text)
        self.assertLess(text.index("ISOPath1"), text.index("[Core]"))
        self.assertIn("SkipIPL = True", text)

    def test_already_present_is_left_alone_and_backup_made_once(self):
        self.ini.write_text("[General]\nISOPaths = 1\nISOPath0 = c:\\games\\gc\nRecursiveISOPaths = True\n")
        before = self.ini.read_text()
        self.assertFalse(self.add()["added"])
        self.assertEqual(self.ini.read_text(), before)
        self.assertFalse((self.ini.parent / dolphinpaths.BACKUP).exists())

    def test_backup_of_original(self):
        self.ini.write_text("[Core]\nX = 1\n")
        self.add()
        self.assertEqual((self.ini.parent / dolphinpaths.BACKUP).read_text(), "[Core]\nX = 1\n")
        self.add("C:/More")
        self.assertEqual((self.ini.parent / dolphinpaths.BACKUP).read_text(), "[Core]\nX = 1\n")

    def test_no_settings_folder_does_not_raise(self):
        with mock.patch("launcher.dolphinpaths.find_user_dir", return_value=None):
            self.assertFalse(self.add()["added"])

    def test_many_folders_and_search_subfolders(self):
        self.ini.write_text("[General]\nISOPaths = 0\nRecursiveISOPaths = False\n")
        out = dolphinpaths.add_game_folders("dolphin.exe", ["C:/A", "C:/B", "c:\\a"])
        self.assertEqual(out["added"], ["C:/A", "C:/B"])
        text = self.ini.read_text()
        self.assertIn("ISOPaths = 2", text)
        self.assertIn("RecursiveISOPaths = True", text)
        self.assertNotIn("False", text)

    def test_newest_settings_folder_wins(self):
        from launcher import dolphinpads
        a, b = Path(self.tmp.name) / "a", Path(self.tmp.name) / "b"
        for d, t in ((a, 100), (b, 200)):
            (d / "Config").mkdir(parents=True)
            os.utime((d / "Config" / "Dolphin.ini").write_text("x") and d / "Config" / "Dolphin.ini", (t, t))
        with mock.patch("launcher.dolphinpads.user_dirs", return_value=[a, b]):
            self.assertEqual(dolphinpads.find_user_dir("dolphin.exe"), b)


if __name__ == "__main__":
    unittest.main()
