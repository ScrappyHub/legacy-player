"""Text must stay readable (WCAG 4.5:1, 3:1 for large text), including on the gradient cards, in both themes.
Skipped when Playwright or Pillow is missing. The full page list runs with `python tools/contrast_check.py`."""
import importlib.util
import unittest
from pathlib import Path

try:
    import PIL  # noqa: F401
    from playwright.sync_api import sync_playwright  # noqa: F401
    READY = True
except ImportError:      # pragma: no cover
    READY = False

TOOL = Path(__file__).resolve().parent.parent / "tools" / "contrast_check.py"


@unittest.skipUnless(READY, "Playwright and Pillow are needed")
class ContrastTests(unittest.TestCase):
    def test_key_pages_are_readable_in_both_themes(self):
        spec = importlib.util.spec_from_file_location("contrast_check", TOOL)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.assertEqual(0, tool.main(pages=["home", "library", "servers", "setup", "settings"]))
