"""A plain Tk window that runs a libretro core in-process: the first "one window" of the
owned shell. Keyboard: arrows, Z (B), X (A), A (Y), S (X), Enter (Start), Shift (Select),
Q/W (L/R), F5 save state, F7 load state, Esc quit. Pads come later through the shell.

Video only (no audio yet): Tk cannot stream audio; SDL2 is the planned next layer.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from .core import Core

KEYS = {"Left": "left", "Right": "right", "Up": "up", "Down": "down", "z": "b", "x": "a", "a": "y", "s": "x",
        "Return": "start", "Shift_L": "select", "q": "l", "w": "r"}


def run(core_path: str, rom: str, system_dir: str, save_dir: str, scale: int = 3) -> int:
    try:
        import tkinter as tk
    except ImportError:
        print("This Python has no tkinter; the in-process viewer needs it.", file=sys.stderr)
        return 2
    core = Core(core_path, system_dir, save_dir)
    av = core.load(rom)
    root = tk.Tk()
    root.title(f"Legacy Player — {Path(rom).stem}")
    label = tk.Label(root)
    label.pack()
    held: set[str] = set()
    state: dict = {"snapshot": None}

    def on_key(event, down: bool):
        name = KEYS.get(event.keysym)
        if name:
            (held.add if down else held.discard)(name)
        elif down and event.keysym == "F5":
            state["snapshot"] = core.save_state()
        elif down and event.keysym == "F7" and state["snapshot"]:
            core.load_state(state["snapshot"])
        elif down and event.keysym == "Escape":
            root.destroy()
    root.bind("<KeyPress>", lambda e: on_key(e, True))
    root.bind("<KeyRelease>", lambda e: on_key(e, False))
    frame_time = 1.0 / (av["fps"] or 60)
    next_at = time.perf_counter()

    def tick():
        nonlocal next_at
        core.press(0, *held)
        core.run(1)
        w, h, rgb = core.frame_rgb()
        if w:
            ppm = b"P6 %d %d 255\n" % (w, h) + rgb
            image = tk.PhotoImage(data=ppm).zoom(scale, scale)
            label.configure(image=image)
            label.image = image
        next_at += frame_time
        delay = max(1, int((next_at - time.perf_counter()) * 1000))
        root.after(delay, tick)
    root.after(1, tick)
    root.mainloop()
    core.close()
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: python -m frontend.window <core> <rom> [system_dir] [save_dir]")
        return 2
    system_dir, save_dir = (argv[3:5] + ["", ""])[:2]       # either folder may be left out
    return run(argv[1], argv[2], system_dir, save_dir)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
