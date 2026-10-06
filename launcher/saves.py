"""Save-file safety net: find a game's save files in the emulator's save folder and
keep timestamped backups. Restore backs up the current files first."""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

SAVE_EXTENSIONS = {".sav", ".srm", ".state", ".sta", ".ss0", ".ss1", ".ss2", ".fcs", ".dsv", ".eep", ".fla", ".mpk", ".mcr", ".mc", ".mcd", ".ps2", ".gci", ".sav0"}


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80]


def find_save_files(save_dir: Path, game_stem: str) -> list[Path]:
    if not save_dir.is_dir():
        return []
    stem = game_stem.lower()
    found = []
    for path in save_dir.rglob("*"):
        if len(path.relative_to(save_dir).parts) > 4 or not path.is_file():
            continue
        if path.suffix.lower() in SAVE_EXTENSIONS or ".state" in path.name.lower():
            if path.stem.lower().startswith(stem) or stem in path.name.lower():
                found.append(path)
    return sorted(found)


def backup_dir(data_dir: Path, console: str, compat_id: str) -> Path:
    return Path(data_dir) / "save_backups" / _safe(console) / _safe(compat_id)


def create_backup(data_dir: Path, console: str, compat_id: str, files: list[Path], save_dir: Path) -> dict:
    if not files:
        raise ValueError("no save files found for this game")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = backup_dir(data_dir, console, compat_id) / stamp
    suffix = 0
    while target.exists():
        suffix += 1
        target = backup_dir(data_dir, console, compat_id) / f"{stamp}-{suffix}"
    for file in files:
        destination = target / file.relative_to(save_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, destination)
    return {"backup": target.name, "files": len(files)}


def list_backups(data_dir: Path, console: str, compat_id: str) -> list[dict]:
    root = backup_dir(data_dir, console, compat_id)
    if not root.is_dir():
        return []
    return [
        {"backup": d.name, "files": sum(1 for f in d.rglob("*") if f.is_file())}
        for d in sorted(root.iterdir(), reverse=True) if d.is_dir()
    ]


def restore_backup(data_dir: Path, console: str, compat_id: str, backup: str, save_dir: Path, game_stem: str) -> dict:
    root = backup_dir(data_dir, console, compat_id)
    source = (root / backup).resolve()
    if source.parent != root.resolve() or not source.is_dir():
        raise ValueError("unknown backup")
    current = find_save_files(save_dir, game_stem)
    safety = create_backup(data_dir, console, compat_id, current, save_dir)["backup"] if current else None
    restored = 0
    for file in source.rglob("*"):
        if file.is_file():
            destination = save_dir / file.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
            restored += 1
    return {"restored": restored, "previous_saves_backed_up_as": safety}
