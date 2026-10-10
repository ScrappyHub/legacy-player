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


def _jpeg(w: int, h: int) -> bytes:
    """The smallest JPEG header that carries a size (SOI, one SOF0 frame, EOI); enough for the shape check."""
    sof = b"\xff\xc0" + (11).to_bytes(2, "big") + b"\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big") + b"\x01\x01\x11\x00"
    return b"\xff\xd8" + sof + b"\xff\xd9"


class SteamPicturesAndHiddenGames(unittest.TestCase):
    def test_image_size_reads_png_and_jpeg_headers(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (460).to_bytes(4, "big") + (215).to_bytes(4, "big")
        self.assertEqual((460, 215), pcgames.image_size(png))
        self.assertEqual((300, 450), pcgames.image_size(_jpeg(300, 450)))
        self.assertIsNone(pcgames.image_size(b"not a picture"))

    def test_steam_art_reads_all_three_cache_layouts_and_the_players_own_choice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Steam"
            make_steam(root)
            env = {"STEAM_ROOT": str(root)}
            cache = root / "appcache" / "librarycache"
            # oldest: flat file named after the app
            cache.mkdir(parents=True)
            (cache / "620_library_600x900.jpg").write_bytes(_jpeg(600, 900) + b"old")
            self.assertTrue(pcgames.steam_art("620", env).endswith(b"old"))
            # 2024: a folder per app, a folder per version, the usual names inside
            (cache / "730" / "0a1b2c").mkdir(parents=True)
            (cache / "730" / "0a1b2c" / "library_600x900.jpg").write_bytes(_jpeg(600, 900) + b"mid")
            self.assertTrue(pcgames.steam_art("730", env).endswith(b"mid"))
            # newest: files named by content; the tall one is the cover, the wide one is the header
            (cache / "999").mkdir()
            (cache / "999" / "7b45d809a40cf4f7763748c98fc863c2.jpg").write_bytes(_jpeg(920, 430) + b"wide")
            (cache / "999" / "c98fc863c27b45d809a40cf4f7763748.jpg").write_bytes(_jpeg(300, 450) + b"tall")
            self.assertTrue(pcgames.steam_art("999", env).endswith(b"tall"))
            # a wide header is still better than nothing
            (cache / "111").mkdir()
            (cache / "111" / "x.jpg").write_bytes(_jpeg(920, 430) + b"onlywide")
            (cache / "111_header.jpg").write_bytes(_jpeg(460, 215) + b"flatheader")
            self.assertTrue(pcgames.steam_art("111", env).endswith(b"flatheader"))
            # the picture chosen inside Steam wins over everything
            grid = root / "userdata" / "12345" / "config" / "grid"
            grid.mkdir(parents=True)
            (grid / "620p.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16 + b"mine")
            self.assertTrue(pcgames.steam_art("620", env).endswith(b"mine"))
            self.assertIsNone(pcgames.steam_art("424242", env))
            self.assertIsNone(pcgames.steam_art("not-an-id", env))

    def test_hidden_inside_steam_is_read_from_sharedconfig(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Steam"
            make_steam(root)
            remote = root / "userdata" / "12345" / "7" / "remote"
            remote.mkdir(parents=True)
            (remote / "sharedconfig.vdf").write_text('"UserRoamingConfigStore"\n{\n "Software"\n {\n  "Valve"\n  {\n   "Steam"\n   {\n    "apps"\n    {\n'
                                                     '     "620"\n     {\n      "tags"\n      {\n       "0" "favorite"\n      }\n      "Hidden" "1"\n     }\n'
                                                     '     "730"\n     {\n      "LastPlayed" "1700000000"\n     }\n    }\n   }\n  }\n }\n}\n')
            self.assertEqual({"620"}, pcgames.steam_hidden({"STEAM_ROOT": str(root)}))
            info = pcgames.steam_diagnostics({"STEAM_ROOT": str(root)})
        self.assertTrue(info["found"])
        self.assertEqual(2, info["games"])
        self.assertEqual(2, len(info["libraries"]))
        self.assertFalse(pcgames.steam_diagnostics({"STEAM_ROOT": str(Path(d) / "nowhere")})["found"])
