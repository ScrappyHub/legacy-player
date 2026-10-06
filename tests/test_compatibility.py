import unittest

from tools.memory_probe.game_fingerprint.compatibility import (
    UnsupportedGameProfileError,
    require_game_profile,
)


class CompatibilityTests(unittest.TestCase):
    def test_accepts_supported_profile(self):
        game = {"game_id": "GMPE01", "region": "USA"}
        self.assertIs(game, require_game_profile(game))

    def test_rejects_other_games_and_regions(self):
        with self.assertRaises(UnsupportedGameProfileError):
            require_game_profile({"game_id": "GMPP01", "region": "EUR"})


if __name__ == "__main__":
    unittest.main()
