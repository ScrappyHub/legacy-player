"""Load tests kept small enough for CI; the full numbers are in docs/STRESS_TEST_RESULTS.md."""
import json
import socket
import threading
import unittest

from server.lobby import LobbyService
from tests.test_community_lobby import PROFILE
from tests.test_launcher import ServerThread


class LobbyLoadTests(unittest.TestCase):
    def test_many_rooms_with_waiting_lines_in_parallel(self):
        server = ServerThread().start()
        self.addCleanup(server.stop)
        errors = []

        def call(req):
            with socket.create_connection(("127.0.0.1", server.port), timeout=10) as s:
                s.sendall(json.dumps(req).encode() + b"\n")
                r = json.loads(s.makefile("rb").readline())
            if not r.get("ok"):
                raise RuntimeError(r.get("error"))
            return r["result"]

        def room(i):
            try:
                c = call({"operation": "create", "participant_id": f"h{i}", "profile": PROFILE, "adapter_id": "a",
                          "game_pack_id": "g", "max_players": 2})
                sid, code = c["session"]["session_id"], c["invite_code"]
                auth = {"session_id": sid, "participant_id": f"h{i}", "credential": c["credential"]}
                call({"operation": "join", "invite_code": code, "participant_id": f"g{i}", "profile": PROFILE})
                w = [call({"operation": "join", "invite_code": code, "participant_id": f"w{i}{k}", "profile": PROFILE}) for k in range(4)]
                assert all(x["status"] == "waiting" for x in w)
                call({"operation": "kick", "target_id": f"g{i}", "reason": "x", **auth})
                got = call({"operation": "join_status", "session_id": sid, "participant_id": f"w{i}0", "request_token": w[0]["request_token"]})
                assert got["status"] == "approved", got
                assert len(call({"operation": "list_waiting", **auth})["waiting"]) == 3
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{i}: {exc}")

        threads = [threading.Thread(target=room, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual([], errors)

    def test_service_handles_thousands_of_operations_in_memory(self):
        service = LobbyService(max_sessions=500)
        for i in range(400):
            c = service.dispatch({"operation": "create", "participant_id": f"h{i}", "profile": PROFILE, "adapter_id": "a", "game_pack_id": "g"})
            for k in range(3):
                service.dispatch({"operation": "join", "invite_code": c["invite_code"], "participant_id": f"p{i}{k}", "profile": PROFILE})
        snapshot = service.export_state()
        restored = LobbyService(max_sessions=500)
        restored.import_state(snapshot)
        self.assertEqual(400, len(restored.sessions))
        self.assertLess(len(json.dumps(snapshot)), 20 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
