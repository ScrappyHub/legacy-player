"""The in-game overlay as a real overlay: a small frameless, always-on-top panel (like the Xbox, Steam or NVIDIA ones),
not a browser window. It shows what is running and for how long, and manages the game and the room from right there.

Built on tkinter (it ships with Python and is already inside the packaged app). One thread owns every Tk call; other
threads talk to it through a queue. If tkinter or a display is missing, `available()` says so and the caller falls back.
Windows is the target; the code is plain Tk, so it also runs (and is tested) elsewhere."""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable

try:                                                   # the packaged app has it; a bare Python may not
    import tkinter as tk
except Exception:                                      # pragma: no cover - depends on the machine
    tk = None  # type: ignore[assignment]

BG, CARD, TEXT, MUTED, ACCENT, BAD = "#10142a", "#1a2040", "#e9ecff", "#9aa3c7", "#4f8cff", "#e5484d"
WIDTH = 340


def available() -> bool:
    return tk is not None


def duration(seconds: float) -> str:
    """"7 min", "1 h 05 min": how long a session has been going."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "under a minute"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


class NativeOverlay:
    """`state()` returns {"game": {"title","emulator","since"} | None, "room": {...} | None}.
    `actions` maps "back" / "fullscreen" / "windowed" / "force_quit" / "open_app" to callables (run on the overlay's thread).
    `pad()` (optional) returns a list of pressed-button masks for controller navigation: dpad up/down, A to press, B to close."""

    def __init__(self, state: Callable[[], dict], actions: dict[str, Callable[[], object]],
                 monitor: Callable[[], dict | None] | None = None, pad: Callable[[], list[int]] | None = None) -> None:
        self.state, self.actions, self.monitor, self.pad = state, actions, monitor, pad
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._open = False
        self._lock = threading.RLock()
        self._stopping = False
        self.error = ""

    # --- called from any thread ---------------------------------------------------------------------------
    def toggle(self) -> bool:
        """Show the overlay, or hide it if it is showing. Returns whether it is open afterwards."""
        with self._lock:
            self._ensure()
            self._open = not self._open
            self._q.put("show" if self._open else "hide")
            return self._open

    def close(self) -> None:
        if self._thread and self._open:
            self._open = False
            self._q.put("hide")

    def is_open(self) -> bool:
        return self._open

    def stop(self) -> None:
        with self._lock:
            if self._thread:
                self._stopping = True
                self._open = False
                self._q.put("quit")

    def _ensure(self) -> None:
        if self._thread and self._thread.is_alive() and not self._stopping:
            return
        if tk is None:
            raise RuntimeError("tkinter is not available")
        if self._thread and self._thread.is_alive():          # one that was asked to quit: let it finish first
            self._thread.join(2.0)
        self._stopping = False
        self.error = ""
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="overlay-window")
        self._thread.start()
        self._ready.wait(5.0)
        if self.error:
            raise RuntimeError(self.error)

    # --- the Tk thread -----------------------------------------------------------------------------------
    def _run(self) -> None:
        try:
            self.root = tk.Tk()
            self.root.withdraw()
            self.win = tk.Toplevel(self.root)
            self.win.withdraw()
            self.win.overrideredirect(True)                 # no title bar, no border, no taskbar button
            self.win.attributes("-topmost", True)
            try:
                self.win.attributes("-alpha", 0.96)
            except tk.TclError:
                pass
            self.win.configure(bg=ACCENT)                   # a 1px accent frame around the card
            self.body = tk.Frame(self.win, bg=BG)
            self.body.pack(padx=1, pady=1, fill="both", expand=True)
            self.win.bind("<Escape>", lambda e: self._hide(user=True))
            self._buttons: list = []
            self._armed = 0.0
            self._was: dict[int, bool] = {}
            self.root.after(40, self._pump)
            self._ready.set()
            self.root.mainloop()
        except Exception as exc:                            # pragma: no cover - display problems
            self.error = f"{type(exc).__name__}: {exc}"
            self._ready.set()
        finally:
            self._open = False

    def _pump(self) -> None:
        try:
            self._pump_once()
        except Exception as exc:                        # one bad frame must never end the overlay for the rest of the session
            self.error = ""
            print(f"overlay: {type(exc).__name__}: {exc}", flush=True)
        if not self._stopping:
            self.root.after(60, self._pump)

    def _pump_once(self) -> None:
        try:
            while True:
                cmd = self._q.get_nowait()
                if cmd == "show":
                    self._draw()
                    self._place()
                    self.win.deiconify()
                    self.win.lift()
                    self.win.attributes("-topmost", True)
                    try:
                        self.win.focus_force()
                    except tk.TclError:
                        pass
                elif cmd == "hide":
                    self.win.withdraw()
                elif cmd == "quit":
                    self._stopping = True
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        if self._open:
            self._poll_pad()
            if time.time() - getattr(self, "_drawn", 0) > 1.0:
                self._tick()

    def _signature(self, s: dict) -> str:
        g, r = s.get("game") or {}, s.get("room") or {}
        return repr((g.get("title"), g.get("emulator"), r.get("game"), r.get("invite_code"), tuple(r.get("members") or []), time.time() - self._armed < 4.0))

    def _tick(self) -> None:
        """Once a second: redraw only if something changed, otherwise just move the session timer (no flicker)."""
        self._drawn = time.time()
        try:
            s = self.state() or {}
        except Exception:
            return
        if not s.get("game"):
            self._hide()                                    # the game ended: nothing left to manage
            return
        if self._signature(s) != getattr(self, "_sig", None):
            self._draw(force=True)                      # the card grew or shrank (a room appeared): resize the window to fit
            return
        game = s.get("game")
        if game and game.get("since") and getattr(self, "_timer", None) is not None:
            self._timer.configure(text="Playing for " + duration(time.time() - game["since"]) + "  ·  in " + str(game.get("emulator") or "an emulator"))

    def _hide(self, user: bool = False) -> None:
        self._open = False
        self.win.withdraw()

    def _place(self) -> None:
        self.win.update_idletasks()
        w, h = WIDTH, self.win.winfo_reqheight()
        mon = None
        try:
            mon = self.monitor() if self.monitor else None
        except Exception:
            mon = None
        if mon:
            x, y = mon["x"] + mon["w"] - w - 24, mon["y"] + 24
        else:
            x, y = self.win.winfo_screenwidth() - w - 24, 24
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _label(self, text: str, size: int = 10, bold: bool = False, fg: str = TEXT, pady=(0, 0)):
        lab = tk.Label(self.body, text=text, bg=BG, fg=fg, anchor="w", justify="left", wraplength=WIDTH - 32,
                       font=("Segoe UI", size, "bold" if bold else "normal"))
        lab.pack(fill="x", padx=14, pady=pady)
        return lab

    def _button(self, parent, text: str, action: str | None, bad: bool = False, command=None, side=None, small: bool = False):
        def run() -> None:
            try:
                if command:
                    command()
                elif action:
                    self.actions[action]()
            except Exception as exc:                        # a failing action must never take the overlay down
                self._flash(f"That did not work: {exc}")
        b = tk.Button(parent, text=text, command=run, bd=0, relief="flat", cursor="hand2", takefocus=1,
                      bg=("#3a1d27" if bad else CARD), fg=(BAD if bad else TEXT), activebackground=(BAD if bad else ACCENT),
                      activeforeground="#ffffff", highlightthickness=2, highlightbackground=(BG), highlightcolor=ACCENT,
                      font=("Segoe UI", 9 if small else 10), padx=8 if small else 10, pady=2 if small else 7)
        if side == "right":
            b.pack(side="right")
        elif side:
            b.pack(side=side, fill="x", expand=True, padx=(0, 6) if side == "left" else 0)
        else:
            b.pack(fill="x", padx=14, pady=3)
        b.bind("<Return>", lambda e: b.invoke())
        self._buttons.append(b)
        return b

    def _flash(self, text: str) -> None:
        self._note = text
        self._draw(force=True)

    def _draw(self, force: bool = False) -> None:
        focus_idx = -1
        try:
            cur = self.win.focus_get()
            focus_idx = self._buttons.index(cur) if cur in self._buttons else -1
        except Exception:
            pass
        for child in self.body.winfo_children():
            child.destroy()
        self._buttons = []
        self._drawn = time.time()
        try:
            s = self.state() or {}
        except Exception:
            s = {}
        game, room = s.get("game"), s.get("room")
        self._sig, self._timer = self._signature(s), None
        head = tk.Frame(self.body, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 0))
        tk.Label(head, text="Legacy Player", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        tk.Button(head, text="✕", command=lambda: self._hide(), bd=0, bg=BG, fg=MUTED, activebackground=BG, activeforeground=TEXT,
                  font=("Segoe UI", 10), cursor="hand2", takefocus=0, highlightthickness=0).pack(side="right")
        if game:
            self._label(game["title"], 13, True, pady=(4, 0))
            since = game.get("since")
            line = ("Playing for " + duration(time.time() - since) + "  ·  " if since else "") + "in " + str(game.get("emulator") or "an emulator")
            self._timer = self._label(line, 9, fg=MUTED, pady=(0, 8))
            self._button(self.body, "Back to the game", "back").configure(bg=ACCENT, fg="#ffffff")
            row = tk.Frame(self.body, bg=BG)
            row.pack(fill="x", padx=14, pady=3)
            self._button(row, "Full screen", "fullscreen", side="left")
            self._button(row, "Windowed", "windowed", side="left")
            armed = time.time() - self._armed < 4.0

            def quit_click() -> None:
                if time.time() - self._armed < 4.0:
                    self._armed = 0.0
                    self.actions["force_quit"]()
                    self._hide()
                else:
                    self._armed = time.time()
                    self._draw(force=True)
            self._button(self.body, "Press again to force quit (unsaved progress is lost)" if armed else "Force quit game", None, bad=True, command=quit_click)
        else:
            self._label("No game is running", 13, True, pady=(4, 8))
        if room:
            box = tk.Frame(self.body, bg=CARD)
            box.pack(fill="x", padx=14, pady=(10, 3))
            tk.Label(box, text=("Hosting " if room.get("role") == "host" else "In room: ") + str(room.get("game") or ""), bg=CARD, fg=MUTED,
                     anchor="w", font=("Segoe UI", 9), wraplength=WIDTH - 60).pack(fill="x", padx=10, pady=(8, 2))
            names = ", ".join(room.get("members") or [])
            if names:
                tk.Label(box, text=names, bg=CARD, fg=TEXT, anchor="w", font=("Segoe UI", 9), wraplength=WIDTH - 60).pack(fill="x", padx=10)
            if room.get("invite_code"):
                code = room["invite_code"]
                r = tk.Frame(box, bg=CARD)
                r.pack(fill="x", padx=10, pady=(4, 8))
                tk.Label(r, text=code, bg=CARD, fg=TEXT, font=("Consolas", 10, "bold")).pack(side="left")
                self._button(r, "Copy", None, command=lambda c=code: self._copy(c), side="right", small=True)
        self._button(self.body, "Open Legacy Player", "open_app")
        note = getattr(self, "_note", "")
        if note:
            self._label(note, 9, fg=BAD, pady=(4, 0))
        tk.Frame(self.body, bg=BG, height=10).pack()
        if focus_idx >= 0 and focus_idx < len(self._buttons):
            self._buttons[focus_idx].focus_set()
        elif self._buttons:
            self._buttons[0].focus_set()
        self.win.update_idletasks()
        if force:
            self._place()

    def _copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self._flash("")

    # --- controller: d-pad up/down moves, A presses, B closes ----------------------------------------------
    def _edge(self, key: int, on: bool) -> bool:
        before = self._was.get(key, False)
        self._was[key] = on
        return on and not before

    def _poll_pad(self) -> None:
        if not self.pad:
            return
        try:
            masks = self.pad() or []
        except Exception:
            return
        held = 0
        for m in masks:
            held |= m
        UP, DOWN, A, B = 0x0001, 0x0002, 0x1000, 0x2000
        if self._edge(UP, bool(held & UP)):
            self._move(-1)
        if self._edge(DOWN, bool(held & DOWN)):
            self._move(1)
        if self._edge(A, bool(held & A)):
            cur = self.win.focus_get()
            if cur in self._buttons:
                cur.invoke()
        if self._edge(B, bool(held & B)):
            self._hide()

    def _move(self, step: int) -> None:
        if not self._buttons:
            return
        try:
            idx = self._buttons.index(self.win.focus_get())
        except ValueError:
            idx = -1
        self._buttons[(idx + step) % len(self._buttons)].focus_set()
