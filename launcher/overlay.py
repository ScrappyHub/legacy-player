"""The in-game overlay: a small Legacy Player window that sits on top of any emulator and opens from a keyboard
shortcut or a controller button combo. The pure parts (parsing, the hold timer) are testable anywhere; the
Windows parts (global hotkey, XInput polling) never raise and do nothing elsewhere."""
from __future__ import annotations

import sys
import threading
import time

TITLE = "Legacy Player overlay"
DEFAULTS = {"enabled": True, "hotkey": "ctrl+shift+l", "pad": ["back", "start"], "hold": 0.8}

MODS = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
PAD_BITS = {"up": 0x0001, "down": 0x0002, "left": 0x0004, "right": 0x0008, "start": 0x0010, "back": 0x0020,
            "ls": 0x0040, "rs": 0x0080, "lb": 0x0100, "rb": 0x0200, "guide": 0x0400,
            "a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000}
PAD_LABELS = {"up": "D-pad up", "down": "D-pad down", "left": "D-pad left", "right": "D-pad right", "start": "Start", "back": "Back / Select",
              "ls": "Left stick click", "rs": "Right stick click", "lb": "Left bumper", "rb": "Right bumper", "guide": "Guide (Xbox) button",
              "a": "A", "b": "B", "x": "X", "y": "Y"}


def parse_hotkey(spec: str) -> tuple[int, int, str]:
    """'ctrl+shift+l' -> (modifier flags, virtual-key code, tidy text). Needs at least one modifier so typing never opens it."""
    parts = [p.strip().lower() for p in str(spec or "").replace(" ", "").split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError("Use a modifier and a key, like Ctrl+Shift+L.")
    key, mods = parts[-1], parts[:-1]
    if any(m not in MODS for m in mods) or len(set(mods)) != len(mods):
        raise ValueError("Start with Ctrl, Alt, Shift or Win, then one key.")
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("The last key must be a letter, a number or F1 to F12.")
    flags = 0
    for m in mods:
        flags |= MODS[m]
    order = [m for m in ("ctrl", "alt", "shift", "win") if m in mods]
    return flags, vk, "+".join(order + [key])


def validate_prefs(body: dict, current: dict) -> dict:
    out = {**DEFAULTS, **{k: v for k, v in (current or {}).items() if k in DEFAULTS}}
    if "enabled" in body:
        out["enabled"] = bool(body["enabled"])
    if "hotkey" in body:
        if str(body["hotkey"] or "").strip() == "":
            out["hotkey"] = ""
        else:
            out["hotkey"] = parse_hotkey(body["hotkey"])[2]
    if "pad" in body:
        pad = [str(p) for p in (body["pad"] or [])]
        if pad and (any(p not in PAD_BITS for p in pad) or len(set(pad)) != len(pad)):
            raise ValueError("That controller combo has a button I do not know.")
        if len(pad) == 1:
            raise ValueError("Pick at least two buttons held together, so it can not open by accident.")
        out["pad"] = pad
    if "hold" in body:
        out["hold"] = max(0.2, min(3.0, float(body["hold"])))
    return out


def names_of(mask: int) -> list[str]:
    return [n for n, bit in PAD_BITS.items() if mask & bit]


class ComboWatcher:
    """True exactly once when every button of the combo has been held for `hold` seconds; lift a button to arm it again."""

    def __init__(self, combo: list[str], hold: float) -> None:
        self.need = 0
        for n in combo:
            self.need |= PAD_BITS.get(n, 0)
        self.hold, self.since, self.fired = hold, None, False

    def feed(self, mask: int, now: float) -> bool:
        if not self.need or (mask & self.need) != self.need:
            self.since, self.fired = None, False
            return False
        if self.since is None:
            self.since = now
        if not self.fired and now - self.since >= self.hold:
            self.fired = True
            return True
        return False


_XINPUT = None


def read_pad_slots() -> dict[int, int]:
    """{controller slot: button mask} for every connected Xbox-style (XInput) controller. Empty off Windows."""
    global _XINPUT
    if sys.platform != "win32":
        return {}
    try:
        import ctypes
        from ctypes import wintypes

        class PAD(ctypes.Structure):
            _fields_ = [("buttons", wintypes.WORD), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                        ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]

        class STATE(ctypes.Structure):
            _fields_ = [("packet", wintypes.DWORD), ("pad", PAD)]

        if _XINPUT is None:
            dll = None
            for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
                try:
                    dll = ctypes.WinDLL(name)
                    break
                except OSError:
                    continue
            if dll is None:
                return {}
            try:
                _XINPUT = dll[100]                         # XInputGetStateEx: the same, plus the Guide button
            except (AttributeError, OSError):
                _XINPUT = dll.XInputGetState
        out = {}
        for slot in range(4):
            st = STATE()
            if _XINPUT(slot, ctypes.byref(st)) == 0:
                out[slot] = int(st.pad.buttons)
        return out
    except Exception:
        return {}


def read_pads() -> list[int]:
    return list(read_pad_slots().values())


class Listeners:
    """Runs the global hotkey and the controller watcher in the background and calls `on_open` when either fires.
    Each start() gets its own stop event and its own threads, so restarting after a settings change never leaves an old
    watcher behind (which would fire the overlay twice and toggle it straight shut)."""

    def __init__(self, on_open) -> None:
        self.on_open = on_open
        self._lock = threading.Lock()
        self._stop: threading.Event | None = None
        self._threads: list[threading.Thread] = []
        self._tids: list[int] = []
        self.error = ""

    def start(self, prefs: dict) -> None:
        self.stop()
        self.error = ""
        if sys.platform != "win32" or not prefs.get("enabled", True):
            return
        with self._lock:
            ev = self._stop = threading.Event()
            if prefs.get("hotkey"):
                ready = threading.Event()
                t = threading.Thread(target=self._hotkey, args=(prefs["hotkey"], ev, ready), daemon=True, name="overlay-hotkey")
                t.start()
                ready.wait(2.0)                       # the thread has registered (or failed) before we return
                self._threads.append(t)
            if prefs.get("pad"):
                t = threading.Thread(target=self._pad, args=(list(prefs["pad"]), float(prefs.get("hold", 0.8)), ev), daemon=True, name="overlay-pad")
                t.start()
                self._threads.append(t)

    def stop(self) -> None:
        with self._lock:
            if self._stop is not None:
                self._stop.set()
            if sys.platform == "win32":
                try:
                    import ctypes
                    for tid in self._tids:
                        ctypes.windll.user32.PostThreadMessageW(tid, 0x0012, 0, 0)   # WM_QUIT
                except Exception:
                    pass
            for t in self._threads:
                t.join(timeout=1.0)
            self._threads, self._tids, self._stop = [], [], None

    def _hotkey(self, spec: str, ev: threading.Event, ready: threading.Event) -> None:
        tid = 0
        try:
            import ctypes
            from ctypes import wintypes
            flags, vk, _ = parse_hotkey(spec)
            user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0x0400, 0x0400, 0)         # gives this thread a message queue
            if not user32.RegisterHotKey(None, 1, flags | 0x4000, vk):              # MOD_NOREPEAT
                self.error = "Another program already uses that shortcut. Pick a different one."
                return
            tid = kernel32.GetCurrentThreadId()
            self._tids.append(tid)
            ready.set()
            while not ev.is_set() and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:                                            # WM_HOTKEY
                    self._fire()
            user32.UnregisterHotKey(None, 1)
        except Exception as exc:
            self.error = str(exc)[:120]
        finally:
            if tid and tid in self._tids:
                self._tids.remove(tid)
            ready.set()

    def _pad(self, combo: list[str], hold: float, ev: threading.Event) -> None:
        watchers: dict[int, ComboWatcher] = {}
        while not ev.wait(0.05):
            now = time.time()
            slots = read_pad_slots()
            for gone in [k for k in watchers if k not in slots]:
                del watchers[gone]
            for slot, mask in slots.items():
                if watchers.setdefault(slot, ComboWatcher(combo, hold)).feed(mask, now):
                    self._fire()

    def _fire(self) -> None:
        try:
            self.on_open()
        except Exception:
            pass
