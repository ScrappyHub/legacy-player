"""Network services hardening: friendships need a real request, half-made rooms, shutdown with open connections, slow and
odd clients, no addresses in logs, hello limits, safe saving, admin keys only in a header, unusable snapshots."""
import asyncio
import contextlib
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from server import selfsigned
from server.api import json_server
from server.http_guard import AddressWindow, BoundedHTTPServer
from server.lobby import LobbyError, LobbyService
from server.social import MAX_FRIENDS, SocialError, SocialService
from server.social.__main__ import FriendsHTTPServer, make_handler
from server.state_store import SNAPSHOT_NAME, StateStore

PROFILE = {"game_id": "GMPE01", "region": "USA"}


def create_request(**extra):
    return {"operation": "create", "participant_id": "host", "profile": PROFILE, "adapter_id": "dolphin",
            "game_pack_id": "mario_party_4", **extra}


class Clock:
    def __init__(self, t=3_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


# --- 1. a friendship needs a request that is really there --------------------------------------------------------
class DecideNeedsARequest(unittest.TestCase):
    def setUp(self):
        self.s = SocialService(None, Clock())
        self.a, self.b, self.c = self.s.hello("Alec"), self.s.hello("Bea"), self.s.hello("Cal")

    def test_accepting_someone_who_never_asked_does_nothing(self):
        with self.assertRaises(SocialError):
            self.s.decide(self.a["id"], self.a["secret"], self.b["id"], True)
        self.assertEqual([], self.s.players[self.a["id"]]["friends"])
        self.assertEqual([], self.s.players[self.b["id"]]["friends"])
        with self.assertRaises(SocialError):                       # and so no message can be forced on them
            self.s.message(self.a["id"], self.a["secret"], self.b["id"], "hi")

    def test_a_block_either_way_refuses_the_request(self):
        self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        self.s.players[self.a["id"]]["blocked"].append(self.b["id"])    # Alec blocked Bea after asking
        with self.assertRaises(SocialError):
            self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)
        self.assertEqual([], self.s.players[self.b["id"]]["friends"])
        self.assertEqual([], self.s.players[self.b["id"]]["requests_in"])   # the request is gone either way

    def test_the_other_sides_full_list_is_checked_too(self):
        self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        self.s.players[self.a["id"]]["friends"] = [f"x{i}" for i in range(MAX_FRIENDS)]
        with self.assertRaises(SocialError) as ctx:
            self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)
        self.assertIn("full", str(ctx.exception))
        self.assertEqual([self.a["id"]], self.s.players[self.b["id"]]["requests_in"])   # still there to accept later

    def test_a_real_request_still_works_and_declining_is_quiet(self):
        self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        inbox = self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)
        self.assertEqual(["Alec"], [f["name"] for f in inbox["friends"]])
        self.s.request(self.c["id"], self.c["secret"], self.b["code"])
        self.s.decide(self.b["id"], self.b["secret"], self.c["id"], False)
        self.assertNotIn(self.c["id"], self.s.players[self.b["id"]]["friends"])


