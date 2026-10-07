import os
import subprocess
import sys
import textwrap
import unittest

from launcher import overlay_window


@unittest.skipUnless(overlay_window.available(), "tkinter is not installed here")
class OverlayPanelTests(unittest.TestCase):
    def test_panel_opens_closes_and_hides_when_the_game_ends(self):
        """Runs the real panel in a child process (it needs a display); skipped quietly where there is none."""
        code = textwrap.dedent('''
            import time, sys
            from launcher import overlay_window as ow
            state = {"game": {"title": "Bomberman II", "emulator": "RetroArch", "since": time.time() - 90},
                     "room": {"game": "Bomberman II", "role": "host", "invite_code": "K7QD2-M9XPA", "members": ["a", "b"]}}
            hits = []
            acts = {k: (lambda k=k: hits.append(k)) for k in ("back", "fullscreen", "windowed", "force_quit", "open_app")}
            o = ow.NativeOverlay(lambda: state, acts, monitor=lambda: {"x": 0, "y": 0, "w": 1000, "h": 700})
            try:
                assert o.toggle() is True
            except RuntimeError as exc:
                print("NODISPLAY", exc); sys.exit(0)
            time.sleep(0.6)
            assert o.is_open()
            texts = [w.cget("text") for w in o.body.winfo_children() if w.winfo_class() == "Label"]
            assert any("Bomberman II" in t for t in texts), texts
            assert any("Playing for 1 min" in t for t in texts), texts
            assert o.toggle() is False
            time.sleep(0.3)
            o.toggle(); time.sleep(0.4)
            state["game"] = None
            time.sleep(1.8)
            assert not o.is_open()
            o.stop()
            print("OK")
        ''')
        env = dict(os.environ, PYTHONPATH=os.getcwd())
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=40, env=env)
        if "NODISPLAY" in out.stdout:
            self.skipTest("no display here")
        self.assertIn("OK", out.stdout, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
