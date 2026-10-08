"""Add the folder a game lives in to Dolphin's game list paths, so NetPlay can find the game.

Dolphin keeps these in `Config/Dolphin.ini` under `[General]` as `ISOPaths = N` and `ISOPath0..N-1`. Only that
section's two kinds of line are touched; everything else in the file is kept byte for byte. The first time, the file
you had is copied to `Dolphin.ini.legacy-player-backup`. Never raises: if anything is wrong Dolphin keeps its own
settings and the on-screen steps still tell the player how to add the folder by hand.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .dolphinpads import find_user_dir

BACKUP = "Dolphin.ini.legacy-player-backup"
_KEY = re.compile(r"^\s*ISOPath(\d+)\s*=\s*(.*?)\s*$", re.I)
_COUNT = re.compile(r"^\s*ISOPaths\s*=\s*(\d+)\s*$", re.I)


def _norm(p: str) -> str:
    return p.strip().strip('"').replace("\\", "/").rstrip("/").lower()


def add_game_folders(exe: str | Path, folders: list, *, recursive: bool = False) -> dict:
    """Add each folder not already listed. The folders are the exact ones the games are in, so Dolphin's own "Search Subfolders"
    choice is left alone unless `recursive` is asked for."""
    try:
        user = find_user_dir(exe)
        if user is None:
            return {"added": [], "already": 0, "why": "Dolphin has not made its settings folder yet. Open Dolphin once, close it, then try again."}
        target = user / "Config" / "Dolphin.ini"
        text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines()
        start = next((i for i, l in enumerate(lines) if l.strip().lower() == "[general]"), None)
        if start is None:
            lines += ["[General]"]
            start = len(lines) - 1
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        existing, count_at, rec_at = {}, None, None
        for i in range(start + 1, end):
            m = _KEY.match(lines[i])
            if m:
                existing[int(m.group(1))] = m.group(2)
            elif _COUNT.match(lines[i]):
                count_at = i
            elif lines[i].strip().lower().startswith("recursiveisopaths"):
                rec_at = i
        have = {_norm(v) for v in existing.values()}
        added, already, index = [], 0, (max(existing) + 1) if existing else 0
        new = []
        for f in folders:
            want = Path(f).as_posix()
            if _norm(want) in have:
                already += 1
                continue
            have.add(_norm(want))
            new.append(f"ISOPath{index} = {want}")
            added.append(want)
            index += 1
        changed = bool(new)
        if recursive and (rec_at is None or "true" not in lines[rec_at].lower()):
            changed = True
            if rec_at is None:
                new.append("RecursiveISOPaths = True")
            else:
                lines[rec_at] = "RecursiveISOPaths = True"
        if not changed:
            return {"added": [], "already": already}
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines[insert_at:insert_at] = new
        if added:
            count_line = f"ISOPaths = {index}"
            if count_at is not None:
                lines[count_at] = count_line
            else:
                lines.insert(start + 1, count_line)
        backup = target.with_name(BACKUP)
        if target.exists() and not backup.exists():
            backup.write_text(text, encoding="utf-8", newline="")
        tmp = target.with_suffix(".ini.lp-tmp")
        tmp.write_text(nl.join(lines) + nl, encoding="utf-8", newline="")
        os.replace(tmp, target)
        return {"added": added, "already": already, "file": str(target)}
    except OSError as exc:
        return {"added": [], "already": 0, "why": f"Could not update Dolphin's settings: {exc}"}


def add_game_folder(exe: str | Path, folder: str | Path) -> dict:
    out = add_game_folders(exe, [folder])
    return {"added": bool(out["added"]), **{k: v for k, v in out.items() if k in {"file", "why"}}}


def missing_folders(exe: str | Path, folders: list) -> dict:
    """Read only. Which of these folders Dolphin's game list does not have yet. `known` is False when its settings can't be found."""
    try:
        user = find_user_dir(exe)
        if user is None:
            return {"known": False, "missing": []}
        target = user / "Config" / "Dolphin.ini"
        text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        have = {_norm(m.group(2)) for l in text.splitlines() if (m := _KEY.match(l))}
        return {"known": True, "missing": [str(f) for f in folders if _norm(Path(f).as_posix()) not in have]}
    except OSError:
        return {"known": False, "missing": []}