# --- 5. free text is filtered, bans clear both sides, friendship needs both sides -------------------------------
class FiltersMutesAndBans(unittest.TestCase):
    def setUp(self):
        self.s = SocialService(None, Clock())
        self.a, self.b = self.s.hello("Alec"), self.s.hello("Bea")
        self.s.request(self.a["id"], self.a["secret"], self.b["code"])
        self.s.decide(self.b["id"], self.b["secret"], self.a["id"], True)
        self.s.admin_filter(on=True, words="zorp")

    def test_status_room_game_and_invite_game_go_through_the_filter(self):
        room = {"invite_code": "ABCDE-FGH12", "game": "zorp party", "server_code": "LP-X", "players": "lots", "max_players": 1e999}
        self.s.heartbeat(self.a["id"], self.a["secret"], status="you zorp", room=room)
        friend = self.s.heartbeat(self.b["id"], self.b["secret"])["friends"][0]
        self.assertEqual("", friend["status"])
        self.assertEqual("", friend["room"]["game"])
        self.assertEqual((0, 0), (friend["room"]["players"], friend["room"]["max_players"]))     # odd numbers do not crash
        self.s.invite(self.a["id"], self.a["secret"], self.b["id"], "ABCDE-FGH12", "z0rp night", "LP-X")
        self.assertEqual("", self.s.heartbeat(self.b["id"], self.b["secret"])["invites"][0]["game"])

    def test_a_timed_out_player_shares_no_status(self):
        self.s.admin_act("timeout", player=self.a["id"], length="1h")
        self.s.heartbeat(self.a["id"], self.a["secret"], status="come play",
                         room={"invite_code": "ABCDE-FGH12", "game": "Mario Kart"})
        friend = self.s.heartbeat(self.b["id"], self.b["secret"])["friends"][0]
        self.assertEqual("", friend["status"])
        self.assertEqual("", friend["room"]["game"])

    def test_after_a_ban_and_unban_the_old_friendship_is_gone_for_both(self):
        self.s.admin_act("ban", player=self.b["id"])
        self.assertEqual([], self.s.players[self.b["id"]]["friends"])          # their own list is cleared too
        self.s.admin_act("unban", player=self.b["id"])
        with self.assertRaises(SocialError):
            self.s.message(self.b["id"], self.b["secret"], self.a["id"], "I'm back")
        with self.assertRaises(SocialError):
            self.s.invite(self.b["id"], self.b["secret"], self.a["id"], "ABCDE-FGH12", "x")

    def test_a_one_sided_friend_entry_lets_nothing_through(self):
        self.s.players[self.a["id"]]["friends"].remove(self.b["id"])           # e.g. left over from an older version
        with self.assertRaises(SocialError):
            self.s.message(self.b["id"], self.b["secret"], self.a["id"], "hi")
        with self.assertRaises(SocialError):
            self.s.invite(self.b["id"], self.b["secret"], self.a["id"], "ABCDE-FGH12", "x")
        self.assertEqual([], self.s.heartbeat(self.b["id"], self.b["secret"])["friends"])   # nor shows their presence


# --- 6. no client address in any log -----------------------------------------------------------------------------
class NoAddressInLogs(unittest.TestCase):
    def _error_output(self, server_class):
        httpd = server_class(("127.0.0.1", 0), make_handler(SocialService(None)))
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                try:
                    raise ConnectionResetError("peer 203.0.113.9 went away")
                except ConnectionResetError:
                    httpd.handle_error(None, ("203.0.113.9", 51515))
            return err.getvalue()
        finally:
            httpd.server_close()

    def test_friends_service_and_report_receiver_log_only_the_kind_of_error(self):
        from server.report_receiver import ReceiverHTTPServer
        for cls in (FriendsHTTPServer, ReceiverHTTPServer):
            text = self._error_output(cls)
            self.assertIn("ConnectionResetError", text)
            self.assertNotIn("203.0.113", text)
            self.assertNotIn("51515", text)
            self.assertNotIn("Traceback", text)

    def test_a_broken_request_over_the_wire_leaves_no_address(self):
        httpd = FriendsHTTPServer(("127.0.0.1", 0), make_handler(SocialService(None)))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), mock.patch("server.social.__main__.dispatch", side_effect=RuntimeError):
                s = socket.create_connection(httpd.server_address, timeout=5)
                s.sendall(b'POST / HTTP/1.1\r\nContent-Length: 13\r\n\r\n{"op":"read"}')
                s.recv(1000)
                s.close()
                s = socket.create_connection(httpd.server_address, timeout=5)
                s.sendall(b"POST / HTTP/1.1\r\nContent-Length: 5\r\n\r\n")
                s.shutdown(socket.SHUT_WR)              # the body never arrives
                s.recv(100)
                s.close()
                time.sleep(0.2)
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertNotIn("127.0.0.1", err.getvalue())


