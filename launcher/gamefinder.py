"""Find the folders that hold the player's games, so nobody has to type a path. Read-only: it lists folder and file names
and counts files by type; it never opens, copies or changes anything. It runs as part of the full scan on this computer,
which the player started and agreed to."""
from __future__ import annotations

import fnmatch
import os
import threading
import time
from collections import Counter
from pathlib import Path

from .consoles import AMBIGUOUS_EXTENSIONS, console_for_extension, console_for_folder_name
from .scanner import DEFAULT_EXCLUDES

MIN_GAMES = 3
NOT_GAMES_HERE = {".md", ".pkg", ".wad", ".img", ".rom", ".fig", ".lnx"}      # also documents, packages and other programs' files, so not evidence of a library
WIDE = {"downloads", "documents", "desktop", "users", "program files", "program files (x86)", "onedrive"}
SKIP = {"windows", "$recycle.bin", "system volume information", "node_modules", ".git", "__pycache__", "winsxs", "appdata",
        "recovery", "config.msi", "steamapps", "programdata", "proc", "sys", "dev", "run", "snap", "boot"}


def _console_of(name: str, parts: tuple[str, ...]) -> str | None:
    ext = os.path.splitext(name)[1].lower()
    if ext in NOT_GAMES_HERE:
        return None
    console = console_for_extension(ext)
    if console is not None:
        if ext in {".cso", ".zso", ".chd", ".iso", ".bin"}:           # shared types: the folder name decides when it can
            for part in reversed(parts[-3:]):
                by_folder = console_for_folder_name(part)
                if by_folder is not None:
                    return by_folder.id
        return console.id
    if ext in AMBIGUOUS_EXTENSIONS:
        for part in reversed(parts[-3:]):
            by_folder = console_for_folder_name(part)
            if by_folder is not None:
                return by_folder.id
    return None


def _excluded(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in DEFAULT_EXCLUDES)


def find(roots: list[tuple[Path, int]], emulator_exes: set[str], *, stop: threading.Event | None = None, progress=None,
         seconds: float = 60.0, max_dirs: int = 150000) -> list[dict]:
    """Walk the given (folder, depth) pairs and return [{"path", "games", "consoles"}] for the folders that make up the library."""
    direct: dict[Path, Counter] = {}
    deadline = time.time() + seconds
    visited = 0
    seen: set[str] = set()
    tops: set[Path] = set()
    for root, depth in roots:
        if not root.is_dir():
            continue
        tops.add(root)
        base = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            visited += 1
            if (stop and stop.is_set()) or time.time() > deadline or visited > max_dirs:
                return _choose(direct, tops)
            here = Path(dirpath)
            key = str(here).lower()
            if key in seen:
                dirnames[:] = []
                continue
            seen.add(key)
            if len(here.parts) - base >= depth:
                dirnames[:] = []
            else:
                dirnames[:] = [d for d in dirnames if d.lower() not in SKIP and not d.startswith("$") and not _excluded(d)]
            lowered = {f.lower() for f in filenames}
            if lowered & emulator_exes:                  # an emulator's own folder: not a library
                dirnames[:] = []
                continue
            cues = {os.path.splitext(f)[0].lower() for f in filenames if f.lower().endswith(".cue")}
            counts: Counter = Counter()
            for f in filenames:
                if f.lower().endswith(".bin") and os.path.splitext(f)[0].lower() in cues:
                    continue                                   # the .cue sheet stands for the disc
                console = _console_of(f, here.parts)
                if console:
                    counts[console] += 1
            if counts:
                direct[here] = counts
            if progress and visited % 200 == 0:
                progress(str(here), visited)
    return _choose(direct, tops)


def _is_wide(path: Path) -> bool:
    if path.parent == path:                                      # a drive root
        return True
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return path == home or path.name.lower() in WIDE


def _choose(direct: dict[Path, Counter], tops: set[Path]) -> list[dict]:
    sub: dict[Path, Counter] = {}
    for folder, counts in direct.items():
        for ancestor in (folder, *folder.parents):
            sub.setdefault(ancestor, Counter()).update(counts)
    kids: dict[Path, list[Path]] = {}
    for folder in sub:
        if folder.parent != folder:
            kids.setdefault(folder.parent, []).append(folder)
    chosen: list[Path] = []

    def visit(folder: Path) -> None:
        total = sum(sub.get(folder, Counter()).values())
        if total < MIN_GAMES:
            return
        if _is_wide(folder):
            if direct.get(folder) and sum(direct[folder].values()) >= MIN_GAMES:
                chosen.append(folder)                              # games sit right here: take the folder
                return
            for child in sorted(kids.get(folder, [])):
                visit(child)
            return
        chosen.append(folder)

    for top in sorted(tops, key=lambda p: len(p.parts)):
        if not any(top == c or c in top.parents for c in chosen):
            visit(top)
    out = []
    for folder in chosen:
        counts = sub[folder]
        out.append({"path": str(folder), "games": sum(counts.values()), "consoles": dict(counts)})
    return sorted(out, key=lambda r: -r["games"])
