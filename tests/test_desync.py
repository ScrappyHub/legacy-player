import unittest

from runtime.desync import DesyncTracker


class DesyncTrackerTests(unittest.TestCase):
    def test_reports_match_and_mismatch_only_when_complete(self):
        tracker = DesyncTracker({"host", "peer"})
        digest_a = "a" * 64
        digest_b = "b" * 64
        self.assertFalse(tracker.submit(0, "host", digest_a).complete)
        matched = tracker.submit(0, "peer", digest_a)
        self.assertTrue(matched.complete)
        self.assertTrue(matched.matched)
        tracker.submit(1, "host", digest_a)
        mismatch = tracker.submit(1, "peer", digest_b)
        self.assertFalse(mismatch.matched)

    def test_rejects_malformed_hashes_and_bounds_pending_frames(self):
        tracker = DesyncTracker({"host", "peer"}, max_pending=1)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            tracker.submit(0, "host", "not-a-hash")
        tracker.submit(0, "host", "a" * 64)
        with self.assertRaisesRegex(RuntimeError, "window exceeded"):
            tracker.submit(1, "host", "b" * 64)


if __name__ == "__main__":
    unittest.main()
