import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from launcher import memprobe

PAGE = 4096


def fake_reader():
    mod = types.ModuleType("tools.memory_probe.memory_reader.reader")
    mod.memory = {}
    mod.read_region = lambda proc, address, size: mod.memory.get(address, b"\0" * size)[:size].ljust(size, b"\0")
    mod.iter_readable_regions = lambda proc, limit=512: []
    return mod


class MemProbeTests(unittest.TestCase):
    def setUp(self):
        for name in [n for n in sys.modules if n.startswith("tools.memory_probe.")]:
            sys.modules.pop(name, None)
        self.reader = fake_reader()
        self.saved = sys.modules.get("tools.memory_probe.memory_reader.reader")
        self.saved_fp = sys.modules.get("tools.memory_probe.game_fingerprint.fingerprint")
        fp = types.ModuleType("tools.memory_probe.game_fingerprint.fingerprint")      # the real one loads Windows libraries
        fp.detect_game = lambda proc: {}
        sys.modules["tools.memory_probe.game_fingerprint.fingerprint"] = fp
        sys.modules["tools.memory_probe.memory_reader.reader"] = self.reader
        import importlib
        hav = importlib.import_module("tools.memory_probe.hot_action_validator")      # not 'from package import': that can hand back an old copy
        hav.CLUSTER_PATH = Path(__file__).resolve().parent.parent / "game_packs" / "mario_party_4" / "ACTION_PAGE_CLUSTERS_v1.json"
        self.hav = hav
        self.base = 0x10000000
        self.ram = {"base_address": self.base, "region_size": 0x2000000, "protect": 0x04, "type": 0x20000, "score": 1}
        self.alive = True
        self.probe = memprobe.MemProbe(Path(tempfile.mkdtemp()))
        self.probe._load = lambda: SimpleNamespace(
            hav=hav, find_process=lambda: SimpleNamespace(pid=42) if self.alive else None,
            find_ram=lambda proc: self.ram, detect_game=lambda proc: {"game_id": "GMPE01", "region": "USA", "phase_hint": "board"})
        self.cluster_name = next(n for n, c in hav.load_clusters()["clusters"].items() if c.get("page_offsets"))      # one that is grounded
        self.cluster = [int(o) for o in hav.load_clusters()["clusters"][self.cluster_name]["page_offsets"]]

    def tearDown(self):
        if self.saved_fp is not None:
            sys.modules["tools.memory_probe.game_fingerprint.fingerprint"] = self.saved_fp
        else:
            sys.modules.pop("tools.memory_probe.game_fingerprint.fingerprint", None)
        if self.saved is not None:
            sys.modules["tools.memory_probe.memory_reader.reader"] = self.saved
        else:
            sys.modules.pop("tools.memory_probe.memory_reader.reader", None)

    def test_status_when_ready_and_when_dolphin_is_closed(self):
        self.assertTrue(self.probe.status()["ready"])
        self.alive = False
        status = self.probe.status()
        self.assertFalse(status["ready"])
        self.assertIn("Dolphin is not running", status["why"])

    def test_matching_action_is_recognised_and_saved(self):
        self.probe.baseline("inboard event")
        for off in self.cluster:                                  # the action changes every page in the known cluster
            self.reader.memory[self.base + off] = b"\x01" * PAGE
        out = self.probe.capture()
        self.assertEqual(len(self.cluster), out["changed_pages"])
        self.assertEqual(self.cluster_name, out["best_cluster"])
        self.assertNotEqual("NO_STRONG_MATCH", out["token"])
        self.assertTrue(Path(out["file"]).is_file())
        self.assertIn("inboard_event", Path(out["file"]).name)  # the label (spaces made safe)
        with self.assertRaises(memprobe.ProbeError):              # the baseline is used up
            self.probe.capture()

    def test_nothing_changed_is_no_strong_match(self):
        self.probe.baseline("nothing")
        out = self.probe.capture()
        self.assertEqual(0, out["changed_pages"])
        self.assertEqual("NO_STRONG_MATCH", out["token"])

    def test_capture_needs_a_baseline_and_cancel_clears_it(self):
        with self.assertRaises(memprobe.ProbeError):
            self.probe.capture()
        self.probe.baseline("x")
        self.assertTrue(self.probe.status()["waiting_for_action"])
        self.probe.cancel()
        self.assertFalse(self.probe.status()["waiting_for_action"])

    def test_labels_are_made_safe_for_file_names(self):
        self.assertEqual("a_b_c", self.probe.baseline("a b/c")["label"].replace("__", "_"))

    def test_other_systems_get_a_plain_message(self):
        if sys.platform == "win32":
            self.skipTest("this is the non-Windows message")
        probe = memprobe.MemProbe(Path(tempfile.mkdtemp()))
        status = probe.status()
        self.assertFalse(status["supported"])
        self.assertIn("Windows", status["why"])


class AppProbeTests(unittest.TestCase):
    def test_baseline_needs_consent(self):
        from tests.test_app_actions import make_app
        from launcher.app import AppError
        app, _ = make_app()
        with self.assertRaises(AppError):
            app.api_probe_baseline({"label": "x"})
        self.assertFalse(app.api_probe_status({}).get("waiting_for_action"))
