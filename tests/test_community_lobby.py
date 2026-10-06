import tempfile
import unittest
from pathlib import Path

from server.lobby import LobbyError, LobbyService
from server.lobby.invites import InviteBook
from server.state_store import StateStore

PROFILE = {"game_id": "GMPE01", "region": "USA"}


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(service, approval=False):
    created = service.dispatch(
        {
            "operation": "create",
            "participant_id": "host",
            "profile": PROFILE,
            "adapter_id": "dolphin",
            "game_pack_id": "mario_party_4",
            "require_approval": approval,
        }
    )
    return created


def auth(sid, pid, cred):
    return {"session_id": sid, "participant_id": pid, "credential": cred}


class InviteTests(unittest.TestCase):
    def test_invite_code_joins_and_host_is_notified(self):
        service = LobbyService()
        created = make(service)
        sid, host_cred = created["session"]["session_id"], created["credential"]
        joined = service.dispatch(
            {"operation": "join", "invite_code": created["invite_code"], "participant_id": "p2", "profile": PROFILE}
        )
        self.assertEqual("joined", joined["status"])
        events = service.dispatch({"operation": "events", **auth(sid, "host", host_cred)})["events"]
        self.assertIn("participant_joined", [e["kind"] for e in events])

    def test_codes_are_not_stored_in_plaintext(self):
        service = LobbyService()
        created = make(service)
        blob = repr(service.export_state())
        self.assertNotIn(created["invite_code"].replace("-", ""), blob)
        self.assertNotIn(created["join_code"], blob)
        self.assertNotIn(created["credential"], blob)

    def test_invite_expires_and_enforces_use_limit(self):
        clock = FakeClock()
        book = InviteBook(clock=clock)
        code, _ = book.create("s1", ttl_seconds=60, max_uses=1)
        self.assertEqual("s1", book.redeem(code.lower().replace("-", " ")))
        with self.assertRaisesRegex(Exception, "invalid or expired"):
            book.redeem(code)
        code2, _ = book.create("s1", ttl_seconds=60)
        clock.now += 61
        with self.assertRaisesRegex(Exception, "invalid or expired"):
            book.redeem(code2)

    def test_wrong_guesses_lock_out_brute_force(self):
        book = InviteBook(max_failures=3)
        for _ in range(3):
            with self.assertRaises(Exception):
                book.redeem("AAAAA-AAAAA")
        with self.assertRaisesRegex(Exception, "too many"):
            book.redeem("AAAAA-AAAAA")

    def test_host_can_revoke_invites(self):
        service = LobbyService()
        created = make(service)
        sid = created["session"]["session_id"]
        service.dispatch({"operation": "revoke_invites", **auth(sid, "host", created["credential"])})
        with self.assertRaisesRegex(LobbyError, "invalid or expired"):
            service.dispatch(
                {"operation": "join", "invite_code": created["invite_code"], "participant_id": "p2", "profile": PROFILE}
            )


class ApprovalTests(unittest.TestCase):
    def test_host_approves_join_request(self):
        service = LobbyService()
        created = make(service, approval=True)
        sid, host_cred = created["session"]["session_id"], created["credential"]
        pending = service.dispatch(
            {"operation": "join", "invite_code": created["invite_code"], "participant_id": "p2", "profile": PROFILE}
        )
        self.assertEqual("pending", pending["status"])
        events = service.dispatch({"operation": "events", **auth(sid, "host", host_cred)})["events"]
        self.assertEqual("join_requested", events[-1]["kind"])
        waiting = {"operation": "join_status", "session_id": sid, "participant_id": "p2", "request_token": pending["request_token"]}
        self.assertEqual("pending", service.dispatch(waiting)["status"])
        service.dispatch({"operation": "decide_join", "target_id": "p2", "approve": True, **auth(sid, "host", host_cred)})
        result = service.dispatch(waiting)
        self.assertEqual("approved", result["status"])
        service.dispatch({"operation": "heartbeat", **auth(sid, "p2", result["credential"])})

    def test_denied_request_cannot_get_a_credential(self):
        service = LobbyService()
        created = make(service, approval=True)
        sid = created["session"]["session_id"]
        pending = service.dispatch(
            {"operation": "join", "invite_code": created["invite_code"], "participant_id": "p2", "profile": PROFILE}
        )
        service.dispatch({"operation": "decide_join", "target_id": "p2", "approve": False, **auth(sid, "host", created["credential"])})
        status = service.dispatch(
            {"operation": "join_status", "session_id": sid, "participant_id": "p2", "request_token": pending["request_token"]}
        )
        self.assertEqual("denied", status["status"])
        self.assertNotIn("credential", status)


