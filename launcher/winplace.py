"""Put a game's window where the player wants it: in front, on the chosen monitor, full screen or in a window.

Windows only (everything here quietly does nothing elsewhere). The decisions are in plain functions (`plan`, `pick_window`)
so they can be tested anywhere; the parts that talk to Windows are small and wrapped so a failure never stops a game.
"""
from __future__ import annotations

import sys
import threading
import time

NEAR = 3      # pixels: a window this close to a monitor's rectangle counts as covering it


def plan(win: tuple[int, int, int, int], mon: dict | None, mode: str, has_flag: bool) -> dict:
    """What to do with a window at win=(x, y, w, h). mon={'x','y','w','h'} or None (leave it where the emulator put it).
    Returns {'move': (x, y, w, h) or None, 'borderless': bool}."""
    if not mon:
        return {"move": None, "borderless": False}
    x, y, w, h = win
    covers = abs(x - mon["x"]) <= NEAR and abs(y - mon["y"]) <= NEAR and abs(w - mon["w"]) <= NEAR and abs(h - mon["h"]) <= NEAR
    if mode == "fullscreen":
        if covers:
            return {"move": None, "borderless": False}
        return {"move": (mon["x"], mon["y"], mon["w"], mon["h"]), "borderless": True}
    # windowed: only move it when it is not on the chosen monitor already
    cx, cy = x + w // 2, y + h // 2
    inside = mon["x"] <= cx < mon["x"] + mon["w"] and mon["y"] <= cy < mon["y"] + mon["h"]
    if inside:
        return {"move": None, "borderless": False}
    nw, nh = min(w, mon["w"]), min(h, mon["h"])
    return {"move": (mon["x"] + (mon["w"] - nw) // 2, mon["y"] + (mon["h"] - nh) // 2, nw, nh), "borderless": False}


def pick_window(windows: list[dict]) -> dict | None:
    """From visible top-level windows of the game's process, the main one: has a title, biggest area."""
    usable = [w for w in windows if w.get("title") and w["w"] > 160 and w["h"] > 120]
    return max(usable, key=lambda w: w["w"] * w["h"]) if usable else None


# ---- Windows plumbing --------------------------------------------------------------------------------------------

def _user32():
    import ctypes
    return ctypes.windll.user32


def list_monitors() -> list[dict]:
    """[{'index', 'name', 'x', 'y', 'w', 'h', 'primary', 'label'}], primary first. Empty when not on Windows."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]
        found: list[dict] = []
        proc_t = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

        def cb(hmon, hdc, rect, lparam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcMonitor
                found.append({"name": info.szDevice, "x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top,
                              "primary": bool(info.dwFlags & 1)})
            return 1
        ctypes.windll.user32.EnumDisplayMonitors(None, None, proc_t(cb), 0)
        found.sort(key=lambda m: (not m["primary"], m["x"], m["y"]))
        for i, m in enumerate(found, 1):
            m["index"] = i
            m["label"] = f"Monitor {i}{' (main)' if m['primary'] else ''}: {m['w']}x{m['h']}"
        return found
    except Exception:
        return []


def _windows_of(pids: set[int] | None) -> list[dict]:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    out: list[dict] = []
    proc_t = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if (pids is None or pid.value in pids) and user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append({"hwnd": hwnd, "title": buf.value, "x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top})
        return 1
    user32.EnumWindows(proc_t(cb), 0)
    return out


def _family(pid: int) -> set[int]:
    pids = {pid}
    try:
        import psutil
        pids.update(c.pid for c in psutil.Process(pid).children(recursive=True))
    except Exception:
        pass
    return pids


def _apply(hwnd, win: dict, mon: dict | None, mode: str, has_flag: bool) -> None:
    import ctypes
    user32 = ctypes.windll.user32
    todo = plan((win["x"], win["y"], win["w"], win["h"]), mon, mode, has_flag)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)                      # SW_RESTORE
    if todo["borderless"]:
        GWL_STYLE, WS_CAPTION, WS_THICKFRAME = -16, 0x00C00000, 0x00040000
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~(WS_CAPTION | WS_THICKFRAME))
    if todo["move"]:
        x, y, w, h = todo["move"]
        user32.SetWindowPos(hwnd, None, x, y, w, h, 0x0004 | 0x0020 | 0x0040)   # NOZORDER | FRAMECHANGED | SHOWWINDOW
    _to_front(hwnd)


def _to_front(hwnd) -> None:
    """Windows refuses to let a background program steal focus; attaching to the current foreground thread allows it."""
    import ctypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    fore = user32.GetForegroundWindow()
    me = kernel32.GetCurrentThreadId()
    there = user32.GetWindowThreadProcessId(fore, None) if fore else 0
    attached = bool(there and there != me and user32.AttachThreadInput(me, there, True))
    try:
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)    # TOPMOST for a moment, so it lands in front
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)    # then back to normal
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, there, False)


def arrange(pid: int, monitor: dict | None, mode: str, has_flag: bool, wait: float = 30.0) -> None:
    """Wait for the game's window, then bring it forward and place it. Re-checks twice because many emulators open a small
    start-up window first and the real one a moment later. Never raises."""
    if sys.platform != "win32":
        return
    try:
        deadline = time.time() + wait
        done_at: list[float] = []
        seen = None
        while time.time() < deadline:
            win = pick_window(_windows_of(_family(pid)))
            if win and (seen is None or win["hwnd"] != seen):
                seen = win["hwnd"]
                _apply(win["hwnd"], win, monitor, mode, has_flag)
                done_at = [time.time() + 2.5, time.time() + 6.0]
            elif win and done_at and time.time() >= done_at[0]:
                done_at.pop(0)
                _apply(win["hwnd"], win, monitor, mode, has_flag)
                if not done_at:
                    return
            time.sleep(0.4)
    except Exception:
        return


def arrange_async(pid: int, monitor: dict | None, mode: str, has_flag: bool) -> None:
    if sys.platform == "win32":
        threading.Thread(target=arrange, args=(pid, monitor, mode, has_flag), daemon=True).start()


def _titled(fragment: str) -> list[dict]:
    if sys.platform != "win32":
        return []
    try:
        return [w for w in _windows_of(None) if fragment.lower() in w["title"].lower()]
    except Exception:
        return []


def overlay_open(fragment: str) -> bool:
    return bool(_titled(fragment))


def close_titled(fragment: str) -> bool:
    """Politely close every window whose title contains the text (the same as pressing its X)."""
    wins = _titled(fragment)
    if wins and sys.platform == "win32":
        import ctypes
        for w in wins:
            ctypes.windll.user32.PostMessageW(w["hwnd"], 0x0010, 0, 0)         # WM_CLOSE
    return bool(wins)


def pin_titled(fragment: str, mon: dict | None, wait: float = 12.0, margin: int = 24) -> None:
    """Wait for the overlay window, put it in the top-right corner of the monitor and keep it above full-screen games."""
    def run() -> None:
        import ctypes
        deadline = time.time() + wait
        while time.time() < deadline:
            wins = _titled(fragment)
            if wins:
                w = wins[0]
                user32 = ctypes.windll.user32
                x, y = w["x"], w["y"]
                if mon:
                    x, y = mon["x"] + mon["w"] - w["w"] - margin, mon["y"] + margin
                user32.SetWindowPos(w["hwnd"], -1, x, y, 0, 0, 0x0001 | 0x0040)   # HWND_TOPMOST, keep size, show
                _to_front(w["hwnd"])
                user32.SetWindowPos(w["hwnd"], -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)   # stay on top
                return
            time.sleep(0.3)
    if sys.platform == "win32":
        threading.Thread(target=run, daemon=True).start()
