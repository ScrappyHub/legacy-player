import asyncio
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from launcher.app import AppError, LauncherApp
from launcher.catalog import Catalog, CatalogError
from launcher.scanner import clean_title, scan
from launcher.web import make_handler
from server.api.json_server import handle_client
from server.relay import Relay
from server.lobby import LobbyService
from http.server import ThreadingHTTPServer


def touch(path: Path, data: bytes = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def make_library(root: Path):
    touch(root / "NES" / "Battle of Olympus, The (USA).nes")
    touch(root / "SNES" / "Chrono Trigger (USA).sfc")
    touch(root / "GBA" / "Gameboy" / "Tetris (World).gb")
    touch(root / "GBA" / "Gameboy advanced" / "Mario Golf (USA).gba")
    touch(root / "GBA" / "Gameboy advanced" / "Mario Golf (USA).sav", b"save")
    touch(root / "PS2" / "Game A (USA).iso")
    touch(root / "Gamecube" / "Game B (USA).ciso")
    touch(root / "PS1" / "Crash (USA).7z")
    touch(root / "PS1" / "Disc (USA).cue")
    touch(root / "PS1" / "Disc (USA).bin")
    touch(root / "random" / "stray.iso")          # no console hint: must be skipped
    touch(root / "Emulators" / "pcsx2" / "x.nes")  # excluded folder
    touch(root / "ZZZ-Wii" / "games" / "Dup (USA).ciso")


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "Games"
        make_library(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_classifies_by_extension_and_folder(self):
        games = {g.title: g for g in scan([self.root])["games"]}
        self.assertEqual("nes", games["The Battle of Olympus"].console)
        self.assertEqual("gb", games["Tetris"].console)
        self.assertEqual("gba", games["Mario Golf"].console)
        self.assertEqual("ps2", games["Game A"].console)
        self.assertEqual("gamecube", games["Game B"].console)
        self.assertEqual("ps1", games["Crash"].console)
        self.assertTrue(games["Crash"].is_archive)

    def test_skips_unhinted_discs_excluded_folders_and_bin_with_cue(self):
        result = scan([self.root])
        titles = [g.title for g in result["games"]]
        self.assertNotIn("stray", titles)
        self.assertNotIn("x", titles)
        self.assertNotIn("Dup", titles)
        self.assertEqual(1, titles.count("Disc"))
        self.assertTrue(next(g for g in result["games"] if g.title == "Disc").path.endswith(".cue"))

    def test_scan_never_modifies_files(self):
        before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.root.rglob("*") if p.is_file()}
        scan([self.root])
        after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_title_cleaning(self):
        self.assertEqual(("The Legend of Zelda", "USA", ["Rev 1"]), clean_title("Legend of Zelda, The (USA) (Rev 1)"))
        self.assertEqual("Dark Lord", clean_title("Dark_Lord_(Tr)")[0])

    def test_compat_id_matches_across_machines(self):
        other = Path(self.tmp.name) / "Elsewhere"
        touch(other / "SNES" / "Chrono Trigger (USA).sfc")
        mine = next(g for g in scan([self.root])["games"] if g.title == "Chrono Trigger")
        theirs = scan([other])["games"][0]
        self.assertEqual(mine.compat_id, theirs.compat_id)
        self.assertNotEqual(mine.path, theirs.path)


class CatalogTests(unittest.TestCase):
    def test_settings_validation_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            c = Catalog(Path(d))
            c.set_setting("theme", "light")
            with self.assertRaises(CatalogError):
                c.set_setting("theme", "neon")
            with self.assertRaises(CatalogError):
                c.set_setting("server_port", 99999)
            with self.assertRaises(CatalogError):
                c.set_setting("nope", 1)
            c.set_favorite("abc", True)
            again = Catalog(Path(d))
            self.assertEqual("light", again.settings()["theme"])
            self.assertEqual(["abc"], again.data["favorites"])


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "Games"
        make_library(self.root)
        self.app = LauncherApp(Path(self.tmp.name) / "data", roots=[str(self.root)])
        self.app.rescan()

    def tearDown(self):
        self.tmp.cleanup()

    def game(self, title):
        return next(g for g in self.app.api_library({})["games"] if g["title"] == title)

    def test_library_filters_and_favorites(self):
        gba = self.app.api_library({"console": "gba"})
        self.assertEqual(["Mario Golf"], [g["title"] for g in gba["games"]])
        gid = self.game("Tetris")["id"]
        self.app.api_favorite({"id": gid, "favorite": True})
        self.assertEqual(["Tetris"], [g["title"] for g in self.app.api_library({"favorites": True})["games"]])
        self.assertEqual(["Chrono Trigger"], [g["title"] for g in self.app.api_library({"q": "chrono"})["games"]])

    def test_launch_explains_missing_emulator_and_archives(self):
        with self.assertRaisesRegex(AppError, "No emulator set"):
            self.app.api_launch({"id": self.game("Chrono Trigger")["id"]})
        with self.assertRaisesRegex(AppError, "archive"):
            self.app.api_launch({"id": self.game("Crash")["id"]})

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script as a fake emulator")
    def test_launch_uses_configured_emulator_without_a_shell(self):
        script = Path(self.tmp.name) / "fake_emulator.sh"
        out = Path(self.tmp.name) / "args.txt"
        script.write_text(f'#!/bin/sh\nprintf "%s" "$1" > "{out}"\n')
        script.chmod(0o755)
        self.app.api_emulators({"emulator": "snes9x", "path": str(script)})
        result = self.app.api_launch({"id": self.game("Chrono Trigger")["id"]})
        self.assertEqual("Snes9x", result["emulator"])
        for _ in range(50):
            if out.exists():
                break
            import time; time.sleep(0.05)
        self.assertTrue(out.read_text().endswith("Chrono Trigger (USA).sfc"))
        self.assertEqual(1, self.game("Chrono Trigger")["plays"])

    def test_controller_overrides_validate(self):
        self.app.api_controllers({"console": "snes", "buttons": {"A": 3}})
        layout = self.app.api_controllers({"console": "snes"})["layout"]
        self.assertTrue(layout["customized"])
        self.assertEqual(3, next(b for b in layout["buttons"] if b["name"] == "A")["index"])
        with self.assertRaises(AppError):
            self.app.api_controllers({"console": "snes", "buttons": {"Turbo": 1}})
        with self.assertRaises(AppError):
            self.app.api_controllers({"console": "snes", "buttons": {"A": 99}})

    def test_save_backup_and_restore_round_trip(self):
        gid = self.game("Mario Golf")["id"]
        detail = self.app.api_game({"id": gid})
        self.assertEqual(["Mario Golf (USA).sav"], detail["save_files"])
        self.app.api_backup({"id": gid})
        sav = self.root / "GBA" / "Gameboy advanced" / "Mario Golf (USA).sav"
        sav.write_bytes(b"corrupted")
        backup = self.app.api_game({"id": gid})["backups"][0]["backup"]
        result = self.app.api_restore({"id": gid, "backup": backup})
        self.assertEqual(b"save", sav.read_bytes())
        self.assertIsNotNone(result["previous_saves_backed_up_as"])
        with self.assertRaises(AppError):
            self.app.api_restore({"id": gid, "backup": "../../etc"})


class WebSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = LauncherApp(Path(self.tmp.name))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        self.port = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = make_handler(self.app, "tok", lambda: self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def req(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data

    def test_page_is_served_with_token_and_api_requires_it(self):
        status, page = self.req("GET", "/")
        self.assertEqual(200, status)
        self.assertIn(b'const TOKEN="tok"', page)
        self.assertEqual(403, self.req("POST", "/api/settings", {}, {"Content-Type": "application/json"})[0])
        status, data = self.req("POST", "/api/settings", {}, {"Content-Type": "application/json", "X-LP-Token": "tok"})
        self.assertEqual(200, status)
        self.assertIn("schema", json.loads(data))

    def test_rejects_wrong_host_wrong_type_and_unknown_actions(self):
        ok = {"Content-Type": "application/json", "X-LP-Token": "tok"}
        self.assertEqual(403, self.req("POST", "/api/settings", {}, {**ok, "Host": "evil.example"})[0])
        self.assertEqual(415, self.req("POST", "/api/settings", {}, {"Content-Type": "text/plain", "X-LP-Token": "tok"})[0])
        self.assertEqual(404, self.req("POST", "/api/__class__", {}, ok)[0])
        status, data = self.req("POST", "/api/game", {"id": "nope"}, ok)
        self.assertEqual(400, status)
        self.assertIn("Rescan", json.loads(data)["error"])


class ServerThread:
    def __init__(self):
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.service = LobbyService()
        relay = Relay(self.service)
        self.service.relay = relay
        server = self.loop.run_until_complete(asyncio.start_server(
            lambda r, w: handle_client(r, w, self.service, None, None, relay), "127.0.0.1", 0))
        self.server = server
        self.port = server.sockets[0].getsockname()[1]
        self.ready.set()
        self.loop.run_forever()

    def start(self):
        self.thread.start()
        self.ready.wait(5)
        return self

    def stop(self):
        def shutdown():
            self.server.close()
            for task in asyncio.all_tasks(self.loop):
                task.cancel()
            self.loop.call_later(0.05, self.loop.stop)

        self.loop.call_soon_threadsafe(shutdown)
        self.thread.join(2)


class MultiplayerFlowTests(unittest.TestCase):
    def setUp(self):
        self.server = ServerThread().start()
        self.tmp = tempfile.TemporaryDirectory()
        self.apps = {}
        for name in ("Host", "Guest"):
            root = Path(self.tmp.name) / name / "Games"
            touch(root / "SNES" / "Super Bomberman (USA).sfc")
            app = LauncherApp(Path(self.tmp.name) / name / "data", roots=[str(root)])
            app.rescan()
            app.catalog.set_setting("display_name", name)
            app.catalog.set_setting("server_port", self.server.port)
            self.apps[name] = app

    def tearDown(self):
        self.server.stop()
        self.tmp.cleanup()

    def gid(self, app):
        return app.api_library({})["games"][0]["id"]

    def test_single_player_game_cannot_be_hosted(self):
        host = self.apps["Host"]
        root = Path(self.tmp.name) / "Host" / "Games"
        touch(root / "SNES" / "Chrono Trigger (USA).sfc")
        host.rescan()
        solo = next(g for g in host.api_library({})["games"] if "Chrono" in g["title"])
        self.assertEqual(1, solo["players"]["max"])
        with self.assertRaises(AppError):
            host.api_mp_host({"id": solo["id"]})

    def test_room_size_follows_the_game(self):
        host = self.apps["Host"]
        room = host.api_mp_host({"id": self.gid(host), "require_approval": False, "max_players": 8})["room"]
        self.assertEqual(4, room["max_players"])      # Bomberman takes 4; the app will not offer more seats than the game has

    def test_host_approves_guest_then_kicks_and_guest_is_told(self):
        host, guest = self.apps["Host"], self.apps["Guest"]
        room = host.api_mp_host({"id": self.gid(host)})["room"]
        code = room["invite_code"]
        waiting = guest.api_mp_join({"id": self.gid(guest), "invite_code": code})["room"]
        self.assertTrue(waiting["waiting_for_host"])
        self.assertEqual([guest.catalog.player_tag()], host.api_mp_state({})["room"]["pending"])
        host.api_mp_decide({"target": guest.catalog.player_tag(), "approve": True})
        joined = guest.api_mp_state({})["room"]
        self.assertFalse(joined["waiting_for_host"])
        self.assertEqual({host.catalog.player_tag(), guest.catalog.player_tag()}, {m["name"] for m in joined["members"]})
        self.assertEqual([], host.api_mp_state({})["room"]["pending"])
        host.api_mp_kick({"target": guest.catalog.player_tag(), "reason": "afk"})
        result = guest.api_mp_state({})
        self.assertIsNone(result["room"])
        self.assertIn("afk", result["notice"])

    def _extra_app(self, name):
        root = Path(self.tmp.name) / name / "Games"
        touch(root / "SNES" / "Super Bomberman (USA).sfc")
        app = LauncherApp(Path(self.tmp.name) / name / "data", roots=[str(root)])
        app.rescan()
        app.catalog.set_setting("display_name", name)
        app.catalog.set_setting("server_port", self.server.port)
        self.apps[name] = app
        return app

    def test_full_room_has_a_waiting_line_with_priority(self):
        host, guest = self.apps["Host"], self.apps["Guest"]
        third, fourth = self._extra_app("Third"), self._extra_app("Fourth")
        room = host.api_mp_host({"id": self.gid(host), "require_approval": False, "max_players": 2})["room"]
        self.assertEqual(2, room["max_players"])
        code = room["invite_code"]
        guest.api_mp_join({"id": self.gid(guest), "invite_code": code})
        queued = third.api_mp_join({"id": self.gid(third), "invite_code": code})["room"]
        self.assertEqual(1, queued["queue"]["position"])
        self.assertFalse(queued["waiting_for_host"])
        fourth.api_mp_join({"id": self.gid(fourth), "invite_code": code})
        self.assertEqual([third.catalog.player_tag(), fourth.catalog.player_tag()], [w["participant_id"] for w in host.api_mp_state({})["room"]["waitlist"]])
        host.api_mp_priority({"target": fourth.catalog.player_tag(), "priority": True})
        self.assertEqual(1, fourth.api_mp_state({})["room"]["queue"]["position"])
        self.assertEqual(2, third.api_mp_state({})["room"]["queue"]["position"])
        host.api_mp_kick({"target": guest.catalog.player_tag(), "reason": "make room"})
        joined = fourth.api_mp_state({})["room"]
        self.assertIsNone(joined["queue"])
        self.assertEqual({host.catalog.player_tag(), fourth.catalog.player_tag()}, {m["name"] for m in joined["members"]})
        self.assertEqual(1, third.api_mp_state({})["room"]["queue"]["position"])
        third.api_mp_leave({})
        self.assertEqual([], host.api_mp_state({})["room"]["waitlist"])

    def test_open_room_browse_and_queue_while_in_another_room(self):
        host, guest = self.apps["Host"], self.apps["Guest"]
        third = self._extra_app("Third")
        host.api_mp_host({"id": self.gid(host), "require_approval": False, "max_players": 2, "open": True, "label": "Anyone welcome"})
        rooms = guest.api_mp_browse({})["rooms"]
        self.assertEqual(1, len(rooms))
        self.assertEqual(("Anyone welcome", 1, 2, True), (rooms[0]["label"], rooms[0]["players"], rooms[0]["max_players"], rooms[0]["you_have_it"]))
        for forbidden in ("Host#", host.catalog.player_tag(), "credential", "address", "127.0.0.1"):
            self.assertNotIn(forbidden, json.dumps(rooms))
        guest.api_mp_join({"id": self.gid(guest), "session_id": rooms[0]["session_id"]})  # walks in, room now full
        # Third hosts their own room, then queues for the open one in the background while hosting
        third.api_mp_host({"id": self.gid(third), "require_approval": False})
        state = third.api_mp_join({"id": self.gid(third), "session_id": rooms[0]["session_id"], "background": True})
        self.assertEqual("host", state["room"]["role"])
        self.assertEqual(1, state["waits"][0]["position"])
        host.api_mp_kick({"target": guest.catalog.player_tag(), "reason": "bye"})
        state = third.api_mp_state({})
        self.assertTrue(state["waits"][0]["ready"])
        self.assertTrue(any("Switch" in e["text"] for e in state["room"]["new_events"]))
        switched = third.api_mp_switch({"session_id": rooms[0]["session_id"]})
        self.assertEqual("guest", switched["room"]["role"])
        self.assertEqual([], switched["waits"])
        self.assertIn(third.catalog.player_tag(), [m["name"] for m in host.api_mp_state({})["room"]["members"]])

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script as a fake emulator")
    def test_your_turn_closes_the_current_game_politely_and_joins(self):
        from adapters.retroarch import tunnel
        if not tunnel.available():
            self.skipTest("TLS-PSK needs Python 3.13+")
        host, guest = self.apps["Host"], self.apps["Guest"]
        third = self._extra_app("Third")
        host_out, third_out = self.fake_retroarch("Host"), self.fake_retroarch("Third")
        # Third is playing something from the library (a sleeping fake emulator)
        sleeper = Path(self.tmp.name) / "sleeper.sh"
        sleeper.write_text("#!/bin/sh\ntrap 'exit 0' TERM\nsleep 60 & wait\n")
        sleeper.chmod(0o755)
        third.api_emulators({"emulator": "snes9x", "path": str(sleeper)})
        third.catalog.set_mapping("console_emulator", "snes", "snes9x")
        third.api_launch({"id": self.gid(third)})
        self.assertIsNotNone(third.running)
        pid = third.running["pid"]
        room = host.api_mp_host({"id": self.gid(host), "require_approval": False, "max_players": 2, "open": True})["room"]
        sid = host.room["session_id"]
        guest.api_mp_join({"id": self.gid(guest), "invite_code": room["invite_code"]})
        third.api_mp_join({"id": self.gid(third), "session_id": sid, "background": True})
        host.api_mp_kick({"target": guest.catalog.player_tag(), "reason": "done"})
        self.assertTrue(third.api_mp_state({})["waits"][0]["ready"])
        host.api_mp_lock({})
        host.api_mp_launch({"relay": True, "port": 55490})
        self.wait_args(host_out)
        third.catalog.set_mapping("console_emulator", "snes", None)
        state = third.api_mp_switch({"session_id": sid, "close_game": True, "auto_join": True})
        self.assertEqual("Super Bomberman", state["closed_game"])
        import os, time
        for _ in range(40):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except OSError:
                break
        else:
            self.fail("the old game was not closed")
        self.assertIn("joined_match", state, state.get("join_note"))
        self.assertTrue(state["joined_match"]["relay"])
        self.wait_args(third_out)
        host.api_mp_leave({}); third.api_mp_leave({})

    def test_guest_with_wrong_game_is_caught_by_host_check(self):
        host, guest = self.apps["Host"], self.apps["Guest"]
        touch(Path(self.tmp.name) / "Guest" / "Games" / "SNES" / "Other Game (USA).sfc")
        guest.rescan()
        other = next(g for g in guest.api_library({})["games"] if g["title"] == "Other Game")
        room = host.api_mp_host({"id": self.gid(host), "require_approval": False})["room"]
        guest.api_mp_join({"id": other["id"], "invite_code": room["invite_code"]})
        with self.assertRaisesRegex(AppError, "incompatible"):
            host.api_mp_lock({})

    def fake_retroarch(self, name):
        base = Path(self.tmp.name) / name / "ra"
        (base / "cores").mkdir(parents=True)
        (base / "cores" / "snes9x_libretro.so").write_bytes(b"core")
        out = Path(self.tmp.name) / name / "ra_args.txt"
        exe = base / "retroarch"
        exe.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{out}"\n')
        exe.chmod(0o755)
        self.apps[name].api_emulators({"emulator": "retroarch", "path": str(exe)})
        return out

    def wait_args(self, out):
        import time
        for _ in range(60):
            if out.exists() and out.read_text():
                return out.read_text().split()
            time.sleep(0.05)
        self.fail("fake emulator never ran")

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script as a fake emulator")
    def test_host_launches_then_guest_connects_to_published_address(self):
        host, guest = self.apps["Host"], self.apps["Guest"]
        for app in (host, guest):
            app.catalog.set_setting("encrypt_matches", False)  # the encrypted path has its own test
            app.catalog.set_setting("allow_direct_connections", True)
        host_out, guest_out = self.fake_retroarch("Host"), self.fake_retroarch("Guest")
        room = host.api_mp_host({"id": self.gid(host), "require_approval": False})["room"]
        guest.api_mp_join({"id": self.gid(guest), "invite_code": room["invite_code"]})
        with self.assertRaisesRegex(AppError, "Check everyone"):
            host.api_mp_launch({"address": "192.168.1.20", "relay": False, "expose_address": True})
        self.assertFalse(host.api_mp_state({})["room"]["launch"]["ready"])
        host.api_mp_lock({})
        self.assertTrue(host.api_mp_state({})["room"]["launch"]["ready"])
        with self.assertRaisesRegex(AppError, "not launched yet"):
            guest.api_mp_launch({})
        host.api_mp_launch({"address": "192.168.1.20", "port": 55440, "relay": False, "expose_address": True})
        args = self.wait_args(host_out)
        self.assertIn("--host", args)
        self.assertEqual("55440", args[args.index("--port") + 1])
        state = guest.api_mp_state({})["room"]
        self.assertIn("The host has launched. Press Join match.", [e["text"] for e in state["new_events"]])
        guest.api_mp_launch({"expose_address": True})
        gargs = self.wait_args(guest_out)
        self.assertEqual("192.168.1.20", gargs[gargs.index("--connect") + 1])
        self.assertTrue(gargs[gargs.index("--nick") + 1].startswith("Guest"))

    def _ready_room(self):
        host, guest = self.apps["Host"], self.apps["Guest"]
        host_out, guest_out = self.fake_retroarch("Host"), self.fake_retroarch("Guest")
        room = host.api_mp_host({"id": self.gid(host), "require_approval": False})["room"]
        guest.api_mp_join({"id": self.gid(guest), "invite_code": room["invite_code"]})
        host.api_mp_lock({})
        return host, guest, host_out, guest_out

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script as a fake emulator")
    def test_encrypted_match_uses_tunnel_and_keeps_key_out_of_snapshots(self):
        from adapters.retroarch import tunnel
        if not tunnel.available():
            self.skipTest("TLS-PSK needs Python 3.13+")
        host, guest, host_out, guest_out = self._ready_room()
        for app in (host, guest):
            app.catalog.set_setting("allow_direct_connections", True)
        result = host.api_mp_launch({"address": "127.0.0.1", "port": 55440, "relay": False, "expose_address": True})
        self.assertTrue(result["encrypted"])
        hargs = self.wait_args(host_out)
        self.assertEqual("55441", hargs[hargs.index("--port") + 1])  # RetroArch is on the private port
        endpoint = guest._call({"operation": "get_endpoint", **guest._auth()})["endpoint"]
        self.assertEqual(55440, endpoint["port"])
        self.assertEqual(64, len(endpoint["psk"]))
        result = guest.api_mp_launch({"expose_address": True})
        self.assertTrue(result["encrypted"])
        gargs = self.wait_args(guest_out)
        self.assertEqual("127.0.0.1", gargs[gargs.index("--connect") + 1])
        self.assertNotEqual("55440", gargs[gargs.index("--port") + 1])  # local tunnel port
        self.assertNotIn(endpoint["psk"], json.dumps(self.server.service.export_state()))
        host.api_mp_leave({})
        guest.api_mp_leave({})

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script as a fake emulator")
    def test_direct_connection_needs_setting_and_confirmation_on_both_sides(self):
        from adapters.retroarch import tunnel
        if not tunnel.available():
            self.skipTest("TLS-PSK needs Python 3.13+")
        host, guest, host_out, guest_out = self._ready_room()
        with self.assertRaisesRegex(AppError, "Direct connections are off"):
            host.api_mp_launch({"relay": False, "address": "127.0.0.1"})
        host.catalog.set_setting("allow_direct_connections", True)
        with self.assertRaisesRegex(AppError, "Confirm"):
            host.api_mp_launch({"relay": False, "address": "127.0.0.1"})
        self.assertFalse(host_out.exists())
        host.api_mp_launch({"relay": False, "address": "127.0.0.1", "port": 55480, "expose_address": True})
        self.wait_args(host_out)
        self.assertEqual("direct", guest.api_mp_state({})["room"]["launch"]["endpoint_kind"])
        with self.assertRaisesRegex(AppError, "direct connection"):
            guest.api_mp_launch({})          # the guest is protected too
        self.assertFalse(guest_out.exists())
        guest.catalog.set_setting("allow_direct_connections", True)
        with self.assertRaisesRegex(AppError, "Confirm"):
            guest.api_mp_launch({})
        guest.api_mp_launch({"expose_address": True})
        self.wait_args(guest_out)
        host.api_mp_leave({}); guest.api_mp_leave({})

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script as a fake emulator")
    def test_relay_match_publishes_no_address(self):
        from adapters.retroarch import tunnel
        if not tunnel.available():
            self.skipTest("TLS-PSK needs Python 3.13+")
        host, guest, host_out, guest_out = self._ready_room()
        result = host.api_mp_launch({"relay": True, "port": 55460})
        self.assertTrue(result["relay"])
        hargs = self.wait_args(host_out)
        self.assertEqual("55460", hargs[hargs.index("--port") + 1])
        endpoint = guest._call({"operation": "get_endpoint", **guest._auth()})["endpoint"]
        self.assertEqual("relay", endpoint["kind"])
        self.assertNotIn("port", endpoint)
        result = guest.api_mp_launch({})
        self.assertTrue(result["relay"])
        gargs = self.wait_args(guest_out)
        self.assertEqual("127.0.0.1", gargs[gargs.index("--connect") + 1])  # the local tunnel, never the host
        host.api_mp_leave({})
        guest.api_mp_leave({})

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script as a fake emulator")
    def test_encryption_never_silently_downgrades(self):
        from unittest import mock
        host, guest, host_out, guest_out = self._ready_room()
        host.catalog.set_setting("allow_direct_connections", True)
        with mock.patch("adapters.retroarch.tunnel.available", return_value=False):
            with self.assertRaisesRegex(AppError, "Encrypt match traffic"):
                host.api_mp_launch({"address": "127.0.0.1", "relay": False, "expose_address": True})
        self.assertFalse(host_out.exists())

    def gc_game(self, name):
        root = Path(self.tmp.name) / name / "Games"
        touch(root / "Gamecube" / "Mario Party 4 (USA).ciso")
        self.apps[name].rescan()
        return next(g for g in self.apps[name].api_library({"console": "gamecube"})["games"])["id"]

    def fake_dolphin(self, name):
        exe = Path(self.tmp.name) / name / "Dolphin"
        out = Path(self.tmp.name) / name / "dolphin_args.txt"
        exe.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{out}"\n')
        exe.chmod(0o755)
        self.apps[name].api_emulators({"emulator": "dolphin", "path": str(exe)})
        return out

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script as a fake emulator")
    def _allow_direct(self, *apps):
        for app in apps:
            app.catalog.set_setting("allow_direct_connections", True)

    def test_dolphin_needs_direct_consent(self):
        host, guest = self.apps["Host"], self.apps["Guest"]
        self.fake_dolphin("Host")
        room = host.api_mp_host({"id": self.gc_game("Host"), "require_approval": False})["room"]
        guest.api_mp_join({"id": self.gc_game("Guest"), "invite_code": room["invite_code"]})
        host.api_mp_lock({})
        with self.assertRaisesRegex(AppError, "cannot use the relay"):
            host.api_mp_launch({"mode": "traversal"})
        self._allow_direct(host)
        with self.assertRaisesRegex(AppError, "Confirm"):
            host.api_mp_launch({"mode": "traversal"})

    def test_dolphin_traversal_guided_flow(self):
        host, guest = self.apps["Host"], self.apps["Guest"]
        h_out, g_out = self.fake_dolphin("Host"), self.fake_dolphin("Guest")
        room = host.api_mp_host({"id": self.gc_game("Host"), "require_approval": False})["room"]
        guest.api_mp_join({"id": self.gc_game("Guest"), "invite_code": room["invite_code"]})
        host.api_mp_lock({})
        self.assertEqual("dolphin", host.api_mp_state({})["room"]["launch"]["engine"])
        self._allow_direct(host, guest)
        result = host.api_mp_launch({"mode": "traversal", "expose_address": True})
        self.assertTrue(result["needs_code"])
        self.assertTrue(any("host code" in step for step in result["steps"]))
        args = self.wait_args(h_out)
        self.assertEqual("-e", args[0])
        self.assertNotIn("-b", args)
        with self.assertRaisesRegex(AppError, "not shared"):
            guest.api_mp_launch({"expose_address": True})
        host.api_mp_share_code({"code": "ZX81QR55"})
        guest_result = guest.api_mp_launch({"expose_address": True})
        self.assertTrue(any("ZX81QR55" in step for step in guest_result["steps"]))
        self.wait_args(g_out)

    @unittest.skipIf(sys.platform == "win32", "uses a POSIX shell script as a fake emulator")
    def test_dolphin_direct_publishes_address(self):
        host, guest = self.apps["Host"], self.apps["Guest"]
        self.fake_dolphin("Host"); self.fake_dolphin("Guest")
        room = host.api_mp_host({"id": self.gc_game("Host"), "require_approval": False})["room"]
        guest.api_mp_join({"id": self.gc_game("Guest"), "invite_code": room["invite_code"]})
        host.api_mp_lock({})
        self._allow_direct(host, guest)
        host.api_mp_launch({"mode": "direct", "address": "192.168.1.9", "port": 2626, "expose_address": True})
        steps = guest.api_mp_launch({"expose_address": True})["steps"]
        self.assertTrue(any("192.168.1.9" in s and "2626" in s for s in steps))

    def test_launch_explains_missing_retroarch_and_core(self):
        host = self.apps["Host"]
        host.api_mp_host({"id": self.gid(host), "require_approval": False})
        with self.assertRaisesRegex(AppError, "RetroArch is not set up"):
            host.api_mp_launch({})

    def test_unreachable_server_gives_helpful_message(self):
        host = self.apps["Host"]
        host.catalog.set_setting("server_port", 1)
        with self.assertRaisesRegex(AppError, "Is it running"):
            host.api_mp_host({"id": self.gid(host)})


if __name__ == "__main__":
    unittest.main()


class CatalogRobustnessTests(unittest.TestCase):
    def test_damaged_settings_files_are_set_aside_not_fatal(self):
        import tempfile
        from pathlib import Path
        from launcher.catalog import Catalog
        for bad in (b"[1, 2]", b"\xff\xfe\x00bad", b"{not json", b'{"roots": "C:", "favorites": 5}'):
            d = Path(tempfile.mkdtemp())
            (d / "user_data.json").write_bytes(bad)
            c = Catalog(d)
            self.assertIsInstance(c.data["roots"], list)
            self.assertIsInstance(c.data["favorites"], list)
