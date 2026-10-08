"""Scan this computer for emulator programs by file name. Read-only: it lists folders and looks at
names, never opens, copies, changes or runs anything. It only starts when the user presses the button."""
from __future__ import annotations

import os
import string
import sys
import threading
import time
from pathlib import Path

SKIP = {"windows", "$recycle.bin", "system volume information", "node_modules", ".git", "__pycache__",
        "winsxs", "programdata\\microsoft", "recovery", "config.msi", "$windows.~bt", "$windows.~ws",
        "proc", "sys", "dev", "run", "snap", "boot"}


def standard_roots(environ=None, platform: str | None = None) -> list[tuple[Path, int]]:
    """(folder, depth) pairs worth looking in first: where installers and downloads put emulators."""
    env = environ if environ is not None else os.environ
    platform = platform or sys.platform
    home = Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())
    out: list[tuple[Path, int]] = []
    if platform == "win32":
        for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            if env.get(key):
                out.append((Path(env[key]), 3))
        if env.get("LOCALAPPDATA"):
            out += [(Path(env["LOCALAPPDATA"]) / "Programs", 3), (Path(env["LOCALAPPDATA"]), 2)]
        if env.get("APPDATA"):
            out.append((Path(env["APPDATA"]), 2))
        for name in ("Downloads", "Desktop", "Documents", "Games", "Emulators"):
            out.append((home / name, 5))
        for letter in string.ascii_uppercase:           # every drive: the top few levels
            drive = Path(f"{letter}:\\")
            if drive.exists():
                for name in ("Downloads", "Games", "Emulators", "Emulator set ups", "Emulation"):
                    out.append((drive / name, 6))       # people keep emulators in their own folders on other drives
                out.append((drive, 4))
    else:
        out += [(Path("/usr/bin"), 1), (Path("/usr/local/bin"), 1), (Path("/opt"), 3), (home / "Applications", 3),
                (Path("/Applications"), 2), (home / "Downloads", 4), (home / "Games", 4), (home, 2)]
    seen: set[str] = set()
    unique = []
    for folder, depth in out:
        key = str(folder).lower()
        if key not in seen:
            seen.add(key)
            unique.append((folder, depth))
    return unique


def registry_locations() -> list[Path]:
    """Install folders that Windows knows about (Uninstall and App Paths keys). Empty elsewhere."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []
    found: list[Path] = []
    spots = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
    for hive, sub in spots:
        try:
            with winreg.OpenKey(hive, sub) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, i)) as app:
                            loc, _ = winreg.QueryValueEx(app, "InstallLocation")
                            if loc and Path(str(loc).strip('"')).is_dir():
                                found.append(Path(str(loc).strip('"')))
                    except OSError:
                        continue
        except OSError:
            continue
    return found


def scan(roots: list[tuple[Path, int]], wanted: dict[str, list[str]], *, seconds: float = 90.0, max_dirs: int = 120000,
         stop: threading.Event | None = None, progress=None, matcher=None, archive_matcher=None,
         archives: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """Look for any file whose name matches an emulator's program names. Returns {emulator id: [paths]}.
    With archive_matcher, downloaded-but-not-extracted packages are collected into `archives`."""
    names = {n.lower(): eid for eid, exes in wanted.items() for n in exes}
    matcher = matcher or (lambda f: names.get(f.lower()))
    hits: dict[str, list[str]] = {}
    deadline = time.time() + seconds
    visited = 0
    seen_dirs: set[str] = set()
    for root, depth in roots:
        if not root.is_dir():
            continue
        base = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            visited += 1
            if (stop and stop.is_set()) or time.time() > deadline or visited > max_dirs:
                return hits
            here = Path(dirpath)
            if str(here).lower() in seen_dirs:
                dirnames[:] = []
                continue
            seen_dirs.add(str(here).lower())
            if len(here.parts) - base >= depth:
                dirnames[:] = []
            else:
                dirnames[:] = [d for d in dirnames if d.lower() not in SKIP and not d.startswith("$")]
            for f in filenames:
                eid = matcher(f)
                if eid:
                    full = str(here / f)
                    if full not in hits.setdefault(eid, []):
                        hits[eid].append(full)
                elif archive_matcher is not None and archives is not None:
                    aid = archive_matcher(f)
                    if aid and str(here / f) not in archives.setdefault(aid, []):
                        archives[aid].append(str(here / f))
            if progress and visited % 200 == 0:
                progress(str(here), visited)
    return hits


class PcScan:
    """Runs one scan at a time in the background so the page stays responsive."""

    def __init__(self, wanted: dict[str, list[str]], extra_roots=lambda: [], matcher=None, archive_matcher=None, after=None) -> None:
        self.wanted, self.extra_roots = wanted, extra_roots
        self.after = after                  # called with (roots, stop, progress) once the program search is done; returns a dict
        self.extra: dict = {}
        self.matcher, self.archive_matcher = matcher, archive_matcher
        self.archives: dict[str, list[str]] = {}
        self.state, self.where, self.visited, self.found = "idle", "", 0, {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.finished_at = 0.0

    def start(self) -> dict:
        if self.state == "running":
            return self.view()
        self._stop.clear()
        self.state, self.found, self.visited, self.where = "running", {}, 0, ""
        self.archives, self.extra = {}, {}

        def work() -> None:
            try:
                roots = [(p, 3) for p in self.extra_roots()] + standard_roots() + [(p, 2) for p in registry_locations()]
                self.found = scan(roots, self.wanted, stop=self._stop, progress=self._progress, matcher=self.matcher,
                                  archive_matcher=self.archive_matcher, archives=self.archives)
                if self.after is not None and not self._stop.is_set():
                    try:
                        self.extra = self.after(roots, self._stop, self._progress) or {}
                    except Exception as exc:          # looking for games must never spoil the program search
                        self.extra = {"games_error": str(exc)[:200]}
                self.state = "stopped" if self._stop.is_set() else "done"
            except Exception as exc:     # never leave the page waiting forever
                self.state, self.where = "error", str(exc)[:200]
            self.finished_at = time.time()

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        return self.view()

    def _progress(self, where: str, visited: int) -> None:
        self.where, self.visited = where, visited

    def cancel(self) -> dict:
        self._stop.set()
        return self.view()

    def view(self) -> dict:
        return {"state": self.state, "where": self.where, "visited": self.visited, "found": self.found, "archives": self.archives, **self.extra}
