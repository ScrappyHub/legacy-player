import unittest

from launcher import servercode
from server.lobby import LobbyError
from tests.test_waitlist import join, room
from tests.test_community_lobby import auth


class ServerCodeTests(unittest.TestCase):
    def test_round_trip_and_forgiving_typing(self):
        code = servercode.encode("192.168.1.20", 8765, "ab:cd:ef:01:23:45:67")
        self.assertTrue(code.startswith("LP-"))
        want = {"host": "192.168.1.20", "port": 8765, "fingerprint": "abcdef0123"}
        self.assertEqual(want, servercode.decode(code))
        self.assertEqual(want, servercode.decode(code.lower().replace("-", " ")))
        self.assertEqual(want, servercode.decode(code.replace("0", "O")))   # O typed for zero

    def test_bad_codes_and_hostnames_are_refused(self):
        for bad in ["", "LP-1234", "LP-" + "U" * 18 + "!"]:
            with self.assertRaises(servercode.CodeError):
                servercode.decode(bad)
        with self.assertRaises(servercode.CodeError):
            servercode.encode("example.com", 8765, "aa" * 8)


class StatsAndStartTests(unittest.TestCase):
    def setUp(self):
        self.service, self.sid, self.host, self.code = room(max_players=3)
        joined = join(self.service, self.code, "guest")
        self.guest = auth(self.sid, "guest", joined["credential"])

    def d(self, op, who, **kw):
        return self.service.dispatch({"operation": op, **who, **kw})

    def test_stats_are_numbers_only_and_averaged(self):
        self.d("report_stats", self.host, ping_ms=20, rx_kbps=100, tx_kbps=50, updates_per_s=60)
        self.d("report_stats", self.guest, ping_ms=40, rx_kbps=50, tx_kbps=100, updates_per_s=58)
        view = self.d("status", self.host)["stats"]
        self.assertEqual(30.0, view["average"]["ping_ms"])
        self.assertEqual({"host", "guest"}, set(view["people"]))
        for bad in ({"ping_ms": "fast"}, {"ping_ms": -1}, {"rx_kbps": True}, {"ping_ms": float("nan")}):
            with self.assertRaises(LobbyError):
                self.d("report_stats", self.guest, **bad)

    def test_stats_disappear_when_a_player_leaves(self):
        self.d("report_stats", self.guest, ping_ms=40)
        self.d("leave", self.guest)
        self.assertNotIn("guest", self.d("status", self.host)["stats"]["people"])

    def test_start_needs_the_host_and_each_guest_agrees_for_themselves(self):
        with self.assertRaises(LobbyError):
            self.d("announce_start", self.guest, title="x")
        started = self.d("announce_start", self.host, title="Mario Kart 64")["start"]
        self.assertEqual(["host"], started["consented"])
        self.assertEqual(["guest"], started["waiting_on"])
        with self.assertRaises(LobbyError):
            self.d("consent_start", self.guest, start_id=started["id"] + 1)
        done = self.d("consent_start", self.guest, start_id=started["id"])["start"]
        self.assertEqual([], done["waiting_on"])

    def test_changing_the_game_cancels_a_pending_start(self):
        self.d("announce_start", self.host, title="A")
        self.d("set_game", self.host, title="B", profile={"game_id": "other", "region": "usa"})
        self.assertIsNone(self.d("status", self.guest)["start"])
        with self.assertRaises(LobbyError):
            self.d("set_game", self.guest, title="C", profile={"game_id": "other", "region": "usa"})


if __name__ == "__main__":
    unittest.main()


class AppConnectTests(unittest.TestCase):
    def test_connect_by_code_sets_address_tls_and_pin_and_local_resets_it(self):
        import tempfile
        from pathlib import Path
        from launcher.app import LauncherApp, AppError
        with tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp))
            code = servercode.encode("10.1.2.3", 9100, "aa" * 16)
            app.api_server_status = lambda body: {"online": False, "message": "nobody home"}
            result = app.api_server_connect({"code": code})
            self.assertFalse(result["connected"])
            s = app.catalog.settings()
            self.assertEqual(("10.1.2.3", 9100, True, "aaaaaaaaaa"), (s["server_host"], s["server_port"], s["server_tls"], s["server_fingerprint"]))
            with self.assertRaises(AppError):
                app.api_server_connect({"code": "nonsense"})
            app.api_server_connect({"local": True})
            s = app.catalog.settings()
            self.assertEqual(("127.0.0.1", False, "-"), (s["server_host"], s["server_tls"], s["server_fingerprint"]))

    def test_start_and_consent_need_explicit_yes(self):
        import tempfile
        from pathlib import Path
        from launcher.app import LauncherApp, AppError
        with tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp))
            with self.assertRaises(AppError):
                app.api_mp_start({"consent": True})      # not in a room
            app.room = {"role": "host"}
            with self.assertRaises(AppError):
                app.api_mp_start({})                      # host did not confirm
            app.room = {"role": "guest"}
            with self.assertRaises(AppError):
                app.api_mp_consent({})                    # guest did not agree


