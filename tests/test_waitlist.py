import unittest

from server.lobby import LobbyError, LobbyService
from tests.test_community_lobby import PROFILE, FakeClock, auth, make


def join(service, code, pid):
    return service.dispatch({"operation": "join", "invite_code": code, "participant_id": pid, "profile": PROFILE})


def status(service, sid, pid, token):
    return service.dispatch({"operation": "join_status", "session_id": sid, "participant_id": pid, "request_token": token})


def room(max_players=2, approval=False, clock=None):
    service = LobbyService(clock=clock) if clock else LobbyService()
    created = service.dispatch({
        "operation": "create", "participant_id": "host", "profile": PROFILE, "adapter_id": "retroarch",
        "game_pack_id": "generic", "require_approval": approval, "max_players": max_players})
    return service, created["session"]["session_id"], auth(created["session"]["session_id"], "host", created["credential"]), created["invite_code"]


class WaitlistTests(unittest.TestCase):
    def test_full_room_queues_in_order_and_first_in_line_gets_the_freed_slot(self):
        service, sid, host, code = room()
        p2 = join(service, code, "p2")
        self.assertEqual("joined", p2["status"])
        a, b = join(service, code, "a"), join(service, code, "b")
        self.assertEqual(("waiting", 1, 2), (a["status"], a["position"], b["position"]))
        self.assertEqual("waiting", status(service, sid, "a", a["request_token"])["status"])
        # a slot opens: the host kicks p2; b polling first must not skip a
        service.dispatch({"operation": "kick", "target_id": "p2", **host})
        self.assertEqual("waiting", status(service, sid, "b", b["request_token"])["status"])
        got = status(service, sid, "a", a["request_token"])
        self.assertEqual("approved", got["status"])
        self.assertIn("a", got["session"]["participants"])
        # room is full again; b keeps waiting at position 1
        self.assertEqual(1, status(service, sid, "b", b["request_token"])["position"])

    def test_host_priority_jumps_the_line_and_is_host_only(self):
        service, sid, host, code = room()
        p2 = join(service, code, "p2")
        a, b = join(service, code, "a"), join(service, code, "b")
        with self.assertRaisesRegex(LobbyError, "only the host"):
            service.dispatch({"operation": "set_priority", "target_id": "b", **auth(sid, "p2", p2["credential"])})
        service.dispatch({"operation": "set_priority", "target_id": "b", "priority": True, **host})
        view = service.dispatch({"operation": "list_waiting", **host})["waiting"]
        self.assertEqual(["b", "a"], [w["participant_id"] for w in view])
        self.assertTrue(view[0]["priority"])
        self.assertEqual(1, status(service, sid, "b", b["request_token"])["position"])
        service.dispatch({"operation": "kick", "target_id": "p2", **host})
        self.assertEqual("approved", status(service, sid, "b", b["request_token"])["status"])
        self.assertEqual("waiting", status(service, sid, "a", a["request_token"])["status"])

    def test_priority_invite_code_queues_ahead(self):
        service, sid, host, code = room()
        join(service, code, "p2")
        vip = service.dispatch({"operation": "invite", "priority": True, **host})
        self.assertTrue(vip["priority"])
        a = join(service, code, "a")
        v = join(service, vip["invite_code"], "vip")
        self.assertEqual(1, v["position"])
        self.assertTrue(v["priority"])
        self.assertEqual(2, status(service, sid, "a", a["request_token"])["position"])

    def test_waiters_who_stop_checking_in_lose_their_place(self):
        clock = FakeClock()
        service, sid, host, code = room(clock=clock)
        join(service, code, "p2")
        a, b = join(service, code, "a"), join(service, code, "b")
        clock.now += 40
        status(service, sid, "b", b["request_token"])  # b keeps polling, a does not
        clock.now += 40
        self.assertEqual(1, status(service, sid, "b", b["request_token"])["position"])
        with self.assertRaisesRegex(LobbyError, "unknown join request"):
            status(service, sid, "a", a["request_token"])
        kinds = [e["kind"] for e in service.dispatch({"operation": "events", "after_seq": 0, **host})["events"]]
        self.assertIn("waitlist_dropped", kinds)

    def test_approval_rooms_send_the_waiter_to_the_host_when_their_turn_comes(self):
        service, sid, host, code = room(approval=True)
        r = join(service, code, "p2")
        service.dispatch({"operation": "decide_join", "target_id": "p2", **host})
        self.assertEqual("approved", status(service, sid, "p2", r["request_token"])["status"])
        a = join(service, code, "a")
        self.assertEqual("waiting", a["status"])
        service.dispatch({"operation": "kick", "target_id": "p2", **host})
        self.assertEqual("pending", status(service, sid, "a", a["request_token"])["status"])
        b = join(service, code, "b")  # a's pending request already holds the free slot
        self.assertEqual("waiting", b["status"])
        with self.assertRaisesRegex(LobbyError, "full"):
            service.dispatch({"operation": "decide_join", "target_id": "b", **host})
        service.dispatch({"operation": "decide_join", "target_id": "a", **host})
        self.assertEqual("approved", status(service, sid, "a", a["request_token"])["status"])

    def test_capacity_validation_and_changes(self):
        service, sid, host, code = room(max_players=2)
        with self.assertRaises(LobbyError):
            service.dispatch({"operation": "create", "participant_id": "x", "profile": PROFILE, "adapter_id": "a", "game_pack_id": "g", "max_players": 9})
        join(service, code, "p2")
        a = join(service, code, "a")
        self.assertEqual("waiting", a["status"])
        service.dispatch({"operation": "set_capacity", "max_players": 3, **host})
        self.assertEqual("approved", status(service, sid, "a", a["request_token"])["status"])
        with self.assertRaisesRegex(LobbyError, "remove a player"):
            service.dispatch({"operation": "set_capacity", "max_players": 2, **host})

    def test_waitlist_survives_a_server_restart_but_not_the_secrets(self):
        service, sid, host, code = room()
        join(service, code, "p2")
        a = join(service, code, "a")
        restored = LobbyService()
        restored.import_state(service.export_state())
        self.assertEqual(1, status(restored, sid, "a", a["request_token"])["position"])

    def test_host_can_remove_someone_from_the_list(self):
        service, sid, host, code = room()
        join(service, code, "p2")
        a = join(service, code, "a")
        service.dispatch({"operation": "decide_join", "target_id": "a", "approve": False, **host})
        self.assertEqual("denied", status(service, sid, "a", a["request_token"])["status"])


