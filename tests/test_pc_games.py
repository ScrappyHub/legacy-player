import json
import tempfile
import unittest
from pathlib import Path

from launcher import engines, pcgames, portmap


def make_steam(root: Path):
    apps = root / "steamapps"
    apps.mkdir(parents=True)
    other = root / "lib2"
    (other / "steamapps").mkdir(parents=True)
    (apps / "libraryfolders.vdf").write_text('"libraryfolders"\n{\n "0" { "path" "%s" }\n "1" { "path" "%s" }\n}\n' % (str(root).replace("\\", "\\\\"), str(other).replace("\\", "\\\\")))
    (apps / "appmanifest_620.acf").write_text('"AppState"\n{\n "appid" "620"\n "name" "Portal 2"\n "StateFlags" "4"\n "SizeOnDisk" "1000"\n}\n')
    (other / "steamapps" / "appmanifest_730.acf").write_text('"AppState"\n{\n "appid" "730"\n "name" "Counter-Strike 2"\n "StateFlags" "4"\n}\n')
    (apps / "appmanifest_228980.acf").write_text('"AppState"\n{\n "appid" "228980"\n "name" "Steamworks Common Redistributables"\n "StateFlags" "4"\n}\n')
    (apps / "appmanifest_999.acf").write_text('"AppState"\n{\n "appid" "999"\n "name" "Half Installed"\n "StateFlags" "1026"\n}\n')


class PcGames(unittest.TestCase):
    def test_steam_games_across_libraries(self):
        with tempfile.TemporaryDirectory() as d:
            make_steam(Path(d) / "Steam")
            games = pcgames.steam_games({"STEAM_ROOT": str(Path(d) / "Steam")})
        self.assertEqual({"Portal 2", "Counter-Strike 2"}, {g["title"] for g in games})
        self.assertIn("steam://rungameid/620", {g["uri"] for g in games})

    def test_epic_games_skip_addons_and_unfinished(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.item").write_text(json.dumps({"DisplayName": "Fortnite", "AppName": "Fortnite", "CatalogNamespace": "fn", "CatalogItemId": "abc", "AppCategories": ["public", "games"], "InstallSize": 5}))
            (Path(d) / "b.item").write_text(json.dumps({"DisplayName": "Add-on", "AppName": "Dlc", "MainGameAppName": "Fortnite", "AppCategories": ["games"]}))
            (Path(d) / "c.item").write_text(json.dumps({"DisplayName": "Partial", "AppName": "P", "bIsIncompleteInstall": True}))
            (Path(d) / "d.item").write_text("not json")
            games = pcgames.epic_games({"EPIC_MANIFESTS": d})
        self.assertEqual(["Fortnite"], [g["title"] for g in games])
        self.assertEqual("com.epicgames.launcher://apps/fn%3Aabc%3AFortnite?action=launch&silent=true", games[0]["uri"])

    def test_library_entries_have_library_shape_and_only_safe_launch_addresses(self):
        with tempfile.TemporaryDirectory() as d:
            make_steam(Path(d) / "Steam")
            entries = pcgames.library_entries({"STEAM_ROOT": str(Path(d) / "Steam"), "EPIC_MANIFESTS": d})
        self.assertTrue(entries)
        for e in entries:
            self.assertEqual("pc", e["console"])
            for key in ("id", "title", "sort_title", "region", "tags", "path", "root", "size", "extension", "is_archive", "compat_id"):
                self.assertIn(key, e)
        with self.assertRaises(ValueError):
            pcgames.launch("https://example.com/")
        with self.assertRaises(ValueError):
            pcgames.launch("steam://run/../../x")

    def test_rpcs3_asset_names_old_and_new(self):
        import re
        pattern = re.compile(engines.ENGINES["rpcs3"]["source"]["asset"])
        for name in ("rpcs3-v0.0.35-17936-7f6a2cd4_win64.7z", "rpcs3-v0.0.37-18174-3d1f2a4b_win64_msvc.7z"):
            self.assertTrue(pattern.search(name), name)
        self.assertFalse(pattern.search("rpcs3-v0.0.37-18174-3d1f2a4b_win_aarch64.7z"))

    def test_router_search_goes_out_on_every_adapter(self):
        calls = []
        orig_ips, orig_from = portmap._local_ipv4_addresses, portmap._search_from
        try:
            portmap._local_ipv4_addresses = lambda: ["192.168.1.5", "10.0.0.2"]
            portmap._search_from = lambda source, timeout, found: calls.append(source)
            self.assertEqual([], portmap._find_locations(4))
        finally:
            portmap._local_ipv4_addresses, portmap._search_from = orig_ips, orig_from
        self.assertEqual(["192.168.1.5", "10.0.0.2", None], calls)


if __name__ == "__main__":
    unittest.main()
