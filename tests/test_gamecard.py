"""The game card: file-name facts cost nothing; the look-up asks only Wikipedia and Wikidata, once, with consent."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from launcher import gamecard
from launcher.app import AppError, LauncherApp


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(answers: dict, log: list):
    def opener(request, timeout=0):
        url = request.full_url
        log.append(url)
        for key, value in answers.items():
            if key in url:
                return FakeResponse(json.dumps(value).encode())
        raise OSError("no such page")
    return opener


ANSWERS = {
    "list=search": {"query": {"search": [{"title": "Mario Kart 64"}]}},
    "page/summary": {"extract": "Mario Kart 64 is a kart racing game.", "description": "1996 video game", "wikibase_item": "Q1234"},
    "Special:EntityData/Q1234": {"entities": {"Q1234": {"claims": {
        "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+1996-12-14T00:00:00Z"}}}},
                 {"mainsnak": {"datavalue": {"value": {"time": "+1997-02-10T00:00:00Z"}}}}],
        "P1872": [{"mainsnak": {"datavalue": {"value": {"amount": "+4"}}}}],
        "P178": [{"mainsnak": {"datavalue": {"value": {"id": "Q8093"}}}}],
        "P123": [{"mainsnak": {"datavalue": {"value": {"id": "Q8093"}}}}],
        "P136": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}}}},
    "wbgetentities": {"entities": {"Q8093": {"labels": {"en": {"value": "Nintendo"}}}, "Q5": {"labels": {"en": {"value": "racing game"}}}}},
}


class LocalCard(unittest.TestCase):
    def test_version_and_region_come_from_the_file_name(self):
        g = {"title": "Zelda", "region": "USA", "tags": ["Rev 1", "En,Fr"], "extension": ".n64", "console": "n64"}
        card = gamecard.local_card(g, {})
        self.assertEqual("Revision 1", card["version"])
        self.assertEqual("file", card["version_source"])
        self.assertEqual(["En,Fr"], card["file_tags"])
        self.assertEqual("v1.1", gamecard.local_card({"tags": ["v1.1"], "console": "gba"}, {})["version"])
        self.assertEqual("Beta 2", gamecard.local_card({"tags": ["Beta 2"], "console": "gba"}, {})["version"])
        self.assertEqual("", gamecard.local_card({"tags": [], "console": "gba"}, {})["version"])
        self.assertEqual("Mine", gamecard.local_card({"tags": ["Rev 1"], "console": "gba"}, {"version": "Mine"})["version"])


class Lookup(unittest.TestCase):
    def test_lookup_reads_summary_and_wikidata_and_only_those_hosts(self):
        log = []
        out = gamecard.lookup("Mario Kart 64", "Nintendo 64", fake_opener(ANSWERS, log))
        self.assertTrue(out["found"])
        f = out["fields"]
        self.assertEqual("Mario Kart 64 is a kart racing game.", f["description"])
        self.assertEqual("1996-12-14", f["release"])                         # the earliest release date
        self.assertEqual(4, f["max_players"])
        self.assertEqual("Nintendo", f["developer"])
        self.assertEqual("racing game", f["genre"])                          # the Wikidata genre beats the summary's blurb
        self.assertTrue(all(u.startswith("https://en.wikipedia.org/") or u.startswith("https://www.wikidata.org/") for u in log))
        self.assertTrue(out["source"].startswith("https://en.wikipedia.org/wiki/"))

    def test_nothing_found_is_not_an_error_but_unreachable_is(self):
        out = gamecard.lookup("Nothing", "NES", fake_opener({"list=search": {"query": {"search": []}}}, []))
        self.assertFalse(out["found"])
        with self.assertRaises(LookupError):
            gamecard.lookup("Nothing", "NES", fake_opener({}, []))

    def test_cache_runs_once_and_is_kept_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            log = []
            cards = gamecard.CardLookups(Path(d), fake_opener(ANSWERS, log))
            self.assertIsNone(cards.cached("g1"))
            cards.start("g1", "Mario Kart 64", "Nintendo 64", run_inline=True)
            self.assertEqual("done", cards.state("g1")["state"])
            self.assertEqual("1996-12-14", cards.cached("g1")["fields"]["release"])
            again = gamecard.CardLookups(Path(d), fake_opener(ANSWERS, log))
            self.assertIsNotNone(again.cached("g1"))
            cards.forget("g1")
            self.assertIsNone(cards.cached("g1"))


class CardApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        games = base / "games" / "N64"
        games.mkdir(parents=True)
        (games / "Mario Kart 64 (USA) (Rev 1).z64").write_bytes(b"\x80\x37\x12\x40" + b"\0" * 64)
        self.app = LauncherApp(base / "data", [str(base / "games")])
        self.app.cards.opener = fake_opener(ANSWERS, [])
        self.gid = next(iter(self.app.games))

    def tearDown(self):
        self.tmp.cleanup()

    def test_card_labels_each_fact_and_the_player_wins(self):
        card = self.app.api_game_card({"id": self.gid})
        self.assertEqual("Revision 1", card["fields"]["version"]["value"])
        self.assertEqual("file", card["fields"]["version"]["source"])
        self.assertEqual("", card["fields"]["release"]["value"])
        self.assertEqual("USA", card["region"])
        with self.assertRaises(AppError):
            self.app.api_game_card({"id": self.gid, "action": "lookup", "consent": True})      # internet is off by default
        self.app.catalog.set_setting("allow_internet", True)
        with self.assertRaises(AppError):
            self.app.api_game_card({"id": self.gid, "action": "lookup"})                       # and it asks first
        self.app.cards.start(self.gid, "Mario Kart 64", "Nintendo 64", run_inline=True)
        card = self.app.api_game_card({"id": self.gid})
        self.assertEqual("wikidata", card["fields"]["release"]["source"])
        self.assertEqual("1996-12-14", card["fields"]["release"]["value"])
        self.assertEqual("wikipedia", card["fields"]["description"]["source"])
        self.assertEqual(4, card["players"]["max"])
        card = self.app.api_game_card({"id": self.gid, "action": "save", "release": "1997", "description": "My note"})
        self.assertEqual({"value": "1997", "source": "you"}, card["fields"]["release"])
        self.assertEqual("you", card["fields"]["description"]["source"])
        card = self.app.api_game_card({"id": self.gid, "action": "save", "release": ""})
        self.assertEqual("wikidata", card["fields"]["release"]["source"])


if __name__ == "__main__":
    unittest.main()
