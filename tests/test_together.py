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