# --- 7. hello limits, a player cap and gathered saves --------------------------------------------------------------
class HelloLimitsAndSaving(unittest.TestCase):
    def test_address_window_counts_an_ipv6_household_once_and_never_this_computer(self):
        w = AddressWindow(3, 3600, clock=Clock(0))
        self.assertTrue(all(w.allow("2001:db8:1:2::%d" % i) for i in range(1, 4)))
        self.assertFalse(w.allow("2001:db8:1:2:ffff::1"))             # same /64
        self.assertTrue(w.allow("2001:db8:1:3::1"))                   # another household
        self.assertTrue(all(w.allow("127.0.0.1") for _ in range(50)))
        self.assertTrue(all(w.allow("203.0.113.5") for _ in range(3)))
        self.assertFalse(w.allow("203.0.113.5"))

    def test_hello_over_http_is_limited_per_address(self):
        service = SocialService(None)
        httpd = FriendsHTTPServer(("127.0.0.1", 0), make_handler(service, hello_limit=AddressWindow(2, 3600)))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{httpd.server_address[1]}/"

        def hello():
            req = urllib.request.Request(url, data=json.dumps({"op": "hello", "name": "x"}).encode(), method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status
            except urllib.error.HTTPError as err:
                return err.code
        try:
            with mock.patch("server.http_guard.key_for", return_value="198.51.100.7"):   # as if from another computer
                self.assertEqual([200, 200, 429], [hello(), hello(), hello()])
            self.assertEqual(2, len(service.players))
            self.assertEqual(200, hello())                                                # this computer is not limited
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_the_service_has_a_player_cap(self):
        s = SocialService(None, Clock())
        with mock.patch("server.social.MAX_PLAYERS", 3):
            for name in ("a", "b", "c"):
                s.hello(name)
            with self.assertRaises(SocialError):
                s.hello("d")

    def test_ordinary_changes_are_gathered_into_few_saves_and_flush_writes_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            s = SocialService(Path(d), Clock())
            a = s.hello("A")
            writes = []
            real = s.save
            s.save = lambda: (writes.append(1), real())[1]
            for i in range(30):
                s.heartbeat(a["id"], a["secret"], name=f"N{i}", status=f"s{i}")
                s.hello(f"P{i}")
            self.assertLessEqual(len(writes), 1)                    # 60 changes inside the 2 s window: no write per change
            s.heartbeat(a["id"], a["secret"], name="Renamed")
            s.flush()
            self.assertIsNone(s._timer)
            self.assertEqual("Renamed", SocialService(Path(d), Clock()).players[a["id"]]["name"])

    def test_bans_are_written_at_once(self):
        with tempfile.TemporaryDirectory() as d:
            s = SocialService(Path(d), Clock())
            a = s.hello("A")
            b = s.hello("B")
            s.admin_act("ban", player=b["id"])
            self.assertIn(b["id"], SocialService(Path(d), Clock()).mod["bans"])
            self.assertTrue(a["id"])


# --- 9. safe saving and a damaged players.json -------------------------------------------------------------------
class PlayersFile(unittest.TestCase):
    def test_saves_are_flushed_to_disk_and_leave_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("server.social.os.fsync", wraps=os.fsync) as fsync:
            s = SocialService(Path(d), Clock())
            s.hello("A")
            s.save()
            self.assertTrue(fsync.called)
            self.assertEqual(["players.json"], sorted(p.name for p in Path(d).iterdir()))

    def test_a_corrupt_file_is_kept_aside_logged_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "players.json").write_bytes(b'{"players": {"x": ')
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                s = SocialService(Path(d), Clock())
            self.assertEqual({}, s.players)
            kept = [p.name for p in Path(d).iterdir() if p.name.startswith("players.json.corrupt-")]
            self.assertEqual(1, len(kept))
            self.assertEqual(b'{"players": {"x": ', (Path(d) / kept[0]).read_bytes())
            self.assertIn("could not be read", err.getvalue())
            s.hello("New")
            s.save()
            self.assertTrue((Path(d) / kept[0]).exists())

    def test_bad_entries_are_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            good = SocialService(Path(d), Clock())
            a = good.hello("A")
            good.admin_act("ban", player=a["id"])
            data = json.loads((Path(d) / "players.json").read_text())
            data["players"]["broken"] = "not a player"
            data["players"]["nocode"] = {"name": "x"}
            data["players"][a["id"]]["friends"] = "not a list"
            data["mod"]["reports"] = [{"weird": True}]
            (Path(d) / "players.json").write_text(json.dumps(data))
            with contextlib.redirect_stderr(io.StringIO()):
                s = SocialService(Path(d), Clock())
            self.assertEqual([a["id"]], list(s.players))
            self.assertEqual([], s.players[a["id"]]["friends"])
            self.assertIn(a["id"], s.mod["bans"])
            self.assertEqual([], s.mod["reports"])
            s.admin_reports()                                         # and everything still works


