import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import firewall
from launcher.app import LauncherApp


class RouterTidyTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict("os.environ", {"LEGACY_PLAYER_NO_BACKGROUND": "1"})
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = LauncherApp(Path(self.tmp.name) / "data", roots=[])

    def test_mapping_is_recorded_closed_and_forgotten(self):
        mapped = {"state": "mapped", "port": 8765, "location": "http://192.168.1.1:5000/x", "external_ip": "93.184.216.34", "kind": "public", "message": "ok"}
        with mock.patch("launcher.portmap.open_port", return_value=mapped), mock.patch("launcher.portmap.close_port", return_value=True) as close:
            self.app._manage_router("start", 0, True, 8765)
            self.assertEqual(8765, self.app.catalog.data["router_mapped"]["port"])
            self.app._manage_router("stop", 0, True, 8765)
            close.assert_called_with(8765, "http://192.168.1.1:5000/x")
        self.assertEqual({}, self.app.catalog.data["router_mapped"])

    def test_a_mapping_left_by_a_crash_is_closed_on_next_start_and_on_uninstall(self):
        self.app.catalog.data["router_mapped"] = {"port": 8765, "location": "http://192.168.1.1:5000/x"}
        with mock.patch("launcher.portmap.close_port", return_value=True) as close:
            self.app._close_router_mapping()
            close.assert_called_once_with(8765, "http://192.168.1.1:5000/x")
        self.assertEqual({}, self.app.catalog.data["router_mapped"])


class FirewallRemoveTests(unittest.TestCase):
    def test_remove_is_a_noop_off_windows(self):
        if firewall.supported():
            self.skipTest("windows")
        self.assertEqual({"removed": True}, firewall.remove())
        self.assertFalse(firewall.exists())

    def test_remove_asks_for_approval_only_when_the_plain_delete_fails(self):
        calls = []

        class R:
            def __init__(self, rc, out=""):
                self.returncode, self.stdout = rc, out

        state = {"there": True}

        def run(args, timeout=15.0):
            calls.append(args[0])
            if args[0] == "netsh" and "show" in args:
                return R(0 if state["there"] else 1, firewall.RULE if state["there"] else "")
            if args[0] == "netsh" and "delete" in args:
                return R(1)                      # not an administrator
            state["there"] = False               # the elevated run worked
            return R(0)
        with mock.patch("launcher.firewall.supported", return_value=True):
            self.assertEqual({"removed": True}, firewall.remove(run))
        self.assertIn("powershell", calls)


if __name__ == "__main__":
    unittest.main()


class SharedSaveTests(unittest.TestCase):
    def test_two_games_with_one_file_name_never_lose_each_others_saves_or_files(self):
        from tests.test_app_actions import make_app
        app, base = make_app()
        folder = base / "games" / "NES"
        (folder / "Twin.nes").write_bytes(b"NES\x1a" + b"1" * 64)
        (folder / "Twin.sfc").write_bytes(b"2" * 1024 * 33)
        (folder / "Twin.srm").write_bytes(b"save")
        (folder / "Twin.cue").write_text('FILE "Test Game (USA).nes" BINARY\n')       # points at another game's file
        app.rescan()
        nes = next(g for g in app.games.values() if g["path"].endswith("Twin.nes"))
        plan = app.api_game_uninstall({"id": nes["id"]})
        self.assertTrue(plan["saves_shared"])
        self.assertEqual([], plan["saves"])
        names = [f["name"] for f in plan["files"]]
        self.assertNotIn("Test Game (USA).nes", names)


class RestoreSafetyTests(unittest.TestCase):
    def test_a_damaged_backup_restores_nothing_and_says_so(self):
        import zipfile
        from launcher import saves
        base = Path(tempfile.mkdtemp())
        dest, folder = base / "b", base / "s"
        dest.mkdir(); folder.mkdir()
        (folder / "a.srm").write_bytes(b"keep me")
        bad = dest / "LegacyPlayer-saves-x.zip"
        bad.write_bytes(b"not a zip at all")
        with self.assertRaises(ValueError):
            saves.restore_all(dest, bad.name, {"nes": folder}, base / "safety")
        nomanifest = dest / "LegacyPlayer-saves-y.zip"
        with zipfile.ZipFile(nomanifest, "w") as z:
            z.writestr("nes/a.srm", b"x")
        with self.assertRaises(ValueError):
            saves.restore_all(dest, nomanifest.name, {"nes": folder}, base / "safety")
        self.assertEqual(b"keep me", (folder / "a.srm").read_bytes())


