import pathlib
import unittest

UI = pathlib.Path(__file__).resolve().parent.parent / "launcher" / "ui" / "index.html"
SCAN = pathlib.Path(__file__).resolve().parent.parent / "launcher" / "pcscan.py"


class DoctorScanRefreshTests(unittest.TestCase):
    def test_scan_view_reports_when_it_finished(self):
        self.assertIn('"finished_at": self.finished_at', SCAN.read_text(encoding="utf-8"))

    def test_visit_dialogue_notices_a_scan_finishing(self):
        src = UI.read_text(encoding="utf-8")
        for needle in ("refreshLines", "const fin=async", "stale", "You just scanned this computer"):
            self.assertIn(needle, src)

    def test_stale_never_scanned_lines_are_dropped_after_refresh(self):
        src = UI.read_text(encoding="utf-8")
        self.assertIn("buildVisit(fresh,true)", src)

    def test_case_cards_do_not_shadow_the_act_helper(self):
        src = UI.read_text(encoding="utf-8")
        line = next(l for l in src.split("\n") if l.startswith("function caseCards"))
        self.assertNotIn("const act=", line)         # "I don't need it" calls act(): a local of that name broke the button

    def test_pc_games_never_ask_for_an_emulator(self):
        import tempfile
        from pathlib import Path
        from launcher.app import LauncherApp
        app = LauncherApp(Path(tempfile.mkdtemp()))
        app.games = {"x": {"id": "x", "console": "pc", "title": "T", "path": "steam://rungameid/1", "region": "", "compat_id": "x"}}
        kinds = [i["key"] for i in app.api_doctor({})["issues"]]
        self.assertNotIn("pc", kinds)


if __name__ == "__main__":
    unittest.main()