class SeatRecoveryTests(unittest.TestCase):
    def test_disconnected_player_is_vacated_and_next_in_line_gets_the_seat(self):
        clock = FakeClock()
        service, sid, host, code = room(clock=clock)
        service.heartbeat_timeout = 10
        p2 = join(service, code, "p2")
        a = join(service, code, "a")
        outcomes = []
        for _ in range(5):  # host and the waiter keep talking; p2 goes silent
            clock.now += 8
            service.dispatch({"operation": "heartbeat", **host})
            outcomes.append(status(service, sid, "a", a["request_token"])["status"])
            service.sweep_disconnected()
        self.assertNotIn("p2", service.sessions[sid].participants)
        self.assertIn("approved", outcomes)
        kinds = [e["kind"] for e in service.dispatch({"operation": "events", "after_seq": 0, **host})["events"]]
        self.assertIn("participant_disconnected", kinds)
        self.assertIn("participant_left", kinds)

    def test_leaving_a_native_netplay_match_does_not_end_it(self):
        service, sid, host, code = room(max_players=3)
        p2 = join(service, code, "p2")
        service.dispatch({"operation": "validate", **host})
        service.dispatch({"operation": "ready", "ready": True, **host})
        service.dispatch({"operation": "ready", "ready": True, **auth(sid, "p2", p2["credential"])})
        self.assertEqual("active", service.sessions[sid].state.value)
        service.dispatch({"operation": "leave", **auth(sid, "p2", p2["credential"])})
        self.assertEqual("active", service.sessions[sid].state.value)
        self.assertNotIn("p2", service.sessions[sid].participants)


class OpenRoomTests(unittest.TestCase):
    def test_browse_lists_open_rooms_without_identities(self):
        service, sid, host, code = room()
        private = service.dispatch({"operation": "create", "participant_id": "secret_host", "profile": PROFILE,
                                    "adapter_id": "retroarch", "game_pack_id": "generic"})
        service.dispatch({"operation": "set_open", "open": True, **host})
        join(service, code, "p2")
        join(service, code, "waiter")
        rooms = service.dispatch({"operation": "browse"})["rooms"]
        self.assertEqual([sid], [r["session_id"] for r in rooms])
        text = str(rooms)
        for secret in ("host", "p2", "waiter", "secret_host", "credential", "192.", "address"):
            self.assertNotIn(secret, text.replace("max_players", "").replace("session_id", "").replace("host_id", ""))
        self.assertEqual((2, 2, 1), (rooms[0]["players"], rooms[0]["max_players"], rooms[0]["waiting"]))
        self.assertIn("max_players_per_room", service.dispatch({"operation": "browse"})["limits"])

    def test_open_room_joins_without_a_code_private_does_not(self):
        service, sid, host, code = room(max_players=3)
        service.dispatch({"operation": "set_open", "open": True, **host})
        joined = service.dispatch({"operation": "join", "open": True, "session_id": sid, "participant_id": "walkin", "profile": PROFILE})
        self.assertEqual("joined", joined["status"])
        service.dispatch({"operation": "set_open", "open": False, **host})
        with self.assertRaisesRegex(LobbyError, "private"):
            service.dispatch({"operation": "join", "open": True, "session_id": sid, "participant_id": "x", "profile": PROFILE})

    def test_server_can_turn_waiting_lines_off(self):
        service = LobbyService(max_waiting=0)
        created = service.dispatch({"operation": "create", "participant_id": "h", "profile": PROFILE, "adapter_id": "a",
                                    "game_pack_id": "g", "max_players": 2})
        join(service, created["invite_code"], "p2")
        with self.assertRaisesRegex(LobbyError, "does not keep waiting lines"):
            join(service, created["invite_code"], "p3")

    def test_bad_label_rejected(self):
        service = LobbyService()
        with self.assertRaisesRegex(LobbyError, "label"):
            service.dispatch({"operation": "create", "participant_id": "h", "profile": PROFILE, "adapter_id": "a",
                              "game_pack_id": "g", "label": "<script>"})


if __name__ == "__main__":
    unittest.main()