class Round3Tests(unittest.TestCase):
    def test_router_lease_is_timed_and_falls_back(self):
        from launcher import portmap
        calls = []

        class GW:
            def __init__(self, *a, **k): pass
            def add(self, port, ip, lease=0):
                calls.append(lease)
                if lease:
                    raise portmap.PortMapError("code 725")
            def external_ip(self): return "8.8.8.8"
            def delete(self, port): pass
        with mock.patch.object(portmap, "Gateway", GW):
            out = portmap.open_port(8765, locations=["http://192.168.1.1:80/x"], local_ip="192.168.1.5")
        self.assertEqual("mapped", out["state"])
        self.assertEqual([portmap.LEASE_SECONDS, 0], calls)
        self.assertLess(portmap.RENEW_SECONDS, portmap.LEASE_SECONDS)

    def test_firewall_rule_names_the_program_when_given(self):
        from launcher import firewall
        self.assertIn("program=C:\\x\\LegacyPlayer.exe", firewall.rule_args(8765, "C:\\x\\LegacyPlayer.exe"))
        self.assertFalse(any(a.startswith("program=") for a in firewall.rule_args(8765)))


class Round4Tests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict("os.environ", {"LEGACY_PLAYER_NO_BACKGROUND": "1"})
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = LauncherApp(Path(self.tmp.name) / "data", roots=[])

    def test_firewall_approval_runs_a_script_file_and_reports_netsh_words(self):
        import tempfile
        from pathlib import Path as P
        seen = {}

        def run(cmd, timeout=0):
            seen["cmd"] = cmd
            folder = P(tempfile.gettempdir())
            seen["script"] = (folder / "lp-firewall.cmd").read_text(encoding="ascii")
            (folder / "lp-firewall.log").write_text("The requested operation requires elevation.\nLP_EXIT=1\n", encoding="utf-8")
            return mock.Mock(stderr="")
        out = firewall._elevated(firewall.rule_args(8765, "C:\\Program Files\\LP\\LegacyPlayer.exe"), run)
        self.assertIn("RunAs", seen["cmd"][-1])
        self.assertIn('"name=Legacy Player server"', seen["script"])
        self.assertIn('"program=C:\\Program Files\\LP\\LegacyPlayer.exe"', seen["script"])
        self.assertEqual(out["log"], "The requested operation requires elevation.")
        self.assertFalse(out["cancelled"])
        self.assertFalse(out["ok"])

    def test_firewall_cancel_is_told_apart_and_a_manual_command_is_given(self):
        def run(cmd, timeout=15.0):
            if cmd[0] == "powershell":
                return mock.Mock(stderr="The operation was canceled by the user.")
            return mock.Mock(returncode=1, stdout="")
        with mock.patch("launcher.firewall.supported", return_value=True):
            r = firewall.allow(8765, run)
        self.assertFalse(r["allowed"])
        self.assertIn("closed or refused", r["message"])
        self.assertIn("localport=8765", r["manual"])
        self.assertIn("profile=any", r["manual"])

    def test_hosting_starts_a_stopped_own_server_once(self):
        from launcher.lobby_client import LobbyClientError
        refused = LobbyClientError("refused")
        refused.__cause__ = ConnectionRefusedError()
        calls = []

        class C:
            def call(self_, request):
                calls.append(request)
                if len(calls) == 1:
                    raise refused
                return {"ok": True}
        with mock.patch.object(self.app, "_client", return_value=C()), \
                mock.patch.object(self.app, "api_server_control", return_value={}) as ctl:
            self.assertEqual({"ok": True}, self.app._call({"operation": "browse"}))
            ctl.assert_called_once()
            self.assertEqual("start", ctl.call_args[0][0]["action"])

    def test_a_friends_server_is_never_started_by_us(self):
        from launcher.lobby_client import LobbyClientError
        self.app.catalog.set_setting("server_host", "203.0.113.5")
        refused = LobbyClientError("refused")
        refused.__cause__ = ConnectionRefusedError()
        self.assertFalse(self.app._own_server_refused(refused))

    def test_activity_is_offline_when_nothing_answers(self):
        self.assertEqual({"online": False}, self.app.api_server_activity({}))

    def test_auto_agree_only_when_switched_on_and_game_present(self):
        room = {"role": "guest", "me": "me", "game_id": "g1", "start": {"id": 3, "consented": ["host"]}, "session_id": "s", "credential": "c"}
        events = []
        self.app.room = room
        room["r"] = None
        room.update(session_id="s", me="me", credential="c")
        with mock.patch.object(self.app, "_call") as call:
            self.app._maybe_auto_agree(room, events)           # setting off
            call.assert_not_called()
            self.app.catalog.set_setting("mp_auto_agree", True)
            self.app._maybe_auto_agree(room, events)           # game missing
            call.assert_not_called()
            self.app.games["g1"] = {"id": "g1"}
            self.app._maybe_auto_agree(room, events)
            self.assertEqual("consent_start", call.call_args[0][0]["operation"])

    def test_firewall_allow_does_nothing_when_the_rule_is_there_and_replaces_a_stale_one(self):
        calls = []

        def run(args, timeout=15.0):
            calls.append(args)
            out = mock.Mock(returncode=0, stdout="Rule Name: Legacy Player server\nLocalPort: 8765\n")
            return out
        with mock.patch("launcher.firewall.supported", return_value=True):
            self.assertTrue(firewall.allow(8765, run)["allowed"])
            self.assertFalse(any("add" in c for c in calls))
            calls.clear()

            def stale(args, timeout=15.0):
                calls.append(args)
                return mock.Mock(returncode=0, stdout="Rule Name: Legacy Player server\nLocalPort: 9999\n")
            firewall.allow(8765, stale)
            self.assertTrue(any("delete" in c for c in calls))
            self.assertTrue(any("add" in c for c in calls))

    def test_focus_titled_is_false_without_a_window(self):
        from launcher import winplace
        with mock.patch.object(winplace, "_titled", return_value=[]):
            self.assertFalse(winplace.focus_titled("Legacy Player —"))