class WindowStatusTests(unittest.TestCase):
    def test_status_summary_and_quit(self):
        import tempfile, time
        from pathlib import Path
        from launcher.app import LauncherApp
        with tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp))
            self.assertEqual({"game": None, "room": None, "waits": []}, app.api_status({}))
            app.running = {"title": "Mario Kart 64"}
            app.room = {"game": "Mario Kart 64", "role": "host", "max_players": 4,
                        "session": {"participants": {"a": {}, "b": {}}}, "stats": {"average": {"ping_ms": 28.4}}}
            got = app.api_status({})
            self.assertEqual(("Mario Kart 64", 2, 4, 28.4), (got["game"], got["room"]["players"], got["room"]["max"], got["room"]["ping_ms"]))
            self.assertFalse(app.should_exit(time.time()))
            app.room = None
            app.api_quit({})
            self.assertTrue(app.should_exit(time.time()))


class PcScanTests(unittest.TestCase):
    def test_scan_finds_by_name_respects_depth_and_skips_system_folders(self):
        import tempfile
        from pathlib import Path
        from launcher.pcscan import scan, standard_roots
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            for rel in ["Dolphin/Dolphin-x64/Dolphin.exe", "a/b/c/d/deep/mGBA.exe", "Ps2/PCSX2/pcsx2-qt.exe", "Windows/x/Dolphin.exe"]:
                (t / rel).parent.mkdir(parents=True, exist_ok=True)
                (t / rel).write_bytes(b"x")
            wanted = {"dolphin": ["Dolphin.exe"], "mgba": ["mGBA.exe"], "pcsx2": ["pcsx2-qt.exe"]}
            got = scan([(t, 3)], wanted)
            self.assertEqual({"dolphin", "pcsx2"}, set(got))
            self.assertEqual(1, len(got["dolphin"]))          # the one under Windows/ was skipped
            self.assertIn("mgba", scan([(t, 6)], wanted))
        win = standard_roots({"ProgramFiles": "C:\\Program Files", "LOCALAPPDATA": "C:\\u\\AppData\\Local", "USERPROFILE": "C:\\u"}, "win32")
        names = [str(p) for p, _ in win]
        self.assertTrue(any("Program Files" in n for n in names))
        self.assertTrue(any(n.endswith("Downloads") for n in names))

    def test_scan_needs_consent(self):
        import tempfile
        from pathlib import Path
        from launcher.app import LauncherApp, AppError
        with tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp))
            with self.assertRaises(AppError):
                app.api_scan_pc({"action": "start"})
            self.assertEqual("idle", app.api_scan_pc({})["state"])


