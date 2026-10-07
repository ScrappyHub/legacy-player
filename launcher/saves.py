"""Save-file safety net: find a game's save files in the emulator's save folder and
keep timestamped backups. Restore backs up the current files first."""
from __future__ import annotations

import re
import os
import shutil
import time
from pathlib import Path

SAVE_EXTENSIONS = {".sav", ".srm", ".state", ".sta", ".ss0", ".ss1", ".ss2", ".fcs", ".dsv", ".eep", ".fla", ".mpk", ".mcr", ".mc", ".mcd", ".ps2", ".gci", ".sav0"}


MAX_RESTORE_BYTES = 2 * 1024 ** 3      # a save backup bigger than this is not a save backup


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


# ---- whole-library backups: one zip with every console's saves, kept wherever the user wants ----
import json as _json
import zipfile as _zipfile


def backup_all(sources: dict[str, Path], dest_root: Path, label: str = "saves") -> dict:
    """Zip every save file under each console's save folder. sources: console id -> folder."""
    dest_root = Path(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = dest_root / f"LegacyPlayer-{_safe(label)}-{stamp}.zip"
    n = 0
    while target.exists():
        n += 1
        target = dest_root / f"LegacyPlayer-{_safe(label)}-{stamp}-{n}.zip"
    files = 0
    size = 0
    manifest = {"made": time.time(), "consoles": {}}
    with _zipfile.ZipFile(target, "w", _zipfile.ZIP_DEFLATED) as z:
        for console, folder in sorted(sources.items()):
            folder = Path(folder)
            if not folder.is_dir():
                continue
            count = 0
            for f in folder.rglob("*"):
                if f.is_file():
                    z.write(f, f"{console}/{f.relative_to(folder).as_posix()}")
                    count += 1
                    size += f.stat().st_size
            if count:
                manifest["consoles"][console] = {"files": count, "folder": str(folder)}
                files += count
        z.writestr("manifest.json", _json.dumps(manifest))
    if not files:
        target.unlink()
        raise ValueError("there are no save files yet in any save folder")
    return {"name": target.name, "files": files, "bytes": target.stat().st_size, "consoles": len(manifest["consoles"])}


def list_all_backups(dest_root: Path) -> list[dict]:
    root = Path(dest_root)
    if not root.is_dir():
        return []
    out = []
    for z in sorted(root.glob("LegacyPlayer-*.zip"), reverse=True):
        try:
            with _zipfile.ZipFile(z) as zf:
                m = _json.loads(zf.read("manifest.json"))
            out.append({"name": z.name, "bytes": z.stat().st_size, "made": m.get("made") or z.stat().st_mtime,
                        "consoles": sorted(m["consoles"]), "files": sum(c["files"] for c in m["consoles"].values())})
        except (OSError, KeyError, ValueError, _zipfile.BadZipFile):
            continue
    return out


def restore_all(dest_root: Path, name: str, sources: dict[str, Path], safety_root: Path) -> dict:
    """Put a whole-library backup back. What is there now is zipped first, so restoring never costs progress."""
    root = Path(dest_root).resolve()
    archive = (root / name).resolve()
    if archive.parent != root or not archive.is_file() or not archive.name.startswith("LegacyPlayer-"):
        raise ValueError("unknown backup")
    safety = None
    try:
        safety = backup_all(sources, safety_root, "before-restore")["name"]
    except ValueError:
        pass
    restored = 0
    try:
        with _zipfile.ZipFile(archive) as z:
            manifest = _json.loads(z.read("manifest.json"))
            if not isinstance(manifest, dict) or not isinstance(manifest.get("consoles"), (list, dict)):
                raise ValueError("this backup has no readable contents list")
            if sum(m.file_size for m in z.infolist()) > MAX_RESTORE_BYTES or any(m.file_size > MAX_RESTORE_BYTES for m in z.infolist()):
                raise ValueError("this backup is far larger than save files should be, so it was not opened")
            bad = z.testzip()                      # checks every file before anything on disk is touched
            if bad:
                raise ValueError(f"this backup is damaged ({bad}), so nothing was restored")
            for member in z.infolist():
                if member.is_dir() or member.filename == "manifest.json":
                    continue
                console, _, rel = member.filename.partition("/")
                folder = sources.get(console)
                if not folder or not rel:
                    continue
                target = (Path(folder) / rel).resolve()
                if Path(folder).resolve() not in target.parents:
                    continue     # never write outside the save folder
                target.parent.mkdir(parents=True, exist_ok=True)
                part = target.with_name(target.name + ".lp-part")
                try:
                    with z.open(member) as src, open(part, "wb") as out:
                        shutil.copyfileobj(src, out)
                    os.replace(part, target)       # a save is either the old one or the whole new one, never half
                finally:
                    if part.exists():
                        part.unlink()
                restored += 1
    except (_zipfile.BadZipFile, KeyError, _json.JSONDecodeError) as exc:
        raise ValueError("this backup could not be read, so nothing was restored") from exc
    return {"restored": restored, "safety_backup": safety, "consoles": sorted(manifest["consoles"])}
