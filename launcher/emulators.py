"""Emulator discovery and launching. Games are launched with an argument list
(never through a shell), only from a game id already in the library."""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

# name, executable candidates, argument template. Defaults are the common documented
# command lines; they are marked unverified until proven on the user's machine.
EMULATORS: dict[str, dict] = {
    "dolphin": {"name": "Dolphin", "exes": ["Dolphin.exe", "dolphin-emu"], "args": ["-b", "-e", "{rom}"], "fullscreen": ["-C","Dolphin.Display.Fullscreen=True"]},
    "pcsx2": {"name": "PCSX2", "exes": ["pcsx2-qt.exe", "pcsx2-qt", "pcsx2.exe", "PCSX2"], "args": ["-batch", "--", "{rom}"], "fullscreen": ["-fullscreen"]},
    "mgba": {"name": "mGBA", "exes": ["mGBA.exe", "mgba-qt", "mgba"], "args": ["{rom}"], "fullscreen": ["-f"]},
    "duckstation": {"name": "DuckStation", "exes": ["duckstation-qt-x64-ReleaseLTCG.exe", "duckstation-qt"], "args": ["-batch", "--", "{rom}"], "fullscreen": ["-fullscreen"]},
    "mesen": {"name": "Mesen", "exes": ["Mesen.exe", "mesen"], "args": ["{rom}"], "fullscreen": ["--fullscreen"]},
    "bsnes": {"name": "bsnes", "exes": ["bsnes.exe", "bsnes"], "args": ["{rom}"], "fullscreen": ["--fullscreen"]},
    "snes9x": {"name": "Snes9x", "exes": ["snes9x-x64.exe", "snes9x"], "args": ["{rom}"]},
    "mupen": {"name": "Mupen64Plus", "exes": ["mupen64plus-gui.exe", "mupen64plus"], "args": ["{rom}"], "fullscreen": ["--fullscreen"]},
    "melonds": {"name": "melonDS", "exes": ["melonDS.exe", "melonDS"], "args": ["{rom}"], "fullscreen": ["-f"]},
    "ppsspp": {"name": "PPSSPP", "exes": ["PPSSPPWindows64.exe", "PPSSPPSDL"], "args": ["{rom}"], "fullscreen": ["--fullscreen"]},
    "azahar": {"name": "Azahar", "exes": ["azahar.exe", "azahar"], "args": ["{rom}"], "fullscreen": ["-f"]},
    "citra": {"name": "Citra", "exes": ["citra-qt.exe", "citra-qt"], "args": ["{rom}"], "fullscreen": ["-f"]},
    "xemu": {"name": "xemu", "exes": ["xemu.exe", "xemu"], "args": ["-dvd_path", "{rom}"], "fullscreen": ["-full-screen"]},
    "xenia": {"name": "Xenia", "exes": ["xenia.exe", "xenia_canary.exe"], "args": ["{rom}"], "fullscreen": ["--fullscreen=true"]},
    "rpcs3": {"name": "RPCS3", "exes": ["rpcs3.exe", "rpcs3"], "args": ["{rom}"]},
    "retroarch": {"name": "RetroArch", "exes": ["retroarch.exe", "retroarch"], "args": ["{rom}"]},
}


# Program names differ between releases (snes9x.exe, snes9x-x64.exe, xemu.exe ...), so match by prefix as well.
_PREFIX = {"dolphin": "dolphin", "pcsx2": "pcsx2", "mgba": "mgba", "duckstation": "duckstation", "mesen": "mesen", "bsnes": "bsnes",
           "snes9x": "snes9x", "mupen": "mupen64plus", "melonds": "melonds", "ppsspp": "ppsspp", "azahar": "azahar",
           "citra": "citra-qt", "xemu": "xemu", "xenia": "xenia", "rpcs3": "rpcs3", "retroarch": "retroarch"}
_NOT_THE_EMULATOR = re.compile(r"(uninst|unins\d|updater|setup|installer|tool|-room|-sdl|crashpad|helper|dspt)", re.I)
_EXE = {eid: re.compile(r"^" + re.escape(pre) + r"[\w.\-]*\.exe$", re.I) for eid, pre in _PREFIX.items()}
_ARCHIVE = {eid: re.compile(r"^" + re.escape(pre) + r"[\w.\-]*\.(zip|7z|rar)$", re.I) for eid, pre in _PREFIX.items()}