class IdleSeatTests(unittest.TestCase):
    def _room(self):
        from server.lobby import LobbyService
        from tests.test_community_lobby import FakeClock, PROFILE, auth
        clock = FakeClock()
        service = LobbyService(clock=clock, heartbeat_timeout=10_000)
        created = service.dispatch({"operation": "create", "participant_id": "host", "profile": PROFILE, "adapter_id": "retroarch",
                                    "game_pack_id": "generic", "require_approval": False, "max_players": 2})
        sid = created["session"]["session_id"]
        host = auth(sid, "host", created["credential"])
        g = service.dispatch({"operation": "join", "invite_code": created["invite_code"], "participant_id": "idle", "profile": PROFILE})
        return service, clock, sid, host, created["invite_code"], auth(sid, "idle", g["credential"]), PROFILE

    def test_nobody_waiting_means_nobody_is_removed(self):
        service, clock, sid, host, code, idle, profile = self._room()
        service.dispatch({"operation": "validate", **host})
        service.dispatch({"operation": "set_endpoint", "kind": "relay", **host})
        clock.now += 1000
        service.sweep_disconnected()
        self.assertIn("idle", service.dispatch({"operation": "status", **host})["session"]["participants"])

    def test_idle_seat_is_released_for_someone_waiting_but_connected_players_stay(self):
        service, clock, sid, host, code, idle, profile = self._room()
        service.dispatch({"operation": "validate", **host})
        service.dispatch({"operation": "set_endpoint", "kind": "relay", **host})
        waiting = service.dispatch({"operation": "join", "invite_code": code, "participant_id": "next", "profile": profile})
        self.assertEqual("waiting", waiting["status"])
        def poll():
            try:
                service.dispatch({"operation": "join_status", "session_id": sid, "participant_id": "next", "request_token": waiting["request_token"]})
            except LobbyError:
                pass   # already let in
        def wait(seconds):
            for _ in range(seconds // 40):
                clock.now += 40
                poll()
                service.sweep_disconnected()
        wait(120)
        self.assertIn("idle", service.dispatch({"operation": "status", **host})["session"]["participants"])   # still inside the grace period
        service.dispatch({"operation": "report_stats", "in_match": True, "ping_ms": 20, **idle})
        wait(240)
        self.assertIn("idle", service.dispatch({"operation": "status", **host})["session"]["participants"])   # connected: keeps the seat
        service.dispatch({"operation": "report_stats", "in_match": False, **idle})
        wait(240)
        self.assertNotIn("idle", service.dispatch({"operation": "status", **host})["session"]["participants"])


class EngineSourceTests(unittest.TestCase):
    def test_source_details_static_and_lookup_gated_by_internet_setting(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from launcher import app as appmod
        from launcher.app import LauncherApp, AppError
        with tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp))
            info = app.api_engines_source({"engine": "pcsx2"})
            self.assertEqual("https://github.com/PCSX2/pcsx2", info["repo_url"])
            self.assertIn("api.github.com", info["hosts"])
            self.assertNotIn("release", info)
            with self.assertRaises(AppError):
                app.api_engines_source({"engine": "pcsx2", "lookup": True})        # internet off
            app.catalog.set_setting("allow_internet", True)
            fake = {"tag": "v2.0.0", "name": "2.0", "published_at": "2026-01-01T00:00:00Z", "prerelease": False, "page": "https://github.com/x/y/releases/tag/v2.0.0",
                    "assets": [{"name": "pcsx2-v2.0.0-windows-x64-Qt.7z", "url": "https://github.com/x/y/a.7z", "size": 1048576, "sha256": "ab" * 32},
                               {"name": "other.zip", "url": "u", "size": 1, "sha256": ""}]}
            with mock.patch.object(appmod, "latest_release", return_value=fake):
                got = app.api_engines_source({"engine": "pcsx2", "lookup": True})
            self.assertEqual("v2.0.0", got["release"]["tag"])
            self.assertEqual("pcsx2-v2.0.0-windows-x64-Qt.7z", got["release"]["asset"]["name"])
            self.assertEqual(1, got["release"]["other_assets"])
            self.assertEqual("page", app.api_engines_source({"engine": "dolphin"}).get("kind"))


class HomeProfileTests(unittest.TestCase):
    def test_program_names_and_archives(self):
        from launcher import emulators
        for name, eid in [("snes9x.exe", "snes9x"), ("Snes9x-x64.exe", "snes9x"), ("xemu.exe", "xemu"), ("bsnes.exe", "bsnes"), ("PPSSPPWindows64.exe", "ppsspp")]:
            self.assertEqual(emulators.program_for(name), eid)
        for name in ("azahar-room.exe", "DolphinTool.exe", "uninst.exe", "unins000.exe"):
            self.assertIsNone(emulators.program_for(name))
        self.assertEqual(emulators.archive_for("xemu-win-x86_64-release.zip"), "xemu")

    def test_alias_tags_are_unique_among_active_players(self):
        from server.lobby.service import LobbyService, LobbyError
        clock = type("C", (), {"now": 1000.0})()
        svc = LobbyService(clock=lambda: clock.now)
        a = svc.claim_alias({"alias": "Al", "install_id": "aaaa"})
        b = svc.claim_alias({"alias": "al", "install_id": "bbbb"})
        self.assertNotEqual(a["tag"], b["tag"])
        self.assertEqual(svc.claim_alias({"alias": "Al", "install_id": "aaaa"})["tag"], a["tag"])   # stable for the same install
        with self.assertRaises(LobbyError):
            svc.claim_alias({"alias": "bad<>", "install_id": "aaaa"})
        clock.now += 2000      # inactive: the tag is free again
        c = svc.claim_alias({"alias": "Al", "install_id": "cccc", "tag": a["tag"]})
        self.assertEqual(c["tag"], a["tag"])

    def test_profile_storage_home_and_featured(self):
        import tempfile
        from pathlib import Path
        from launcher.app import LauncherApp
        app = LauncherApp(Path(tempfile.mkdtemp()))
        p = app.api_profile({"alias": "Neo", "avatar": "robot"})
        self.assertEqual(p["alias"], "Neo")
        self.assertTrue(p["player"].startswith("Neo#"))
        self.assertEqual(app.api_storage({})["total_games"], 0)
        app.catalog.set_setting("featured_title", "Game night")
        self.assertEqual(app.api_home({})["featured"]["title"], "Game night")
        from launcher.catalog import CatalogError
        with self.assertRaises(CatalogError):
            app.catalog.set_setting("featured_link", "http://x")
        self.assertIn("consoles", app.api_engines({}))


