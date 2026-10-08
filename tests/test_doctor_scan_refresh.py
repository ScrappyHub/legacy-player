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


if __name__ == "__main__":
    unittest.main()