def program_for(filename: str) -> str | None:
    """Which emulator a file name belongs to, or None. Exact names win; otherwise a known prefix with .exe."""
    low = filename.lower()
    for eid, spec in EMULATORS.items():
        if low in {e.lower() for e in spec["exes"]}:
            return eid
    if not low.endswith(".exe") or _NOT_THE_EMULATOR.search(low):
        return None
    for eid, rx in _EXE.items():
        if rx.match(filename):
            return eid
    return None


def archive_for(filename: str) -> str | None:
    """A downloaded but not yet extracted emulator (zip/7z/rar), by name."""
    for eid, rx in _ARCHIVE.items():
        if rx.match(filename):
            return eid
    return None


def find_emulators(search_roots: list[Path], configured: dict[str, str]) -> dict[str, dict]:
    result = {}
    for emulator_id, spec in EMULATORS.items():
        path = configured.get(emulator_id)
        source = "you set this"
        if path and not Path(path).is_file():
            path = None
        if not path:
            source = "found automatically"
            for root in search_roots:
                for dirpath, dirnames, filenames in os.walk(root):
                    if len(Path(dirpath).relative_to(root).parts) >= 4:
                        dirnames[:] = []  # emulators live near the top; keep the search quick
                    hit = next((f for f in filenames if program_for(f) == emulator_id), None)
                    if hit:
                        path = str(Path(dirpath) / hit)
                        break
                if path:
                    break
            if not path:
                for exe in spec["exes"]:
                    found = shutil.which(exe)
                    if found:
                        path = found
                        break
        result[emulator_id] = {"name": spec["name"], "path": path, "source": source if path else None}
    return result


# Which start-up full-screen flags come from the emulator's own documentation, and which are best guesses that the
# player should confirm once. The page says so instead of promising.
FULLSCREEN_DOCUMENTED = {"dolphin", "pcsx2", "duckstation", "mgba", "azahar", "citra", "ppsspp", "xenia"}


def fullscreen_status(emulator_id: str) -> str:
    """'documented', 'unconfirmed' (we pass a flag but have not confirmed it for every version), or 'none'."""
    spec = EMULATORS.get(emulator_id, {})
    if not spec.get("fullscreen"):
        return "none"
    return "documented" if emulator_id in FULLSCREEN_DOCUMENTED else "unconfirmed"


def build_command(emulator_id: str, exe: str, rom_path: str) -> list[str]:
    spec = EMULATORS[emulator_id]
    return [exe] + [arg.replace("{rom}", rom_path) for arg in spec["args"]]


def video_args(emulator_id: str, fullscreen: bool | None) -> list[str]:
    """Command-line flags that make this emulator start full screen, when it has one. Only added when asked for."""
    return list(EMULATORS[emulator_id].get("fullscreen", [])) if fullscreen else []


def launch(emulator_id: str, exe: str, rom_path: str, extra_args: list[str] | None = None) -> int:
    if not Path(rom_path).is_file():
        raise FileNotFoundError("the game file is missing; rescan your library")
    command = build_command(emulator_id, exe, rom_path)
    command[1:1] = extra_args or []
    process = subprocess.Popen(
        command,
        cwd=str(Path(exe).parent),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return process.pid


_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)      # helper programs must not flash a console window


def close_pid(pid: int, grace: float = 8.0) -> None:
    """Ask a game to close the way the X button does (WM_CLOSE on Windows, SIGTERM elsewhere),
    wait a little for it to write saves, then stop it for good if it is still there."""
    import time
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True, timeout=10, creationflags=_NOWIN)   # no /F: polite
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        return
    deadline = time.time() + grace
    while time.time() < deadline:
        if not _alive(pid):
            return
        time.sleep(0.25)
    stop_pid(pid)


def _alive(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=10, creationflags=_NOWIN).stdout
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def stop_pid(pid: int) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10, creationflags=_NOWIN)
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass


def launch_command(command: list[str]) -> int:
    """Start an already-built argument list (no shell). Used by netplay launches."""
    process = subprocess.Popen(
        command, cwd=str(Path(command[0]).parent),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return process.pid
