import unittest

from launcher import winplace

MAIN = {"x": 0, "y": 0, "w": 1920, "h": 1080}
SIDE = {"x": 1920, "y": 0, "w": 2560, "h": 1440}


class PlanTests(unittest.TestCase):
    def test_no_monitor_chosen_leaves_it_alone(self):
        self.assertEqual({"move": None, "borderless": False}, winplace.plan((10, 10, 800, 600), None, "fullscreen", True))

    def test_fullscreen_on_chosen_monitor(self):
        r = winplace.plan((100, 100, 800, 600), SIDE, "fullscreen", True)
        self.assertEqual((1920, 0, 2560, 1440), r["move"])
        self.assertTrue(r["borderless"])

    def test_already_covering_the_monitor_is_untouched(self):
        self.assertIsNone(winplace.plan((0, 0, 1920, 1080), MAIN, "fullscreen", True)["move"])

    def test_windowed_moves_to_middle_of_other_monitor(self):
        r = winplace.plan((100, 100, 800, 600), SIDE, "windowed", False)
        self.assertEqual((1920 + (2560 - 800) // 2, (1440 - 600) // 2, 800, 600), r["move"])
        self.assertFalse(r["borderless"])

    def test_windowed_already_on_it(self):
        self.assertIsNone(winplace.plan((300, 200, 800, 600), MAIN, "windowed", False)["move"])

    def test_oversized_window_is_shrunk_to_fit(self):
        r = winplace.plan((0, 0, 5000, 3000), SIDE, "windowed", False)
        self.assertEqual((2560, 1440), r["move"][2:])

    def test_main_window_is_the_big_titled_one(self):
        wins = [{"title": "", "w": 3000, "h": 3000}, {"title": "splash", "w": 300, "h": 200}, {"title": "Game", "w": 800, "h": 600}]
        self.assertEqual("Game", winplace.pick_window(wins)["title"])
        self.assertIsNone(winplace.pick_window([{"title": "", "w": 900, "h": 900}]))

    def test_monitors_empty_off_windows(self):
        import sys
        if sys.platform != "win32":
            self.assertEqual([], winplace.list_monitors())


if __name__ == "__main__":
    unittest.main()
