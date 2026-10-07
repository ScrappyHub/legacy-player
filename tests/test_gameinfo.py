import unittest

from launcher import gameinfo


class GameInfoTests(unittest.TestCase):
    def test_single_player_known(self):
        r = gameinfo.players_for("n64", "Super Mario 64 (USA)")
        self.assertEqual(1, r["max"]); self.assertEqual("known", r["source"]); self.assertFalse(r["shareable"])

    def test_party_and_coop(self):
        self.assertEqual(4, gameinfo.players_for("gamecube", "Mario Party 4 (USA)")["max"])
        r = gameinfo.players_for("nes", "Contra (USA)")
        self.assertTrue(r["coop"]); self.assertEqual(2, r["max"])

    def test_longest_title_wins(self):
        self.assertEqual(1, gameinfo.players_for("genesis", "Sonic the Hedgehog (USA)")["max"])
        self.assertEqual(2, gameinfo.players_for("genesis", "Sonic the Hedgehog 2 (World)")["max"])
        self.assertEqual(4, gameinfo.players_for("gamecube", "Legend of Zelda Four Swords Adventures")["max"])

    def test_unknown_falls_back_to_console_and_says_so(self):
        r = gameinfo.players_for("snes", "Obscure Thing")
        self.assertEqual("console", r["source"]); self.assertEqual(2, r["max"]); self.assertEqual(5, r["hw"])

    def test_player_override_wins(self):
        r = gameinfo.players_for("n64", "Super Mario 64", "2")
        self.assertEqual(("you", 2), (r["source"], r["max"]))
        self.assertEqual("console", gameinfo.players_for("n64", "Zzz", "99")["source"])


if __name__ == "__main__":
    unittest.main()