# --- 13. the admin key only in a header ------------------------------------------------------------------------
class AdminKeyOnlyInAHeader(unittest.TestCase):
    def test_friends_console_refuses_the_key_in_the_address(self):
        httpd = FriendsHTTPServer(("127.0.0.1", 0), make_handler(SocialService(None), "m0d-key"))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/admin", timeout=5) as r:            # the page loads and asks for the key
                page = r.read()
            self.assertNotIn(b"token=", page)
            self.assertIn(b"X-Admin-Token", page)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(base + "/admin/reports?token=m0d-key", timeout=5)
            self.assertEqual(401, ctx.exception.code)
            req = urllib.request.Request(base + "/admin/reports", headers={"X-Admin-Token": "m0d-key"})
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(200, r.status)
        finally:
            httpd.shutdown()
            httpd.server_close()


# --- 8. bounded concurrency and a total deadline -------------------------------------------------------------------
class BoundedHTTP(unittest.TestCase):
    def test_a_trickling_sender_is_cut_off_and_extra_connections_are_closed(self):
        class Small(FriendsHTTPServer):
            max_concurrent = 1
            request_deadline = 0.6
        httpd = Small(("127.0.0.1", 0), make_handler(SocialService(None)))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        quiet = contextlib.redirect_stderr(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        try:
            slow = socket.create_connection(httpd.server_address, timeout=5)
            slow.sendall(b"POST / HTTP/1.1\r\n")                    # and then nothing for a long time
            time.sleep(0.2)
            extra = socket.create_connection(httpd.server_address, timeout=5)
            self.assertEqual(b"", extra.recv(100))                  # over the cap: closed at once
            extra.close()
            start = time.monotonic()
            slow.recv(100)                                          # the deadline ends the slow one
            self.assertLess(time.monotonic() - start, 4)
            slow.close()
            time.sleep(0.2)
            with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/health", timeout=5) as r:
                self.assertEqual(200, r.status)                     # and the slot is free again
        finally:
            httpd.shutdown()
            httpd.server_close()


# --- 2, 10, 16, 17: the lobby ------------------------------------------------------------------------------------
class LobbyRooms(unittest.TestCase):
    def test_a_refused_create_leaves_nothing_behind(self):
        s = LobbyService(max_sessions=1)
        for bad in ({"max_players": 99}, {"max_players": "4"}, {"label": "<script>"}):
            with self.assertRaises(LobbyError):
                s.create_session(create_request(**bad))
        self.assertEqual({}, s.sessions)
        self.assertEqual({}, s.credentials)
        s.create_session(create_request())                          # the only slot is still free
        s.announce_stopping()

    def test_half_made_sessions_from_an_old_snapshot_do_not_break_anything(self):
        s = LobbyService()
        s.create_session(create_request())
        state = s.export_state()
        orphan = dict(next(iter(state["sessions"].values())), session_id="orphan")
        state["sessions"]["orphan"] = orphan
        fresh = LobbyService()
        fresh.import_state(state)
        self.assertNotIn("orphan", fresh.sessions)
        fresh.sessions["orphan2"] = fresh.sessions[next(iter(fresh.sessions))].__class__.from_dict(dict(orphan, session_id="orphan2"))
        fresh.announce_stopping()                                   # tolerant of a session without events
        fresh.sweep_disconnected()
        fresh.expire_idle_sessions()                                # no activity stamp: it goes
        self.assertNotIn("orphan2", fresh.sessions)

    def test_a_restart_gives_launched_players_their_grace_again(self):
        clock = Clock(1_000_000.0)
        s = LobbyService(clock=clock)
        made = s.create_session(create_request(max_players=2))
        sid = made["session"]["session_id"]
        s.options[sid]["endpoint_at"] = clock.t
        s.options[sid]["start"] = {"id": 1, "title": "", "at": clock.t, "consented": ["host"]}
        s.established.add((sid, "host"))
        state = json.loads(json.dumps(s.export_state()))
        after_reboot = Clock(50.0)                                  # monotonic time starts again near zero
        again = LobbyService(clock=after_reboot)
        again.import_state(state)
        self.assertEqual(50.0, again.options[sid]["endpoint_at"])
        self.assertEqual(50.0, again.options[sid]["start"]["at"])
        self.assertIn((sid, "host"), again.established)
        self.assertEqual(50.0, again.joined_at[(sid, "host")])

    def test_evicted_sessions_are_forgotten_completely(self):
        clock = Clock(100.0)
        s = LobbyService(max_retained_sessions=1, session_idle_seconds=10, clock=clock)
        sids = []
        for _ in range(3):
            sids.append(s.create_session(create_request())["session"]["session_id"])
            clock.t += 1
        clock.t += 60
        s.expire_idle_sessions()                                    # all three end; only the newest is kept
        self.assertEqual(1, len(s.sessions))
        for old in sids[:2]:
            for table in (s.sessions, s.options, s.events, s.pending, s.last_activity):
                self.assertNotIn(old, table)
        snapshot = json.dumps(s.export_state())
        self.assertNotIn(sids[0], snapshot)

    def test_one_address_cannot_claim_every_name(self):
        s = LobbyService()
        s.aliases_per_address = 3
        for i in range(3):
            s.claim_alias({"alias": f"n{i}", "install_id": f"{i:04x}", "_peer": "203.0.113.5"})
        with self.assertRaises(LobbyError):
            s.claim_alias({"alias": "n9", "install_id": "abcd", "_peer": "203.0.113.5"})
        s.claim_alias({"alias": "n0", "install_id": "0000", "_peer": "203.0.113.5"})     # keeping your own name is fine
        s.claim_alias({"alias": "n9", "install_id": "abcd", "_peer": "198.51.100.1"})    # another address is fine
        s.claim_alias({"alias": "n8", "install_id": "abce", "_peer": "127.0.0.1"})       # this computer is not limited


# --- 14. a snapshot that parses but can't be used -----------------------------------------------------------------
class UnusableSnapshots(unittest.TestCase):
    def test_bytes_that_are_not_utf8_are_set_aside(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(Path(d))
            (Path(d) / SNAPSHOT_NAME).write_bytes(b"\xff\xfe{}")
            self.assertIsNone(store.load_snapshot())
            self.assertTrue((Path(d) / (SNAPSHOT_NAME + ".corrupt")).exists())

    def test_the_server_starts_empty_when_the_snapshot_is_from_elsewhere(self):
        for bad in ({"schema": "something.else"}, {"schema": "legacy_player.lobby_state.v1"}, [1, 2]):
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / SNAPSHOT_NAME).write_text(json.dumps(bad))
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    asyncio.run(_run_and_stop(Path(d)))
                self.assertTrue((Path(d) / (SNAPSHOT_NAME + ".corrupt")).exists())
                self.assertEqual("legacy_player.lobby_state.v1", json.loads((Path(d) / SNAPSHOT_NAME).read_text())["schema"])


async def _admin(state: Path, operation: str) -> dict:
    store = StateStore(state)
    info = store.read_info()
    reader, writer = await asyncio.open_connection("127.0.0.1", info["port"])
    writer.write(json.dumps({"operation": operation, "admin_token": store.admin_token()}).encode() + b"\n")
    await writer.drain()
    answer = json.loads(await reader.readline())
    writer.close()
    return answer


async def _wait_for_info(state: Path, task) -> None:
    for _ in range(200):
        if (state / "server_info.json").exists():
            return
        if task.done():
            task.result()
        await asyncio.sleep(0.02)
    raise AssertionError("server did not start")


async def _run_and_stop(state: Path, before_stop=None) -> float:
    task = asyncio.create_task(json_server.serve("127.0.0.1", 0, state / "replays", state_dir=state, autosave_seconds=3600))
    await _wait_for_info(state, task)
    extra = await before_stop() if before_stop else None
    await _admin(state, "admin_shutdown")
    start = time.monotonic()
    await asyncio.wait_for(task, 15)
    del extra
    return time.monotonic() - start


# --- 2, 3, 15: the running server ------------------------------------------------------------------------------
class RunningServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.quiet = contextlib.ExitStack()
        self.quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.err = io.StringIO()
        self.quiet.enter_context(contextlib.redirect_stderr(self.err))

    async def asyncTearDown(self):
        self.quiet.close()
        self.tmp.cleanup()

    async def test_stop_is_quick_with_parked_relay_and_idle_connections_and_saves_even_if_announcing_fails(self):
        held = []

        async def open_things():
            info = StateStore(self.state).read_info()
            r, w = await asyncio.open_connection("127.0.0.1", info["port"])
            w.write(json.dumps(create_request(access_key=StateStore(self.state).access_key())).encode() + b"\n")
            await w.drain()
            made = json.loads(await r.readline())["result"]
            w.close()
            pr, pw = await asyncio.open_connection("127.0.0.1", info["port"])        # a parked relay connection
            pw.write(json.dumps({"operation": "relay", "role": "host", "session_id": made["session"]["session_id"],
                                 "participant_id": "host", "credential": made["credential"]}).encode() + b"\n")
            await pw.drain()
            self.assertTrue(json.loads(await pr.readline())["result"]["parked"])
            ir, iw = await asyncio.open_connection("127.0.0.1", info["port"])        # and one that just sits there
            held.extend([(pr, pw), (ir, iw)])
            return held

        with mock.patch.object(LobbyService, "announce_stopping", side_effect=KeyError("half-made")):
            took = await _run_and_stop(self.state, open_things)
        self.assertLess(took, json_server.SHUTDOWN_WAIT_SECONDS + 2)
        snap = json.loads((self.state / SNAPSHOT_NAME).read_text())
        self.assertEqual(1, len(snap["sessions"]))                 # saved although announcing failed
        for _, w in held:
            w.close()

    async def test_odd_requests_get_a_plain_no_and_the_connection_survives(self):
        task = asyncio.create_task(json_server.serve("127.0.0.1", 0, self.state / "replays", state_dir=self.state,
                                                     autosave_seconds=3600))
        await _wait_for_info(self.state, task)
        port = StateStore(self.state).read_info()["port"]
        key = StateStore(self.state).access_key()
        r, w = await asyncio.open_connection("127.0.0.1", port)

        async def ask(raw: bytes) -> dict:
            w.write(raw + b"\n")
            await w.drain()
            return json.loads(await asyncio.wait_for(r.readline(), 5))
        made = await ask(json.dumps(create_request(access_key=key)).encode())
        self.assertTrue(made["ok"])
        res = await ask(json.dumps({"operation": "browse", "access_key": "ключ"}).encode())
        self.assertFalse(res["ok"])
        self.assertIn("server code", res["error"])
        res = await ask(json.dumps({"operation": "admin_status", "admin_token": "токен"}).encode())
        self.assertEqual({"ok": False, "error": "invalid admin token"}, res)
        res = await ask(b"[" * 50000 + b"]" * 50000)
        self.assertFalse(res["ok"])
        sid, cred = made["result"]["session"]["session_id"], made["result"]["credential"]
        res = await ask(b'{"operation":"input","session_id":"%s","participant_id":"host","credential":"%s","frame":0,"buttons":0,"stick_x":1e999}'
                        % (sid.encode(), cred.encode()))
        self.assertFalse(res["ok"])
        res = await ask(json.dumps({"operation": "join", "access_key": key, "invite_code": "\ud800", "participant_id": "p",
                                    "profile": PROFILE}).encode())
        self.assertFalse(res["ok"])
        self.assertTrue((await ask(json.dumps({"operation": "browse", "access_key": key}).encode()))["ok"])
        w.close()
        await _admin(self.state, "admin_shutdown")
        await asyncio.wait_for(task, 15)
        self.assertNotIn("127.0.0.1", self.err.getvalue())

    async def test_failing_in_a_row_or_lingering_closes_the_connection(self):
        task = asyncio.create_task(json_server.serve("127.0.0.1", 0, self.state / "replays", state_dir=self.state,
                                                     autosave_seconds=3600))
        await _wait_for_info(self.state, task)
        port = StateStore(self.state).read_info()["port"]
        r, w = await asyncio.open_connection("127.0.0.1", port)
        for _ in range(json_server.MAX_FAILED_IN_A_ROW):
            w.write(b"nonsense\n")
        await w.drain()
        lines = [await asyncio.wait_for(r.readline(), 5) for _ in range(json_server.MAX_FAILED_IN_A_ROW)]
        self.assertTrue(all(b'"ok":false' in line for line in lines))
        self.assertEqual(b"", await asyncio.wait_for(r.readline(), 5))      # then it is closed
        w.close()
        with mock.patch.object(json_server, "CONNECTION_LIFETIME_SECONDS", 0.5):
            r, w = await asyncio.open_connection("127.0.0.1", port)
            start = time.monotonic()
            self.assertEqual(b"", await asyncio.wait_for(r.readline(), 5))
            self.assertLess(time.monotonic() - start, 3)
            w.close()
        await _admin(self.state, "admin_shutdown")
        await asyncio.wait_for(task, 15)


# --- 4, 11 -----------------------------------------------------------------------------------------------------
class SmallServerPieces(unittest.IsolatedAsyncioTestCase):
    async def test_a_failing_periodic_job_keeps_running(self):
        calls = []

        def job():
            calls.append(1)
            raise PermissionError("antivirus has the file")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            task = asyncio.create_task(json_server._periodic(0.01, job, "autosave"))
            await asyncio.sleep(0.2)
            task.cancel()
        self.assertGreater(len(calls), 3)
        self.assertIn("PermissionError", err.getvalue())

    async def test_connections_per_address_count_an_ipv6_household_once(self):
        from server.lobby.throttle import key_for
        self.assertEqual(key_for("2001:db8:1:2::1"), key_for("2001:db8:1:2:aaaa::9"))
        self.assertIsNone(key_for("127.0.0.1"))


# --- 12 --------------------------------------------------------------------------------------------------------
class CliPieces(unittest.TestCase):
    def test_admin_calls_go_to_loopback_first(self):
        from server import cli
        self.assertEqual(["127.0.0.1"], cli._admin_hosts("0.0.0.0"))
        self.assertEqual(["127.0.0.1"], cli._admin_hosts("127.0.0.1"))
        self.assertEqual(["127.0.0.1", "192.168.1.20"], cli._admin_hosts("192.168.1.20"))
        self.assertEqual(["::1"], cli._admin_hosts("::"))
        self.assertEqual(["::1", "2001:db8::5"], cli._admin_hosts("2001:db8::5"))

    def test_a_packaged_app_does_not_hand_its_unpack_folder_to_the_server(self):
        from server import cli
        env = {"PATH": "x", "_MEIPASS2": "C:\\Temp\\_MEI123", "_PYI_APPLICATION_HOME_DIR": "C:\\Temp\\_MEI123",
               "_PYI_PARENT_PROCESS_LEVEL": "1"}
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "frozen", True, create=True):
            child = cli._child_env()
            args = type("A", (), {"state_dir": Path(d) / "server"})()
            cwd = cli._child_cwd(args)
        self.assertEqual("1", child["PYINSTALLER_RESET_ENVIRONMENT"])
        self.assertFalse([k for k in child if k.startswith("_PYI_") or k == "_MEIPASS2"])
        self.assertEqual("x", child["PATH"])
        self.assertEqual(str((Path(d) / "server").resolve()), cwd)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertIn("_MEIPASS2", cli._child_env())          # running from source: untouched


