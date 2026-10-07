"""Emulator discovery and launching. Games are launched with an argument list
(never through a shell), only from a game id already in the library."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

# name, executable candidates, argument template. Defaults are the common documented
# command lines; they are marked unverified until proven on the user's machine.
EMULATORS: dict[str, dict] = {
    "dolphin": {"name": "Dolphin", "exes": ["Dolphin.exe", "dolphin-emu"], "args": ["-b", "-e", "{rom}"]},
    "pcsx2": {"name": "PCSX2", "exes": ["pcsx2-qt.exe", "pcsx2-qt", "pcsx2.exe", "PCSX2"], "args": ["-batch", "--", "{rom}"]},
    "mgba": {"name": "mGBA", "exes": ["mGBA.exe", "mgba-qt", "mgba"], "args": ["{rom}"]},
    "duckstation": {"name": "DuckStation", "exes": ["duckstation-qt-x64-ReleaseLTCG.exe", "duckstation-qt"], "args": ["-batch", "--", "{rom}"]},
    "mesen": {"name": "Mesen", "exes": ["Mesen.exe", "mesen"], "args": ["{rom}"]},
    "bsnes": {"name": "bsnes", "exes": ["bsnes.exe", "bsnes"], "args": ["{rom}"]},
    "snes9x": {"name": "Snes9x", "exes": ["snes9x-x64.exe", "snes9x"], "args": ["{rom}"]},
    "mupen": {"name": "Mupen64Plus", "exes": ["mupen64plus-gui.exe", "mupen64plus"], "args": ["{rom}"]},
    "melonds": {"name": "melonDS", "exes": ["melonDS.exe", "melonDS"], "args": ["{rom}"]},
    "ppsspp": {"name": "PPSSPP", "exes": ["PPSSPPWindows64.exe", "PPSSPPSDL"], "args": ["{rom}"]},
    "azahar": {"name": "Azahar", "exes": ["azahar.exe", "azahar"], "args": ["{rom}"]},
    "citra": {"name": "Citra", "exes": ["citra-qt.exe", "citra-qt"], "args": ["{rom}"]},
    "xemu": {"name": "xemu", "exes": ["xemu.exe", "xemu"], "args": ["-dvd_path", "{rom}"]},
    "xenia": {"name": "Xenia", "exes": ["xenia.exe", "xenia_canary.exe"], "args": ["{rom}"]},
    "rpcs3": {"name": "RPCS3", "exes": ["rpcs3.exe", "rpcs3"], "args": ["{rom}"]},
    "retroarch": {"name": "RetroArch", "exes": ["retroarch.exe", "retroarch"], "args": ["{rom}"]},
}


def find_emulators(search_roots: list[Path], configured: dict[str, str]) -> dict[str, dict]:
    result = {}
    for emulator_id, spec in EMULATORS.items():
        path = configured.get(emulator_id)
        source = "you set this"
        if path and not Path(path).is_file():
            path = None
        if not path:
            source = "found automatically"
            wanted = {e.lower() for e in spec["exes"]}
            for root in search_roots:
                for dirpath, dirnames, filenames in os.walk(root):
                    if len(Path(dirpath).relative_to(root).parts) >= 3:
                        dirnames[:] = []  # emulators live near the top; keep the search quick
                    hit = next((f for f in filenames if f.lower() in wanted), None)
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


def build_command(emulator_id: str, exe: str, rom_path: str) -> list[str]:
    spec = EMULATORS[emulator_id]
    return [exe] + [arg.replace("{rom}", rom_path) for arg in spec["args"]]


def launch(emulator_id: str, exe: str, rom_path: str) -> int:
    if not Path(rom_path).is_file():
        raise FileNotFoundError("the game file is missing; rescan your library")
    process = subprocess.Popen(
        build_command(emulator_id, exe, rom_path),
        cwd=str(Path(exe).parent),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return process.pid


def close_pid(pid: int, grace: float = 8.0) -> None:
    """Ask a game to close the way the X button does (WM_CLOSE on Windows, SIGTERM elsewhere),
    wait a little for it to write saves, then stop it for good if it is still there."""
    import time
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True, timeout=10)   # no /F: polite
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
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=10).stdout
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def stop_pid(pid: int) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
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
