import unittest

from launcher import winstyle


class WinStyleTests(unittest.TestCase):
    def test_colours_are_converted_to_windows_order(self):
        self.assertEqual(0x00402010, winstyle.colorref((0x10, 0x20, 0x40)))
        self.assertEqual((0x05, 0x08, 0x16), winstyle.parse_hex("#050816"))
        self.assertIsNone(winstyle.parse_hex("rgb(1,2,3)"))
        self.assertIsNone(winstyle.parse_hex(""))

    def test_dark_and_light_are_told_apart(self):
        self.assertTrue(winstyle.is_dark((5, 8, 22)))
        self.assertFalse(winstyle.is_dark((0xee, 0xf2, 0xfb)))

    def test_apply_sets_caption_text_and_border_on_each_window(self):
        calls = []
        n = winstyle.apply("#050816", "#eef1ff", windows=[11, 22], setter=lambda h, a, v: calls.append((h, a, v)))
        self.assertEqual(2, n)
        by = {(h, a): v for h, a, v in calls}
        self.assertEqual(winstyle.colorref((5, 8, 22)), by[(11, winstyle.DWMWA_CAPTION_COLOR)])
        self.assertEqual(winstyle.colorref((0xee, 0xf1, 0xff)), by[(22, winstyle.DWMWA_TEXT_COLOR)])
        self.assertEqual(1, by[(11, winstyle.DWMWA_USE_IMMERSIVE_DARK_MODE)])

    def test_bad_colours_or_failures_do_nothing(self):
        self.assertEqual(0, winstyle.apply("nope", "#fff", windows=[1], setter=lambda *a: None))
        def boom(*a): raise OSError("x")
        self.assertEqual(0, winstyle.apply("#050816", "#eef1ff", windows=[1], setter=boom))

    def test_other_systems_are_left_alone(self):
        import sys
        if sys.platform != "win32":
            self.assertEqual(0, winstyle.apply("#050816", "#eef1ff"))


if __name__ == "__main__":
    unittest.main()