# --- 18 --------------------------------------------------------------------------------------------------------
class CertificateLock(unittest.TestCase):
    def test_a_second_process_waits_for_the_first_and_uses_its_pair(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            lock = folder / selfsigned.LOCK_NAME
            lock.write_text("4242")                                 # another process is making the pair
            made = []
            result = {}

            def other():
                with mock.patch.object(selfsigned, "make_certificate", side_effect=lambda *a: made.append(1)):
                    with mock.patch.object(selfsigned, "fingerprint_of", return_value="fp"):
                        result["out"] = selfsigned.ensure_certificate(folder)
            t = threading.Thread(target=other)
            t.start()
            time.sleep(0.3)
            self.assertTrue(t.is_alive())                           # waiting, not writing its own half
            (folder / "key.pem").write_text("KEY")
            (folder / "cert.pem").write_text("CERT")
            lock.unlink()
            t.join(5)
            self.assertEqual([], made)
            self.assertEqual("fp", result["out"][2])
            self.assertFalse(lock.exists())

    def test_temporary_files_have_unique_names_and_the_lock_is_released(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(selfsigned, "make_certificate", return_value=("CERT", "KEY", "x")), \
                    mock.patch.object(selfsigned, "fingerprint_of", return_value="fp"):
                selfsigned.ensure_certificate(Path(d))
            self.assertEqual(["cert.pem", "key.pem"], sorted(p.name for p in Path(d).iterdir()))
            self.assertEqual("KEY", (Path(d) / "key.pem").read_text())


if __name__ == "__main__":
    unittest.main()
