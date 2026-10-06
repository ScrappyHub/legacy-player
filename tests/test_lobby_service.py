import unittest
import tempfile
from pathlib import Path

from server.lobby import LobbyError, LobbyService


PROFILE = {"game_id": "GMPE01", "region": "USA"}


class LobbyServiceTests(unittest.TestCase):
    def setUp(self):
        self.initialize(LobbyService())

    def initialize(self, service):
        self.service = service
        created = self.service.dispatch(
            {
                "operation": "create",
                "participant_id": "host",
                "profile": PROFILE,
                "adapter_id": "dolphin",
                "game_pack_id": "mario_party_4",
            }
        )
        self.session_id = created["session"]["session_id"]
        self.join_code = created["join_code"]
        self.host_credential = created["credential"]
        joined = self.service.dispatch(
            {
                "operation": "join",
                "session_id": self.session_id,
                "join_code": self.join_code,
                "participant_id": "peer",
                "profile": PROFILE,
            }
        )
        self.peer_credential = joined["credential"]

    def auth(self, participant_id, credential):
        return {
            "session_id": self.session_id,
            "participant_id": participant_id,
            "credential": credential,
        }

    def activate(self):
        self.service.dispatch(
            {
                "operation": "validate",
                **self.auth("host", self.host_credential),
            }
        )
        self.service.dispatch(
            {"operation": "ready", **self.auth("host", self.host_credential)}
        )
        result = self.service.dispatch(
            {"operation": "ready", **self.auth("peer", self.peer_credential)}
        )
        self.assertEqual("active", result["session"]["state"])

    def test_rejects_bad_join_code_and_credentials(self):
        with self.assertRaisesRegex(LobbyError, "invalid join code"):
            self.service.dispatch(
                {
                    "operation": "join",
                    "session_id": self.session_id,
                    "join_code": "wrong",
                    "participant_id": "intruder",
                    "profile": PROFILE,
                }
            )
        with self.assertRaisesRegex(LobbyError, "invalid participant credential"):
            self.service.dispatch(
                {
                    "operation": "status",
                    **self.auth("host", "wrong"),
                }
            )

    def test_two_peers_release_and_poll_the_same_frame(self):
        self.activate()
        first = self.service.dispatch(
            {
                "operation": "input",
                **self.auth("host", self.host_credential),
                "frame": 0,
                "buttons": 1,
            }
        )
        self.assertFalse(first["released"])
        second = self.service.dispatch(
            {
                "operation": "input",
                **self.auth("peer", self.peer_credential),
                "frame": 0,
                "buttons": 2,
            }
        )
        self.assertTrue(second["released"])
        for participant_id, credential in (
            ("host", self.host_credential),
            ("peer", self.peer_credential),
        ):
            result = self.service.dispatch(
                {
                    "operation": "poll",
                    **self.auth(participant_id, credential),
                    "after_frame": -1,
                }
            )
            self.assertEqual([0], [item["frame"] for item in result["bundles"]])

    def test_only_host_can_validate(self):
        with self.assertRaisesRegex(LobbyError, "only the host"):
            self.service.dispatch(
                {
                    "operation": "validate",
                    **self.auth("peer", self.peer_credential),
                }
            )

    def test_desync_fails_session_and_writes_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            service = LobbyService(replay_dir=Path(directory))
            self.initialize(service)
            self.activate()
            first = service.dispatch(
                {
                    "operation": "checkpoint",
                    **self.auth("host", self.host_credential),
                    "frame": 0,
                    "state_hash": "a" * 64,
                }
            )
            self.assertFalse(first["checkpoint"]["complete"])
            second = service.dispatch(
                {
                    "operation": "checkpoint",
                    **self.auth("peer", self.peer_credential),
                    "frame": 0,
                    "state_hash": "b" * 64,
                }
            )
            self.assertEqual("failed", second["session"]["state"])
            self.assertEqual(1, len(list(Path(directory).glob("*.json"))))
            with self.assertRaisesRegex(LobbyError, "expired|credential"):
                service.dispatch(
                    {"operation": "status", **self.auth("host", self.host_credential)}
                )

    def test_capacity_and_input_bounds(self):
        service = LobbyService(max_sessions=1, max_participants=2)
        self.initialize(service)
        create = {
            "operation": "create",
            "participant_id": "host",
            "profile": PROFILE,
            "adapter_id": "dolphin",
            "game_pack_id": "mario_party_4",
        }
        with self.assertRaisesRegex(LobbyError, "session capacity"):
            service.dispatch({**create, "participant_id": "other-host"})
        self.activate()
        with self.assertRaisesRegex(LobbyError, "32-bit"):
            service.dispatch(
                {
                    "operation": "input",
                    **self.auth("host", self.host_credential),
                    "frame": 0,
                    "buttons": 1 << 40,
                }
            )

    def test_finalized_session_retention_is_bounded(self):
        service = LobbyService(max_retained_sessions=1)
        for index in range(2):
            self.initialize(service)
            self.activate()
            service.dispatch(
                {"operation": "complete", **self.auth("host", self.host_credential)}
            )
        self.assertEqual(1, len(service.finalized_replays))
        self.assertEqual(1, len(service.finalized_order))


if __name__ == "__main__":
    unittest.main()
