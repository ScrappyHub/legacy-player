import unittest

from tools.memory_probe.dolphin_attach.ram_sampler import build_sample_offsets


class RamSamplerTests(unittest.TestCase):
    def test_offsets_are_bounded_unique_and_deterministic(self):
        kwargs = dict(region_size=4096, window_size=64, max_scan_bytes=512, alignment=64)
        offsets = build_sample_offsets(**kwargs)
        self.assertEqual(offsets, build_sample_offsets(**kwargs))
        self.assertEqual(offsets, sorted(set(offsets)))
        self.assertEqual(0, offsets[0])
        self.assertTrue(all(0 <= offset <= 4096 - 64 for offset in offsets))


if __name__ == "__main__":
    unittest.main()
