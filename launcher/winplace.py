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

_DPI_DONE = False
_U32_LOCK = threading.RLock()
_ORIG: dict[int, tuple[int, tuple[int, int, int, int]]] = {}    # window -> (style, rect) from before we made it borderless


def _user32():
    """user32 with the handle types declared (so 64-bit window handles are never cut to 32 bits), and the process made
    DPI-aware once (so monitor sizes and window positions are real pixels on scaled screens)."""
    import ctypes
    from ctypes import wintypes
    global _DPI_DONE
    u = ctypes.windll.user32
    with _U32_LOCK:                                   # two threads must not use it half prepared
        if _DPI_DONE:
            return u
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)                  # per-monitor
        except Exception:
            try:
                u.SetProcessDPIAware()
            except Exception:
                pass
        try:
            H, B, I = wintypes.HWND, wintypes.BOOL, ctypes.c_int
            u.GetForegroundWindow.restype = H
            u.SetWindowPos.argtypes = [H, H, I, I, I, I, wintypes.UINT]
            u.SetWindowPos.restype = B
            u.BringWindowToTop.argtypes = [H]
            u.SetForegroundWindow.argtypes = [H]
            u.IsIconic.argtypes = [H]
            u.ShowWindow.argtypes = [H, I]
            u.GetWindowLongW.argtypes = [H, I]
            u.SetWindowLongW.argtypes = [H, I, ctypes.c_long]
            u.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
            u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
            u.IsWindowVisible.argtypes = [H]
            u.GetWindowTextLengthW.argtypes = [H]
            u.GetWindowTextW.argtypes = [H, wintypes.LPWSTR, I]
            u.GetClassNameW.argtypes = [H, wintypes.LPWSTR, I]
            u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, B]
            u.PostMessageW.argtypes = [H, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        except Exception:
            pass
        _DPI_DONE = True
    return u


def list_monitors() -> list[dict]:
    """[{'index', 'name', 'x', 'y', 'w', 'h', 'primary', 'label'}], primary first. Empty when not on Windows."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes
        _user32()                                   # makes the process DPI-aware before asking for sizes

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
    user32 = _user32()
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
    from . import procs
    return procs.children(pid)


def _apply(hwnd, win: dict, mon: dict | None, mode: str, has_flag: bool) -> None:
    import ctypes
    user32 = _user32()
    todo = plan((win["x"], win["y"], win["w"], win["h"]), mon, mode, has_flag)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)                      # SW_RESTORE
    GWL_STYLE, WS_CAPTION, WS_THICKFRAME = -16, 0x00C00000, 0x00040000
    if todo["borderless"]:
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        _ORIG.setdefault(int(hwnd), (style, (win["x"], win["y"], win["w"], win["h"])))
        user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~(WS_CAPTION | WS_THICKFRAME))
    elif mode == "windowed" and int(hwnd) in _ORIG:
        # we made it borderless earlier: give back its title bar and its old size, then place it on the monitor
        style, (ox, oy, ow, oh) = _ORIG.pop(int(hwnd))
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        if mon:
            back = plan((ox, oy, ow, oh), mon, "windowed", has_flag)
            ox, oy, ow, oh = back["move"] or (ox, oy, ow, oh)
            if ow >= mon["w"] and oh >= mon["h"]:                        # it was already as big as the screen: make it a window
                ow, oh = int(mon["w"] * 0.8), int(mon["h"] * 0.8)
                ox, oy = mon["x"] + (mon["w"] - ow) // 2, mon["y"] + (mon["h"] - oh) // 2
        todo = {"move": (ox, oy, ow, oh), "borderless": False}
    if todo["move"]:
        x, y, w, h = todo["move"]
        user32.SetWindowPos(hwnd, None, x, y, w, h, 0x0004 | 0x0020 | 0x0040)   # NOZORDER | FRAMECHANGED | SHOWWINDOW
    _to_front(hwnd)


def _to_front(hwnd) -> None:
    """Windows refuses to let a background program steal focus; attaching to the current foreground thread allows it."""
    import ctypes
    user32, kernel32 = _user32(), ctypes.windll.kernel32
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


def arrange(pid: int, monitor: dict | None, mode: str, has_flag: bool, wait: float = 30.0, explicit: bool = False) -> None:
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
                _apply(win["hwnd"], win, monitor or (_monitor_of(win) if explicit else None), mode, has_flag)
                done_at = [time.time() + 2.5, time.time() + 6.0] if not explicit else [time.time() + 0.5]
            elif win and done_at and time.time() >= done_at[0]:
                done_at.pop(0)
                _apply(win["hwnd"], win, monitor or (_monitor_of(win) if explicit else None), mode, has_flag)
                if not done_at:
                    return
            time.sleep(0.4)
    except Exception:
        return


def _monitor_of(win: dict) -> dict | None:
    """The monitor a window is mostly on (the primary one if it is on none)."""
    mons = list_monitors()
    cx, cy = win["x"] + win["w"] // 2, win["y"] + win["h"] // 2
    for m in mons:
        if m["x"] <= cx < m["x"] + m["w"] and m["y"] <= cy < m["y"] + m["h"]:
            return m
    return next((m for m in mons if m.get("primary")), mons[0] if mons else None)


_ARRANGE_LOCK = threading.Lock()


def arrange_async(pid: int, monitor: dict | None, mode: str, has_flag: bool, explicit: bool = False) -> None:
    if sys.platform == "win32":
        def run() -> None:
            with _ARRANGE_LOCK:                      # two quick clicks must not fight over the same window
                arrange(pid, monitor, mode, has_flag, explicit=explicit)
        threading.Thread(target=run, daemon=True).start()


APP_TITLE_MARK = "Legacy Player \u2014"        # the app window: see is_app_title (the overlay's title never matches)
APP_NAME = "Legacy Player"
_APP_SEPARATORS = (" \u2014", " \u2013", " - ")     # em dash (what the page uses), en dash, and the " - Browser name" a tab gets
_BROWSER_CLASSES = {"Chrome_WidgetWin_1", "MozillaWindowClass"}     # Edge, Chrome, Brave, Firefox


def is_app_title(title: str) -> bool:
    """Is this the title of a Legacy Player app window (or browser tab)?

    The page's titles all start with "Legacy Player \u2014 " ("Legacy Player \u2014 Home", "Legacy Player \u2014 restarting",
    "Legacy Player \u2014 closed"); older pages used just "Legacy Player". A browser tab adds " - Microsoft Edge" and so on.
    The overlay ("Legacy Player overlay") never matches."""
    t = (title or "").strip()
    if t == APP_NAME:
        return True
    if not t.startswith(APP_NAME):
        return False
    rest = t[len(APP_NAME):]
    return any(rest.startswith(sep) for sep in _APP_SEPARATORS)


_BROWSER_NAMES = ("Google Chrome", "Microsoft Edge", "Mozilla Firefox", "Firefox", "Brave", "Chromium", "Opera", "Vivaldi")


def is_browser_tab_title(title: str) -> bool:
    """A normal browser window shows the active tab's title plus the browser's name ("… - Google Chrome"). Closing such
    a window would close the player's other tabs too, so the app only ever closes its own app-style window."""
    t = (title or "").replace("​", "").strip()
    return any(t.endswith(name) for name in _BROWSER_NAMES)


