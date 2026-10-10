"""The Legacy Player World themes: day and night follow the clock unless the player picks one, and the tray follows along."""
import time
import unittest

from launcher import world
from launcher.catalog import SETTINGS_SCHEMA


def at(hour, minute=0):
    return time.mktime((2026, 10, 10, hour, minute, 0, 0, 0, -1))


class DayAndNight(unittest.TestCase):
    def test_follow_my_clock_switches_at_seven(self):
        self.assertEqual("night", world.time_now("auto", at(6, 59)))
        self.assertEqual("day", world.time_now("auto", at(7, 0)))
        self.assertEqual("day", world.time_now("auto", at(18, 59)))
        self.assertEqual("night", world.time_now("auto", at(19, 0)))
        self.assertEqual("night", world.time_now("night", at(12)))
        self.assertEqual("day", world.time_now("day", at(23)))

    def test_light_means_the_light_theme_or_a_world_place_by_day(self):
        self.assertTrue(world.looks_light({"theme": "light"}))
        self.assertFalse(world.looks_light({"theme": "dark"}))
        self.assertTrue(world.looks_light({"theme": "harbor", "time_of_day": "day"}))
        self.assertFalse(world.looks_light({"theme": "harbor", "time_of_day": "night"}))
        self.assertTrue(world.looks_light({"theme": "frost", "time_of_day": "auto"}, at(12)))

    def test_every_place_is_a_theme_choice_and_the_page_draws_it(self):
        from pathlib import Path
        page = (Path(__file__).resolve().parent.parent / "launcher" / "ui" / "index.html").read_text(encoding="utf-8")
        for biome, name in world.BIOMES.items():
            self.assertIn(biome, SETTINGS_SCHEMA["theme"]["choices"])
            self.assertIn(f'id:"{biome}",name:"{name}"', page)       # the colours and the scene exist for it
            self.assertIn(f"\n  {biome}:{{still(", page)
        self.assertEqual(list(world.TIMES), SETTINGS_SCHEMA["time_of_day"]["choices"])
        self.assertIn("scene", SETTINGS_SCHEMA["background"]["choices"])


if __name__ == "__main__":
    unittest.main()
