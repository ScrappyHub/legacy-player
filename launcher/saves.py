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


# What may follow the game's own name in one of its save files: an optional slot like "_1" (memory cards), then one
# or more short extensions (".srm", ".state1", ".state.auto", ".ss0"). "Super Mario Bros 3.srm" is not a save of
# "Super Mario Bros": what follows that name there is " 3.srm".
_SAVE_TAIL = re.compile(r"(?:_\d{1,2})?(?:\.[a-z0-9_-]{1,12})+")


class SaveFileBusy(ValueError):
    """A save file could not be read or replaced, usually because the emulator still has it open. A ValueError, so
    callers that turn ValueError into a message for the player show it as one."""


def belongs_to(name: str, game_stem: str) -> bool:
    """True when a file name is one of this game's saves: exactly its name, or its name plus a save suffix."""
    name, stem = name.lower(), game_stem.lower()
    if not stem:
        return True
    if not name.startswith(stem):
        return False
    tail = name[len(stem):]
    return tail == "" or bool(_SAVE_TAIL.fullmatch(tail))


def find_save_files(save_dir: Path, game_stem: str) -> list[Path]:
    """This game's save files (an empty stem means every save file in the folder)."""
    if not save_dir.is_dir():
        return []
    found = []
    for path in save_dir.rglob("*"):
        if len(path.relative_to(save_dir).parts) > 4 or not path.is_file():
            continue
        if path.suffix.lower() in SAVE_EXTENSIONS or ".state" in path.name.lower():
            if belongs_to(path.name, game_stem):
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
    try:
        safety = create_backup(data_dir, console, compat_id, current, save_dir)["backup"] if current else None
    except OSError as exc:
        raise SaveFileBusy(f"The current saves could not be backed up first ({_why(exc)}), so nothing was restored. "
                           "Close the emulator and try again.") from exc
    files = [f for f in sorted(source.rglob("*")) if f.is_file()]
    save_root = Path(save_dir).resolve()
    plan = []
    for file in files:
        destination = save_dir / file.relative_to(source)
        if save_root not in destination.resolve().parents:
            continue                                   # never write outside the save folder
        plan.append((file, destination, destination.with_name(destination.name + ".lp-part")))
    # 1. every file is copied next to its place first; if any copy fails, nothing has been touched yet
    try:
        for file, destination, part in plan:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, part)
    except OSError as exc:
        _remove_parts(plan)
        raise SaveFileBusy(f"Restoring failed before any save was changed ({_why(exc)}). Close the emulator and try again.") from exc
    # 2. each one is swapped in whole (os.replace); if one is locked, those already swapped are put back
    done: list[tuple[Path, bool]] = []
    try:
        for file, destination, part in plan:
            existed = destination.exists()
            os.replace(part, destination)
            done.append((destination, existed))
    except OSError as exc:
        _remove_parts(plan)
        _undo_restore(done, backup_dir(data_dir, console, compat_id) / safety if safety else None, save_dir)
        busy = Path(str(getattr(exc, "filename2", None) or getattr(exc, "filename", None) or "A save file")).name.removesuffix(".lp-part")
        raise SaveFileBusy(f"{busy} is in use ({_why(exc)}), so the restore was undone. Close the emulator and try again.") from exc
    return {"restored": len(done), "previous_saves_backed_up_as": safety}


def _why(exc: OSError) -> str:
    return exc.strerror or type(exc).__name__


def _remove_parts(plan) -> None:
    for _, _, part in plan:
        try:
            part.unlink()
        except OSError:
            pass


def _undo_restore(done: list[tuple[Path, bool]], safety: Path | None, save_dir: Path) -> None:
    """Best effort: put back the files that were already replaced, from the safety backup made just before."""
    for destination, existed in reversed(done):
        try:
            previous = safety / destination.relative_to(save_dir) if safety else None
            if existed and previous is not None and previous.is_file():
                part = destination.with_name(destination.name + ".lp-part")
                shutil.copy2(previous, part)
                os.replace(part, destination)
            elif not existed:
                destination.unlink()
        except OSError:
            pass


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
        raise ValueError("There are no save files yet in any save folder, so there is nothing to back up.")
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
