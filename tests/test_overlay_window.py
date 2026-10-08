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

    def test_every_button_does_what_it_says(self):
        code = textwrap.dedent('''
            import time, sys
            from launcher import overlay_window as ow
            state = {"game": {"title": "Bad Dudes", "emulator": "RetroArch", "since": time.time() - 30},
                     "room": {"game": "Bad Dudes", "role": "host", "invite_code": "ABCDE-FGH12", "members": ["a"]},
                     "server": {"running": True, "shared": True, "players": 1, "rooms": 1}, "can_restart": True}
            hits = []
            acts = {k: (lambda k=k: hits.append(k) or k + " done") for k in ("back", "force_quit", "open_app", "server_on", "server_off", "server_restart", "restart_game")}
            o = ow.NativeOverlay(lambda: state, acts, monitor=lambda: {"x": 0, "y": 0, "w": 1000, "h": 700})
            try:
                o.toggle()
            except RuntimeError as exc:
                print("NODISPLAY", exc); sys.exit(0)
            time.sleep(0.6)
            def press(text):
                for b in o._buttons:
                    if b.cget("text").startswith(text):
                        b.invoke(); return
                raise AssertionError("no button " + text + ": " + repr([b.cget("text") for b in o._buttons]))
            labels = [b.cget("text") for b in o._buttons]
            assert labels == ["\u2302  Legacy Player", "Copy", "Turn off", "Restart", "Restart game", "Force quit"], labels
            press("\u2302"); press("Turn off"); time.sleep(0.5); press("Restart"); time.sleep(0.5)
            assert hits[:2] == ["open_app", "server_off"], hits
            press("Restart game"); time.sleep(0.5)
            assert "restart_game" in hits and "server_restart" in hits, hits
            press("Force quit"); assert "force_quit" not in hits, "first press only arms it"
            time.sleep(0.2); press("Press again"); assert "force_quit" in hits and not o.is_open(), hits
            state["server"] = {"running": False}; o.preview = True; o.toggle(); time.sleep(0.5)
            assert [b.cget("text") for b in o._buttons][:3] == ["\u2302  Legacy Player", "Copy", "Turn on"], [b.cget("text") for b in o._buttons]
            state["game"] = None; time.sleep(1.8)
            assert o.is_open(), "a preview stays open with no game"
            o.stop(); print("OK")
        ''')
        env = dict(os.environ, PYTHONPATH=os.getcwd())
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=40, env=env)
        if "NODISPLAY" in out.stdout:
            self.skipTest("no display here")
        self.assertIn("OK", out.stdout, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
