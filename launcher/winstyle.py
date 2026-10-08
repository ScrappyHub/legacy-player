"""Tints the app window's title bar to match the current theme (Windows 11), so it blends into the app like Steam or Discord.

The window itself is the browser's app window, so we cannot remove its buttons, but Windows lets us set the title bar's colour,
text colour, border and corners. On other systems, and on Windows 10 (which ignores the colours), this quietly does nothing.
"""
from __future__ import annotations

import re
import sys

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def parse_hex(value: str) -> tuple[int, int, int] | None:
    m = _HEX.match(str(value or "").strip())
    if not m:
        return None
    n = m.group(1)
    return int(n[0:2], 16), int(n[2:4], 16), int(n[4:6], 16)


def colorref(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return (b << 16) | (g << 8) | r      # Windows wants 0x00BBGGRR


def is_dark(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 128


def attributes_for(bg: str, fg: str) -> list[tuple[int, int]] | None:
    """The (attribute, value) pairs to set, or None when the colours are not valid."""
    back, text = parse_hex(bg), parse_hex(fg)
    if back is None or text is None:
        return None
    return [(DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if is_dark(back) else 0), (DWMWA_WINDOW_CORNER_PREFERENCE, 2),
            (DWMWA_CAPTION_COLOR, colorref(back)), (DWMWA_BORDER_COLOR, colorref(back)), (DWMWA_TEXT_COLOR, colorref(text))]


def _find_windows() -> list[int]:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found: list[int] = []
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "Chrome_WidgetWin_1":
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        if title.startswith("Legacy Player") and not title.endswith("overlay"):
            found.append(int(hwnd))
        return True
    user32.EnumWindows(proc_type(visit), 0)
    return found


def apply(bg: str, fg: str, windows=None, setter=None) -> int:
    """Colour every Legacy Player window's title bar. Returns how many windows were touched."""
    attrs = attributes_for(bg, fg)
    if attrs is None:
        return 0
    if setter is None:
        if sys.platform != "win32":
            return 0
        import ctypes
        dwm = ctypes.windll.dwmapi

        def setter(hwnd, attr, value):
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_uint(attr), ctypes.byref(v), ctypes.sizeof(v))
    try:
        hwnds = list(windows) if windows is not None else _find_windows()
        for hwnd in hwnds:
            for attr, value in attrs:
                setter(hwnd, attr, value)
        return len(hwnds)
    except Exception:
        return 0