class CoversBackupsVideoTests(unittest.TestCase):
    def test_cover_candidates_and_fetch(self):
        import tempfile, time
        from pathlib import Path
        from launcher import covers
        game = {"id": "g1", "title": "Super Test", "path": "/x/Super Test (USA).nes", "region": "USA", "console": "nes"}
        self.assertEqual(covers.candidates(game)[0], "Super Test (USA)")
        self.assertEqual(covers.clean_name("A: B/C"), "A_ B_C")
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        asked = []

        class Resp:
            def __init__(self, data): self.data = data
            def read(self, n): return self.data[:n]
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def opener(req, timeout=0):
            asked.append(req.full_url)
            if "Super%20Test%20%28USA%29" in req.full_url:
                return Resp(png)
            import urllib.error
            raise urllib.error.URLError("404")
        f = covers.CoverFetcher(Path(tempfile.mkdtemp()), opener=opener, pause=0)
        f.start([game, {**game, "id": "g2", "title": "Nope", "path": "/x/Nope.nes"}])
        for _ in range(100):
            if f.state != "running": break
            time.sleep(0.05)
        self.assertEqual((f.state, f.found, f.done), ("done", 1, 2))
        self.assertTrue(covers.cover_path(f.cache, "g1").is_file())
        self.assertTrue(all(u.startswith("https://thumbnails.libretro.com/") for u in asked))

    def test_whole_library_backup_and_restore(self):
        import tempfile
        from pathlib import Path
        from launcher import saves
        base = Path(tempfile.mkdtemp())
        nes = base / "nes"; nes.mkdir()
        (nes / "a.srm").write_bytes(b"one")
        dest = base / "bk"
        made = saves.backup_all({"nes": nes}, dest)
        self.assertEqual(made["files"], 1)
        (nes / "a.srm").write_bytes(b"changed")
        saves.restore_all(dest, made["name"], {"nes": nes}, base / "safety")
        self.assertEqual((nes / "a.srm").read_bytes(), b"one")
        self.assertTrue(list((base / "safety").glob("*.zip")))     # what was there is kept
        with self.assertRaises(ValueError):
            saves.restore_all(dest, "../evil.zip", {"nes": nes}, base / "safety")
        with self.assertRaises(ValueError):
            saves.backup_all({"nes": base / "nothing"}, dest)

    def test_video_settings_and_retroarch_without_core(self):
        import tempfile
        from pathlib import Path
        from launcher.app import LauncherApp, AppError
        app = LauncherApp(Path(tempfile.mkdtemp()))
        app.api_video({"scope": "all", "key": "fullscreen", "value": True})
        app.api_video({"scope": "snes", "key": "fullscreen", "value": False})
        self.assertTrue(app._video_for("nes")["fullscreen"])
        self.assertFalse(app._video_for("snes")["fullscreen"])
        with self.assertRaises(AppError):
            app.api_video({"scope": "all", "key": "bogus", "value": True})
        ra = Path(tempfile.mkdtemp()) / "retroarch.exe"; ra.write_text("x")
        app.catalog.set_mapping("emulator_paths", "retroarch", str(ra))
        self.assertFalse(app._core_ok("nes", str(ra)))
        self.assertIsNone(app._emulator_for("nes")[0])      # installed, but no core: not "ready"
        (ra.parent / "cores").mkdir()
        import sys
        from adapters.retroarch.netplay import CORE_SUFFIXES, CORES
        (ra.parent / "cores" / (CORES["nes"][0] + CORE_SUFFIXES.get(sys.platform, ".so"))).write_text("x")
        self.assertEqual(app._emulator_for("nes")[0], "retroarch")
