import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from launcher import emulators, gamefinder
from tests.test_app_actions import make_app

EXES = {n.lower() for v in emulators.EMULATORS.values() for n in v["exes"]}


def touch(root: Path, *names):
    for n in names:
        p = root / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")


class FinderTests(unittest.TestCase):
    def layout(self):
        d = Path(tempfile.mkdtemp())
        touch(d, *[f"Library/GBA/g{i}.gba" for i in range(4)], *[f"Library/SNES/s{i}.sfc" for i in range(3)],
              "Library/README.md", "Library/Emulators/stuff/x.nes", "Library/ZZZ-old/y.nes",
              *[f"Docs/notes{i}.md" for i in range(9)],
              "Downloads/one.nes", "Downloads/two.nes",
              "Dolphin/Dolphin.exe", *[f"Dolphin/Sys/a{i}.gba" for i in range(5)])
        return d

    def test_finds_the_library_not_the_emulators_or_documents(self):
        d = self.layout()
        with mock.patch("launcher.gamefinder._is_wide", side_effect=lambda p: p == d or p.name.lower() in gamefinder.WIDE):
            found = gamefinder.find([(d, 5)], EXES)
        self.assertEqual([str(d / "Library")], [f["path"] for f in found])
        self.assertEqual(7, found[0]["games"])                       # the excluded folders, README.md and the emulator's folder never count
        self.assertEqual({"gba": 4, "snes": 3}, found[0]["consoles"])

    def test_two_separate_libraries_stay_separate(self):
        d = Path(tempfile.mkdtemp())
        touch(d, *[f"A/n{i}.nes" for i in range(3)], *[f"B/Roms/s{i}.sfc" for i in range(3)])
        with mock.patch("launcher.gamefinder._is_wide", side_effect=lambda p: p == d):
            found = gamefinder.find([(d, 5)], EXES)
        self.assertEqual({str(d / "A"), str(d / "B")}, {f["path"] for f in found})

    def test_too_few_files_is_not_a_library(self):
        d = Path(tempfile.mkdtemp())
        touch(d, "Stuff/a.nes", "Stuff/b.nes")
        with mock.patch("launcher.gamefinder._is_wide", side_effect=lambda p: p == d):
            self.assertEqual([], gamefinder.find([(d, 5)], EXES))

    def test_cancel(self):
        d = self.layout()
        stop = threading.Event()
        stop.set()
        self.assertEqual([], gamefinder.find([(d, 5)], EXES, stop=stop))


class AutoAddTests(unittest.TestCase):
    def test_full_scan_adds_game_folders_by_itself(self):
        app, _ = make_app()
        d = Path(tempfile.mkdtemp())
        touch(d, *[f"Games/NES/n{i}.nes" for i in range(5)])
        before = list(app.catalog.data["roots"])
        old_games = len(app.games)
        with mock.patch("launcher.gamefinder._is_wide", side_effect=lambda p: p == d):
            out = app._find_games_after_scan([(d, 5)], threading.Event(), None)
        self.assertEqual([str(d / "Games")], out["games_added"])
        self.assertEqual(before + [str(d / "Games")], app.catalog.data["roots"])
        self.assertEqual(old_games + 5, out["games_total"])
        again = None
        with mock.patch("launcher.gamefinder._is_wide", side_effect=lambda p: p == d):
            again = app._find_games_after_scan([(d, 5)], threading.Event(), None)
        self.assertEqual([], again["games_added"])                   # nothing added twice

    def test_a_folder_inside_an_existing_one_is_not_added_and_a_parent_replaces_children(self):
        app, _ = make_app()
        d = Path(tempfile.mkdtemp())
        touch(d, *[f"Games/NES/n{i}.nes" for i in range(5)])
        app.catalog.set_roots([str(d / "Games" / "NES")])
        with mock.patch("launcher.gamefinder._is_wide", side_effect=lambda p: p == d):
            out = app._find_games_after_scan([(d, 5)], threading.Event(), None)
        self.assertEqual([str(d / "Games")], out["games_added"])
        self.assertEqual([str(d / "Games")], app.catalog.data["roots"])


if __name__ == "__main__":
    unittest.main()
