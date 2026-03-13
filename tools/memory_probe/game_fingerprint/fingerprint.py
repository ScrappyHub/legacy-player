import ctypes
import re
from ctypes import wintypes


user32 = ctypes.WinDLL("user32", use_last_error=True)

EnumWindows = user32.EnumWindows
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextW = user32.GetWindowTextW
IsWindowVisible = user32.IsWindowVisible

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
EnumWindows.restype = wintypes.BOOL

GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
GetWindowThreadProcessId.restype = wintypes.DWORD

GetWindowTextLengthW.argtypes = [wintypes.HWND]
GetWindowTextLengthW.restype = ctypes.c_int

GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int

IsWindowVisible.argtypes = [wintypes.HWND]
IsWindowVisible.restype = wintypes.BOOL


def _get_window_titles_for_pid(pid):
    titles = []

    @EnumWindowsProc
    def enum_proc(hwnd, lparam):
        if not IsWindowVisible(hwnd):
            return True

        proc_id = wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))

        if proc_id.value != pid:
            return True

        length = GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(hwnd, buf, length + 1)

        title = buf.value.strip()
        if title:
            titles.append(title)

        return True

    EnumWindows(enum_proc, 0)
    return titles


def _select_best_window_title(window_titles):
    if not window_titles:
        return ""

    game_id_pattern = re.compile(r"\(([A-Z0-9]{6})\)")

    for title in window_titles:
        if game_id_pattern.search(title):
            return title

    return max(window_titles, key=len)


def _extract_game_id(title):
    if not title:
        return "unknown"

    match = re.search(r"\(([A-Z0-9]{6})\)", title)
    if match:
        return match.group(1)

    return "unknown"


def _guess_region_from_game_id(game_id):
    if len(game_id) != 6:
        return "unknown"

    region_code = game_id[3]

    if region_code == "E":
        return "USA"
    if region_code == "P":
        return "EUR"
    if region_code == "J":
        return "JPN"
    if region_code == "K":
        return "KOR"

    return "unknown"


def _guess_phase_from_title(title):
    upper = title.upper()

    if "MARIO PARTY 4" not in upper:
        return "unknown"

    if "SELECT" in upper or "OPTION" in upper or "PARTY MODE" in upper:
        return "setup"

    if "MINIGAME" in upper:
        return "minigame_entry"

    if "RESULT" in upper:
        return "results"

    return "loaded"


def detect_game(proc):
    process_name = ""
    exe = ""
    cmdline = []

    try:
        process_name = proc.name() or ""
    except Exception:
        process_name = ""

    try:
        exe = proc.exe() or ""
    except Exception:
        exe = ""

    try:
        cmdline = proc.cmdline() or []
    except Exception:
        cmdline = []

    window_titles = _get_window_titles_for_pid(proc.pid)
    active_title = _select_best_window_title(window_titles)
    game_id = _extract_game_id(active_title)
    region = _guess_region_from_game_id(game_id)
    phase_hint = _guess_phase_from_title(active_title)

    return {
        "emulator": "dolphin",
        "process_name": process_name,
        "exe": exe,
        "cmdline": cmdline,
        "window_titles": window_titles,
        "active_window_title": active_title,
        "game_id": game_id,
        "region": region,
        "phase_hint": phase_hint,
    }