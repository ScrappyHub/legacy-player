import json
import tempfile
import unittest
from pathlib import Path

from runtime.replay import ReplayRecorder, ReplayStore


class ReplayTests(unittest.TestCase):
    def test_atomic_replay_store_and_event_limit(self):
        recorder = ReplayRecorder("12345678-abcd-1234-abcd-1234567890ab", {}, max_events=1)
        recorder.record("created")
        with self.assertRaisesRegex(RuntimeError, "event limit"):
            recorder.record("overflow")
        with tempfile.TemporaryDirectory() as directory:
            path = ReplayStore(Path(directory)).write(recorder.package())
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(1, saved["event_count"])
            self.assertEqual([], list(Path(directory).glob("*.tmp")))

    def test_replay_store_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReplayStore(Path(directory))
            with self.assertRaisesRegex(ValueError, "unsafe"):
                store.write({"session_id": "../../escape"})

    def test_replay_does_not_accidentally_contain_credentials(self):
        recorder = ReplayRecorder("12345678-abcd-1234-abcd-1234567890ab", {"game": "test"})
        recorder.record("frame", {"buttons": 1})
        serialized = json.dumps(recorder.package())
        self.assertNotIn("credential", serialized.lower())


if __name__ == "__main__":
    unittest.main()
