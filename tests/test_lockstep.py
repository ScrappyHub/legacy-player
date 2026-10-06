import unittest

from runtime.sync import InputFrame, LockstepCoordinator, LockstepError


class LockstepTests(unittest.TestCase):
    def test_releases_frame_only_after_all_inputs_arrive(self):
        sync = LockstepCoordinator({"host", "peer"})
        self.assertIsNone(sync.submit(InputFrame(0, "peer", buttons=1)))
        bundle = sync.submit(InputFrame(0, "host", buttons=2))
        self.assertIsNotNone(bundle)
        self.assertEqual(0, bundle.frame)
        self.assertEqual(["host", "peer"], [item.participant_id for item in bundle.inputs])

    def test_rejects_duplicate_and_stale_inputs(self):
        sync = LockstepCoordinator({"host", "peer"})
        sync.submit(InputFrame(0, "host", buttons=0))
        with self.assertRaisesRegex(LockstepError, "duplicate"):
            sync.submit(InputFrame(0, "host", buttons=0))
        sync.submit(InputFrame(0, "peer", buttons=0))
        with self.assertRaisesRegex(LockstepError, "stale"):
            sync.submit(InputFrame(0, "host", buttons=0))

    def test_bounds_future_frame_buffer(self):
        sync = LockstepCoordinator({"host", "peer"}, max_frame_lead=2)
        sync.submit(InputFrame(2, "host", buttons=0))
        with self.assertRaisesRegex(LockstepError, "lead window"):
            sync.submit(InputFrame(3, "host", buttons=0))


if __name__ == "__main__":
    unittest.main()