def _class_of(hwnd) -> str:
    import ctypes
    buf = ctypes.create_unicode_buffer(128)
    _user32().GetClassNameW(hwnd, buf, 128)
    return buf.value


def _titled(fragment: str) -> list[dict]:
    """Visible windows whose title contains the text. The app's own mark (APP_TITLE_MARK) is special: it finds the app
    window by is_app_title, and only browser windows, never another program that happens to say "Legacy Player"."""
    if sys.platform != "win32":
        return []
    try:
        if fragment == APP_TITLE_MARK:
            return [w for w in _windows_of(None) if is_app_title(w["title"]) and _class_of(w["hwnd"]) in _BROWSER_CLASSES]
        return [w for w in _windows_of(None) if fragment.lower() in w["title"].lower()]
    except Exception:
        return []


def overlay_open(fragment: str) -> bool:
    return bool(_titled(fragment))


def window_exists(fragment: str = APP_TITLE_MARK) -> bool:
    return bool(_titled(fragment))


def minimize_titled(fragment: str) -> bool:
    """Minimise the window whose title contains the text. False when there is none."""
    wins = _titled(fragment)
    for w in wins:
        _user32().ShowWindow(w["hwnd"], 6)              # SW_MINIMIZE
    return bool(wins)


def restore_titled(fragment: str) -> bool:
    """Bring a minimised window back and in front (the same as focus_titled)."""
    return focus_titled(fragment)


def focus_titled(fragment: str) -> bool:
    """Bring a window whose title contains the text to the front (restoring it if minimised). False when there is none."""
    wins = _titled(fragment)
    if not wins:
        return False
    user32 = _user32()
    hwnd = wins[0]["hwnd"]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)                      # SW_RESTORE
    _to_front(hwnd)
    return True


def close_titled(fragment: str) -> bool:
    """Politely close every window whose title contains the text (the same as pressing its X)."""
    wins = _titled(fragment)
    if fragment == APP_TITLE_MARK:                     # never a whole browser window with the player's other tabs in it
        wins = [w for w in wins if not is_browser_tab_title(w["title"])]
    if wins and sys.platform == "win32":
        import ctypes
        for w in wins:
            ctypes.windll.user32.PostMessageW(w["hwnd"], 0x0010, 0, 0)         # WM_CLOSE
    return bool(wins)


def _make_overlay_like(hwnd) -> None:
    """Make a browser app window look like an in-game overlay: no title bar or sizing border, no taskbar button,
    rounded corners where Windows supports them. Everything is best effort; the window still works if any step fails."""
    import ctypes
    user32 = _user32()
    GWL_STYLE, GWL_EXSTYLE = -16, -20
    WS_CAPTION, WS_THICKFRAME, WS_SYSMENU, WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00C00000, 0x00040000, 0x00080000, 0x00020000, 0x00010000
    WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000080, 0x00040000
    try:
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX))
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
    except Exception:
        pass
    try:
        pref = ctypes.c_int(2)                                       # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


def pin_titled(fragment: str, mon: dict | None, wait: float = 12.0, margin: int = 24) -> None:
    """Wait for the overlay window, put it in the top-right corner of the monitor and keep it above full-screen games."""
    def run() -> None:
        import ctypes
        deadline = time.time() + wait
        while time.time() < deadline:
            wins = _titled(fragment)
            if wins:
                w = wins[0]
                user32 = _user32()
                x, y = w["x"], w["y"]
                if mon:
                    x, y = mon["x"] + mon["w"] - w["w"] - margin, mon["y"] + margin
                _make_overlay_like(w["hwnd"])
                user32.SetWindowPos(w["hwnd"], -1, x, y, 0, 0, 0x0001 | 0x0040 | 0x0020)   # HWND_TOPMOST, keep size, show, redo the frame
                _to_front(w["hwnd"])
                user32.SetWindowPos(w["hwnd"], -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)   # stay on top
                return
            time.sleep(0.3)
    if sys.platform == "win32":
        threading.Thread(target=run, daemon=True).start()