class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.service = LobbyService(clock=self.clock, heartbeat_timeout=30)
        created = make(self.service)
        self.sid, self.host = created["session"]["session_id"], created["credential"]
        self.joined = self.service.dispatch(
            {"operation": "join", "invite_code": created["invite_code"], "participant_id": "p2", "profile": PROFILE}
        )

    def events(self, pid="host", cred=None, after=0):
        cred = cred or self.host
        return self.service.dispatch({"operation": "events", "after_seq": after, **auth(self.sid, pid, cred)})["events"]

    def test_kick_notifies_and_blocks_with_reason(self):
        self.service.dispatch({"operation": "kick", "target_id": "p2", "reason": "afk", **auth(self.sid, "host", self.host)})
        self.assertEqual("participant_kicked", self.events()[-1]["kind"])
        with self.assertRaisesRegex(LobbyError, "kicked from session: afk"):
            self.service.dispatch({"operation": "heartbeat", **auth(self.sid, "p2", self.joined["credential"])})

    def test_only_host_can_kick_and_host_cannot_be_kicked(self):
        with self.assertRaisesRegex(LobbyError, "only the host"):
            self.service.dispatch({"operation": "kick", "target_id": "host", **auth(self.sid, "p2", self.joined["credential"])})
        with self.assertRaisesRegex(LobbyError, "cannot be kicked"):
            self.service.dispatch({"operation": "kick", "target_id": "host", **auth(self.sid, "host", self.host)})

    def test_leave_emits_event_and_frees_seat(self):
        self.service.dispatch({"operation": "leave", **auth(self.sid, "p2", self.joined["credential"])})
        self.assertEqual("participant_left", self.events()[-1]["kind"])
        again = self.service.dispatch(
            {"operation": "join", "session_id": self.sid, "invite_code": self.service.dispatch({"operation": "invite", **auth(self.sid, "host", self.host)})["invite_code"], "participant_id": "p2", "profile": PROFILE}
        )
        self.assertEqual("joined", again["status"])

    def test_silent_player_is_flagged_disconnected_then_reconnects(self):
        self.clock.now += 31
        flagged = self.service.sweep_disconnected()
        self.assertTrue(any(e["kind"] == "participant_disconnected" for e in flagged))
        self.service.dispatch({"operation": "heartbeat", **auth(self.sid, "p2", self.joined["credential"])})
        self.assertEqual("participant_reconnected", self.events()[-1]["kind"])

    def test_kick_during_active_session_fails_it_cleanly(self):
        self.service.dispatch({"operation": "validate", **auth(self.sid, "host", self.host)})
        self.service.dispatch({"operation": "ready", **auth(self.sid, "host", self.host)})
        self.service.dispatch({"operation": "ready", **auth(self.sid, "p2", self.joined["credential"])})
        self.service.lockstep_used.add(self.sid)  # frames were streamed through the server (lockstep match)
        self.service.dispatch({"operation": "kick", "target_id": "p2", **auth(self.sid, "host", self.host)})
        self.assertEqual("failed", self.service.sessions[self.sid].state.value)

    def test_host_only_events_are_hidden_from_players(self):
        self.service.dispatch({"operation": "invite", **auth(self.sid, "host", self.host)})
        kinds = [e["kind"] for e in self.events("p2", self.joined["credential"])]
        self.assertNotIn("invite_created", kinds)


