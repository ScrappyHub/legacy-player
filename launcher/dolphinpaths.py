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


def add_game_folder(exe: str | Path, folder: str | Path) -> dict:
    try:
        user = find_user_dir(exe)
        if user is None:
            return {"added": False, "why": "Dolphin has not made its settings folder yet."}
        target = user / "Config" / "Dolphin.ini"
        text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines()
        start = next((i for i, l in enumerate(lines) if l.strip().lower() == "[general]"), None)
        if start is None:
            lines += ["[General]"]
            start = len(lines) - 1
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        existing, count_at = {}, None
        for i in range(start + 1, end):
            m = _KEY.match(lines[i])
            if m:
                existing[int(m.group(1))] = m.group(2)
                continue
            if _COUNT.match(lines[i]):
                count_at = i
        want = Path(folder).as_posix()
        if any(_norm(v) == _norm(want) for v in existing.values()):
            return {"added": False, "why": "already there"}
        index = (max(existing) + 1) if existing else 0
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        new = [f"ISOPath{index} = {want}"]
        lines[insert_at:insert_at] = new
        count_line = f"ISOPaths = {index + 1}"
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
        return {"added": True, "file": str(target)}
    except OSError as exc:
        return {"added": False, "why": f"Could not update Dolphin's settings: {exc}"}