class QuitFarewellTests(unittest.TestCase):
    def test_ping_tells_an_open_window_that_the_app_is_quitting(self):
        import os
        with mock.patch.dict(os.environ, {"LEGACY_PLAYER_NO_BACKGROUND": "1"}), tempfile.TemporaryDirectory() as tmp:
            app = LauncherApp(Path(tmp) / "data", roots=[])
            self.assertFalse(app.api_ping({})["quitting"])
            app.api_quit({})
            self.assertTrue(app.api_ping({})["quitting"])
            self.assertGreater(app.quit_at, 0)


class GameOverlayTests(unittest.TestCase):
    def setUp(self):
        import os
        p = mock.patch.dict(os.environ, {"LEGACY_PLAYER_NO_BACKGROUND": "1"})
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = LauncherApp(Path(self.tmp.name) / "data", roots=[])

    def test_overlay_does_not_open_without_a_game(self):
        from launcher.app import AppError
        with self.assertRaises(AppError):
            self.app.api_overlay_open({})

    def test_overlay_view_names_the_game_and_the_room(self):
        self.assertIsNone(self.app._overlay_view()["game"])
        self.app.running = {"pid": 1, "title": "Bomberman II", "emulator": "RetroArch", "emulator_id": "retroarch", "started": None, "since": 100.0}
        with mock.patch("launcher.procs.is_alive", return_value=True):
            view = self.app._overlay_view()
        self.assertEqual(("Bomberman II", 100.0), (view["game"]["title"], view["game"]["since"]))

    def test_tray_offers_the_overlay_only_while_a_game_runs(self):
        import time
        from launcher.tray import TrayController
        tray = TrayController(self.app, lambda: None)
        tray._state = {"running": False, "players": 0, "live": 0, "open_rooms": 0, "cert": False, "known": True, "shared": False}
        self.assertFalse(any(i and i[0] == "overlay" for i in tray.menu()))
        self.app.running = {"pid": 1, "title": "Bomberman II", "emulator": "RetroArch", "emulator_id": "retroarch", "started": None, "since": time.time() - 1500}
        with mock.patch("launcher.procs.is_alive", return_value=True):
            labels = [i[1] for i in tray.menu() if i]
        self.assertTrue(any(l.startswith("Playing Bomberman II  ·  25 min") for l in labels), labels)
        self.assertIn("Open game overlay", labels)
        self.assertLess([l.startswith("Playing") for l in labels].index(True), labels.index("Open game overlay"))

    def test_app_steps_aside_for_a_game_and_returns_when_it_ends(self):
        from launcher import winplace
        alive = iter([True, True, False])
        with mock.patch("time.sleep"), mock.patch("launcher.procs.is_alive", side_effect=lambda *a: next(alive)), \
                mock.patch.object(winplace, "minimize_titled", return_value=True) as mini, \
                mock.patch.object(winplace, "restore_titled") as back:
            self.app._step_aside_for(7, None)
        mini.assert_called_once()
        back.assert_called_once()

    def test_it_does_not_pop_the_window_back_if_it_never_stepped_aside(self):
        from launcher import winplace
        with mock.patch("time.sleep"), mock.patch("launcher.procs.is_alive", return_value=False), \
                mock.patch.object(winplace, "minimize_titled", return_value=False), mock.patch.object(winplace, "restore_titled") as back:
            self.app._step_aside_for(7, None)
        back.assert_not_called()

    def test_session_length_reads_naturally(self):
        from launcher.overlay_window import duration
        self.assertEqual("under a minute", duration(20))
        self.assertEqual("25 min", duration(1500))
        self.assertEqual("1 h 05 min", duration(3900))