class EndpointTests(MembershipTests):
    def test_endpoint_needs_validated_session_and_host(self):
        with self.assertRaisesRegex(LobbyError, "matching game"):
            self.service.dispatch({"operation": "set_endpoint", "address": "10.0.0.2", "port": 55435, **auth(self.sid, "host", self.host)})
        self.service.dispatch({"operation": "validate", **auth(self.sid, "host", self.host)})
        with self.assertRaisesRegex(LobbyError, "only the host"):
            self.service.dispatch({"operation": "set_endpoint", "address": "10.0.0.2", "port": 55435, **auth(self.sid, "p2", self.joined["credential"])})
        for bad in ({"address": "a b", "port": 55435}, {"address": "10.0.0.2", "port": 70000}, {"address": "-x", "port": 5}):
            with self.assertRaises(LobbyError):
                self.service.dispatch({"operation": "set_endpoint", **bad, **auth(self.sid, "host", self.host)})
        self.service.dispatch({"operation": "set_endpoint", "address": "10.0.0.2", "port": 55435, **auth(self.sid, "host", self.host)})
        got = self.service.dispatch({"operation": "get_endpoint", **auth(self.sid, "p2", self.joined["credential"])})
        self.assertEqual({"kind": "direct", "address": "10.0.0.2", "port": 55435}, got["endpoint"])
        kinds = [e["kind"] for e in self.events("p2", self.joined["credential"])]
        self.assertIn("endpoint_published", kinds)

    def test_traversal_host_code_endpoint(self):
        self.service.dispatch({"operation": "validate", **auth(self.sid, "host", self.host)})
        with self.assertRaisesRegex(LobbyError, "host code"):
            self.service.dispatch({"operation": "set_endpoint", "kind": "code", "address": "bad code!", "**": 1, **auth(self.sid, "host", self.host)})
        self.service.dispatch({"operation": "set_endpoint", "kind": "code", "address": "AB12CD34", **auth(self.sid, "host", self.host)})
        got = self.service.dispatch({"operation": "get_endpoint", **auth(self.sid, "p2", self.joined["credential"])})
        self.assertEqual({"kind": "code", "address": "AB12CD34"}, got["endpoint"])

    def test_address_is_not_leaked_in_events_and_outsiders_cannot_read_it(self):
        self.service.dispatch({"operation": "validate", **auth(self.sid, "host", self.host)})
        self.service.dispatch({"operation": "set_endpoint", "address": "10.9.9.9", "port": 55435, **auth(self.sid, "host", self.host)})
        self.assertNotIn("10.9.9.9", repr(self.events()))
        with self.assertRaisesRegex(LobbyError, "credential"):
            self.service.dispatch({"operation": "get_endpoint", **auth(self.sid, "p2", "wrong")})


class ResumeTests(unittest.TestCase):
    def test_snapshot_round_trip_keeps_seats_codes_and_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory))
            book = InviteBook(pepper=store.pepper())
            first = LobbyService(invite_book=book)
            created = make(first)
            sid, host = created["session"]["session_id"], created["credential"]
            joined = first.dispatch(
                {"operation": "join", "invite_code": created["invite_code"], "participant_id": "p2", "profile": PROFILE}
            )
            first.dispatch({"operation": "validate", **auth(sid, "host", host)})
            first.dispatch({"operation": "ready", **auth(sid, "host", host)})
            first.dispatch({"operation": "ready", **auth(sid, "p2", joined["credential"])})
            self.assertEqual("active", first.sessions[sid].state.value)
            first.announce_stopping()
            store.save_snapshot(first.export_state())

            second = LobbyService(invite_book=InviteBook(pepper=StateStore(Path(directory)).pepper()))
            second.import_state(StateStore(Path(directory)).load_snapshot())
            # Active matches return to the ready barrier; seats and credentials survive.
            self.assertEqual("ready-barrier", second.sessions[sid].state.value)
            events = second.dispatch({"operation": "events", **auth(sid, "p2", joined["credential"])})["events"]
            kinds = [e["kind"] for e in events]
            self.assertIn("server_stopping", kinds)
            self.assertIn("session_resumed", kinds)
            second.dispatch({"operation": "ready", **auth(sid, "host", host)})
            result = second.dispatch({"operation": "ready", **auth(sid, "p2", joined["credential"])})
            self.assertEqual("active", result["session"]["state"])

    def test_corrupt_snapshot_does_not_block_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory))
            (Path(directory) / "lobby_state.json").write_text("{not json")
            self.assertIsNone(store.load_snapshot())


if __name__ == "__main__":
    unittest.main()
