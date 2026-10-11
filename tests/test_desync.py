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

    def test_window_overflow_stores_nothing_and_keeps_the_waiting_frame(self):
        tracker = DesyncTracker({"host", "peer"}, max_pending=2)
        tracker.submit(0, "host", "a" * 64)
        tracker.submit(1, "host", "a" * 64)
        with self.assertRaisesRegex(RuntimeError, "not recorded"):
            tracker.submit(2, "host", "a" * 64)
        self.assertEqual({0, 1}, set(tracker.pending))           # the refused frame left no trace, frame 0 was not dropped
        self.assertTrue(tracker.submit(0, "peer", "a" * 64).matched)
        self.assertFalse(tracker.submit(2, "host", "a" * 64).complete)   # room again: accepted now

    def test_completed_frames_cannot_be_resubmitted(self):
        tracker = DesyncTracker({"host", "peer"})
        tracker.submit(5, "host", "a" * 64)
        self.assertTrue(tracker.submit(5, "peer", "a" * 64).matched)
        for who in ("host", "peer"):
            for frame in (5, 4, 0):
                with self.assertRaisesRegex(ValueError, "already settled"):
                    tracker.submit(frame, who, "b" * 64)          # a different hash for a settled frame is refused
        self.assertEqual({}, tracker.pending)
        self.assertTrue(tracker.submit(6, "host", "a" * 64) is not None)

    def test_older_waiting_frames_are_settled_by_a_newer_complete_one(self):
        tracker = DesyncTracker({"host", "peer"})
        tracker.submit(1, "host", "a" * 64)                       # the peer never checks frame 1
        tracker.submit(2, "host", "a" * 64)
        tracker.submit(2, "peer", "a" * 64)
        self.assertEqual({}, tracker.pending)
        with self.assertRaisesRegex(ValueError, "already settled"):
            tracker.submit(1, "peer", "a" * 64)


if __name__ == "__main__":
    unittest.main()