class FirewallProgramMatchTests(unittest.TestCase):
    def test_a_rule_added_by_hand_for_any_program_counts_and_another_program_does_not(self):
        exe = "C:\\Users\\a\\AppData\\Local\\Programs\\LegacyPlayer\\LegacyPlayer.exe"
        base = "Rule Name: Legacy Player server\nLocalPort: 8765\n"
        self.assertTrue(firewall._program_matches(exe, base + "Action: Allow\nOk.\n"))      # real netsh output of a hand-made rule: no Program line
        self.assertTrue(firewall._program_matches(exe, base + "Program: Any\n"))
        self.assertTrue(firewall._program_matches(exe, base + "Program:   Alle\n"))
        self.assertTrue(firewall._program_matches(exe, base + "Program: c:\\users\\A\\appdata\\local\\programs\\legacyplayer\\LEGACYPLAYER.EXE\n"))
        self.assertFalse(firewall._program_matches(exe, base + "Program: C:\\Other\\thing.exe\n"))


class FirewallTrustsNetshTests(unittest.TestCase):
    def test_exit_code_zero_counts_as_added_even_if_reading_the_rule_back_disagrees(self):
        import tempfile
        from pathlib import Path as P

        def run(cmd, timeout=15.0):
            if cmd[0] == "powershell":
                (P(tempfile.gettempdir()) / "lp-firewall.log").write_text("Ok.\nLP_EXIT=0\n", encoding="utf-8")
                return mock.Mock(stderr="")
            return mock.Mock(returncode=1, stdout="")          # reading the rule never matches
        with mock.patch("launcher.firewall.supported", return_value=True):
            r = firewall.allow(8765, run)
        self.assertTrue(r["allowed"])

    def test_one_approval_replaces_an_old_rule_and_adds_the_new_one(self):
        import tempfile
        from pathlib import Path as P
        seen = {}

        def run(cmd, timeout=15.0):
            if cmd[0] == "powershell":
                seen["script"] = (P(tempfile.gettempdir()) / "lp-firewall.cmd").read_text(encoding="ascii")
                (P(tempfile.gettempdir()) / "lp-firewall.log").write_text("LP_EXIT=0\n", encoding="utf-8")
                return mock.Mock(stderr="")
            if "show" in cmd:
                return mock.Mock(returncode=0, stdout="Rule Name: Legacy Player server\nLocalPort: 1111\n")        # stale rule
            return mock.Mock(returncode=1, stdout="")          # delete and add both need administrator
        with mock.patch("launcher.firewall.supported", return_value=True):
            firewall.allow(8765, run)
        self.assertLess(seen["script"].index("delete rule"), seen["script"].index("add rule"))
        self.assertEqual(seen["script"].count("netsh"), 2)
