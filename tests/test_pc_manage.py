import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import pcgames
from launcher.app import LauncherApp

JPG = b"\xff\xd8\xff\xe0" + b"0" * 200
ENTRIES = [
    {"id": "steam-111", "console": "pc", "title": "Hades", "sort_title": "hades", "region": "", "tags": ["Steam"], "path": "steam://rungameid/111",
     "root": "steam", "size": 1, "extension": ".steam", "is_archive": False, "compat_id": "pc:steam:hades"},
    {"id": "epic-abc", "console": "pc", "title": "Fortnite", "sort_title": "fortnite", "region": "", "tags": ["Epic"],
     "path": "com.epicgames.launcher://apps/abc?action=launch&silent=true", "root": "epic", "size": 1, "extension": ".epic", "is_archive": False,
     "compat_id": "pc:epic:fortnite"},
]


class SteamArtTests(unittest.TestCase):
    def test_finds_old_and_new_layouts_and_skips_big_files(self):
        root = Path(tempfile.mkdtemp())
        (root / "steamapps").mkdir()
        cache = root / "appcache" / "librarycache"
        (cache / "222" / "abcd").mkdir(parents=True)
        (cache / "111_library_600x900.jpg").parent.mkdir(parents=True, exist_ok=True)
        (cache / "111_library_600x900.jpg").write_bytes(JPG)
        (cache / "222" / "abcd" / "library_600x900.jpg").write_bytes(JPG)
        (cache / "333_library_600x900.jpg").write_bytes(b"x" * 700_000)
        env = {"STEAM_ROOT": str(root)}
        self.assertEqual(JPG, pcgames.steam_art("111", env))
        self.assertEqual(JPG, pcgames.steam_art("222", env))
        self.assertIsNone(pcgames.steam_art("333", env))
        self.assertIsNone(pcgames.steam_art("not-a-number", env))

    def test_names_meet_in_the_middle(self):
        self.assertEqual(pcgames.match_key("Hades II (2024)"), pcgames.match_key("hades ii"))


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.app = LauncherApp(Path(tempfile.mkdtemp()))
        patcher = mock.patch("launcher.app.pcgames.library_entries", return_value=[dict(e) for e in ENTRIES])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app.rescan()

    def test_hide_and_show_games_and_stores(self):
        out = self.app.api_pc_games({"action": "hide", "ids": ["steam-111"], "hidden": True})
        self.assertEqual({"steam-111": True, "epic-abc": False}, {g["id"]: g["hidden"] for g in out["games"]})
        self.assertNotIn("steam-111", [g["id"] for g in self.app.api_library({})["games"]])
        out = self.app.api_pc_games({"action": "hide", "all": True, "hidden": False})
        self.assertEqual([False, False], [g["hidden"] for g in out["games"]])
        out = self.app.api_pc_games({"action": "stores", "show_epic_games": False})
        self.assertEqual(["Hades"], [g["title"] for g in out["games"]])
        out = self.app.api_pc_games({"action": "stores", "show_pc_games": False})
        self.assertEqual([], out["games"])

    def test_steam_pictures_are_copied_but_never_over_a_pick(self):
        with mock.patch("launcher.app.pcgames.steam_art", return_value=JPG):
            out = self.app.api_pc_games({"action": "seed_covers"})
            self.assertEqual(1, out["seeded"])                   # Steam only: Epic keeps no pictures
            self.assertEqual({"steam-111": True, "epic-abc": False}, {g["id"]: g["cover"] for g in out["games"]})
            self.assertEqual(0, self.app.api_pc_games({"action": "seed_covers"})["seeded"])   # the picture is already there

    def test_folder_of_pictures_matches_by_name(self):
        folder = Path(tempfile.mkdtemp())
        (folder / "fortnite.jpg").write_bytes(JPG)
        (folder / "Something Else.png").write_bytes(JPG)
        out = self.app.api_pc_games({"action": "import_folder", "path": str(folder)})
        self.assertEqual(1, out["imported"])
        self.assertTrue(next(g for g in out["games"] if g["id"] == "epic-abc")["cover"])


class BackgroundTests(unittest.TestCase):
    def test_new_backgrounds_exist_in_the_setting_and_the_page(self):
        from launcher.catalog import SETTINGS_SCHEMA
        choices = SETTINGS_SCHEMA["background"]["choices"]
        self.assertGreaterEqual(len(choices), 8)
        ui = (Path(__file__).resolve().parent.parent / "launcher" / "ui" / "index.html").read_text(encoding="utf-8")
        for name in ("crt", "bokeh", "bitworld", "bitcity", "bitforest"):
            self.assertIn(name, choices)
            self.assertIn(f"[data-bg={name}]", ui)
        self.assertIn("const BitWorld", ui)


if __name__ == "__main__":
    unittest.main()
