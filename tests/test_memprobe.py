import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from launcher import memprobe

PAGE = 4096
PAGES = 64


class FakeDolphin:
    """A pretend Dolphin: a block of RAM we can change, one page that changes by itself, and a game title."""

    def __init__(self, game_id="GTSE01", title="Test Game (GTSE01)"):
        self.ram = bytearray(PAGE * PAGES)
        self.base = 0x10000000
        self.alive = True
        self.game = {"game_id": game_id, "region": "USA", "active_window_title": title}
        self.tick = itertools.count(1)
        self.noisy_page = 7

    def read_region(self, proc, address, size):
        offset = address - self.base
        self.ram[self.noisy_page * PAGE] = next(self.tick) % 256           # this page never sits still
        return bytes(self.ram[offset:offset + size])

    def write(self, page, value):
        self.ram[page * PAGE + 100] = value

    def deps(self):
        return SimpleNamespace(find_process=lambda: SimpleNamespace(pid=42) if self.alive else None,
                               find_ram=lambda proc: {"base_address": self.base, "region_size": PAGE * PAGES},
                               detect_game=lambda proc: dict(self.game), read_region=self.read_region)


class MemProbeTests(unittest.TestCase):
    def setUp(self):
        memprobe.NOISE_GAP = memprobe.POST_DELAY = 0
        self.fake = FakeDolphin()
        self.probe = memprobe.MemProbe(Path(tempfile.mkdtemp()))
        self.probe._load = self.fake.deps

    def do(self, label, pages, value=1):
        self.probe.baseline(label)
        for p in pages:
            self.fake.write(p, value)
        return self.probe.capture()

    def test_status_when_ready_and_when_dolphin_is_closed(self):
        status = self.probe.status()
        self.assertTrue(status["ready"])
        self.assertEqual(PAGES, status["ram"]["pages"])
        self.fake.alive = False
        self.assertIn("Dolphin is not running", self.probe.status()["why"])

    def test_pages_that_change_by_themselves_are_ignored(self):
        out = self.do("coin", [10, 11])
        self.assertEqual(2, out["changed_pages"])
        self.assertGreaterEqual(out["noise_pages"], 1)

    def test_a_label_gets_more_trustworthy_when_repeated(self):
        first = self.do("roll_dice", [10, 11, 12], 1)
        self.assertEqual("candidate", first["learned"]["confidence"])
        second = self.do("roll_dice", [11, 12, 20], 2)           # page 10 was a fluke, page 20 is new
        self.assertEqual("grounded", second["learned"]["confidence"])
        self.assertEqual(2, second["learned"]["pages"])
        saved = self.probe.status()["learned"]
        self.assertEqual([("roll_dice", 2, 2, "grounded")], [(x["name"], x["runs"], x["pages"], x["confidence"]) for x in saved])

    def test_a_repeat_that_shares_nothing_replaces_the_old_pages(self):
        self.do("jump", [10, 11])
        out = self.do("jump", [30, 31], 3)
        self.assertEqual("candidate", out["learned"]["confidence"])
        self.assertFalse(out["learned"]["agreed_with_before"])
        self.assertTrue(out["learned"]["note"])

    def test_a_new_capture_is_compared_with_the_other_labels_of_the_same_game(self):
        self.do("start_minigame", [10, 11, 12, 13])
        out = self.do("start_minigame_again", [10, 11, 12, 13], 5)
        self.assertEqual("MATCH_START_MINIGAME", out["token"])
        self.assertEqual("start_minigame", out["best_label"])
        other = self.do("something_else", [40, 41, 42], 9)
        self.assertEqual("NO_STRONG_MATCH", other["token"])

    def test_nothing_changed_says_so(self):
        out = self.do("idle", [])
        self.assertEqual("NOTHING_CHANGED", out["token"])
        self.assertEqual([], self.probe.status()["learned"])

    def test_any_game_gets_its_own_memory(self):
        self.do("coin", [10])
        self.fake.game = {"game_id": "GALE01", "region": "USA", "active_window_title": "Super Smash Bros. Melee (GALE01)"}
        self.assertEqual([], self.probe.status()["learned"])          # the other game's labels are not here
        self.do("coin", [20])
        self.assertEqual(1, len(self.probe.status()["learned"]))
        self.fake.game = {"game_id": "unknown", "region": "unknown", "active_window_title": "Some Homebrew Game"}
        status = self.probe.status()
        self.assertEqual("title-some-homebrew-game", status["game"]["key"])
        self.assertEqual([], status["learned"])

    def test_switching_game_between_baseline_and_capture_is_refused(self):
        self.probe.baseline("x")
        self.fake.game = {"game_id": "GALE01", "region": "USA", "active_window_title": "Melee (GALE01)"}
        with self.assertRaises(memprobe.ProbeError):
            self.probe.capture()
        self.assertFalse(self.probe.status()["waiting_for_action"])

    def test_mario_party_4_starts_with_its_shipped_pages(self):
        self.fake.game = {"game_id": "GMPE01", "region": "USA", "active_window_title": "Mario Party 4 (GMPE01)"}
        labels = {x["name"]: x for x in self.probe.status()["learned"]}
        self.assertIn("coin_total_change_once", labels)
        self.assertEqual("shipped", labels["coin_total_change_once"]["confidence"])

    def test_capture_needs_a_baseline_and_cancel_clears_it(self):
        with self.assertRaises(memprobe.ProbeError):
            self.probe.capture()
        self.probe.baseline("x")
        self.assertTrue(self.probe.status()["waiting_for_action"])
        self.probe.cancel()
        self.assertFalse(self.probe.status()["waiting_for_action"])

    def test_forget_removes_a_label(self):
        self.do("oops", [10])
        self.probe.forget("oops")
        self.assertEqual([], self.probe.status()["learned"])
        with self.assertRaises(memprobe.ProbeError):
            self.probe.forget("oops")

    def test_labels_are_made_safe_and_the_record_is_written(self):
        out = self.do("a b/c!", [10])
        self.assertEqual("a_b_c", out["label"])
        record = json.loads(Path(out["file"]).read_text(encoding="utf-8"))
        self.assertEqual(1, record["changed_page_count"])
        self.assertEqual(hex(self.fake.base + 10 * PAGE), record["changed_pages"][0]["absolute_address"])

    def test_unreadable_memory_is_explained(self):
        self.fake.read_region = lambda proc, address, size: None
        self.probe._load = self.fake.deps
        with self.assertRaises(memprobe.ProbeError):
            self.probe.baseline("x")

    def test_other_systems_get_a_plain_message(self):
        if sys.platform == "win32":
            self.skipTest("this is the non-Windows message")
        status = memprobe.MemProbe(Path(tempfile.mkdtemp())).status()
        self.assertFalse(status["supported"])
        self.assertIn("Windows", status["why"])


class AppProbeTests(unittest.TestCase):
    def test_baseline_needs_consent(self):
        from tests.test_app_actions import make_app
        from launcher.app import AppError
        app, _ = make_app()
        with self.assertRaises(AppError):
            app.api_probe_baseline({"label": "x"})
