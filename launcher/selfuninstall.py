"""Uninstalling Legacy Player itself. Only ever touches what Legacy Player made: its own data folder,
its log folder and its own program file. Your games, and emulators you installed yourself, are never touched."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KEEPABLE = ("saves", "save_backups")


def _size(path: Path) -> int:
    if path.is_symlink():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                pass
    return total


def _mb(n: int) -> float:
    return round(n / 1048576, 1)


def log_folder() -> Path | None:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "LegacyPlayer" if base else None


def program_file() -> Path | None:
    """The downloaded program itself, only when this is the packaged app (never a source checkout)."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return exe if exe.is_file() else None
    return None


def created_folders(custom_save_root: str, custom_backup_root: str, console_ids, data_dir: Path | None = None) -> list[dict]:
    """Folders Legacy Player itself made inside places the player chose. Only the exact shapes it creates:
    <save root>/<console>/(saves|states) and LegacyPlayer-*.zip backups. Anything else in those places is never listed."""
    out = []
    ids = set(console_ids or [])
    if custom_save_root:
        root = Path(custom_save_root)
        if root.is_dir() and not (data_dir and _inside(root, Path(data_dir))):
            for cid in sorted(ids):
                d = root / cid
                if d.is_dir() and not d.is_symlink():
                    kids = [k.name for k in d.iterdir()]
                    if kids and set(kids) <= {"saves", "states"}:
                        out.append({"kind": "saves", "label": f"Saves for {cid}", "path": str(d), "mb": _mb(_size(d))})
    if custom_backup_root:
        root = Path(custom_backup_root)
        if root.is_dir() and not (data_dir and _inside(root, Path(data_dir))):
            zips = [z for z in sorted(root.glob("LegacyPlayer-*.zip")) if z.is_file() and not z.is_symlink()]
            if zips:
                out.append({"kind": "backups", "label": f"{len(zips)} backup file{'s' if len(zips) != 1 else ''}", "path": str(root),
                            "files": [str(z) for z in zips], "mb": _mb(sum(_size(z) for z in zips))})
    return out


def check_data_dir(data_dir: Path) -> str | None:
    """Why this folder must not be cleaned out, or None when it is clearly Legacy Player's own. Legacy Player deletes
    the contents of its data folder, so it first makes sure that is really what the folder is."""
    try:
        d = Path(data_dir).resolve()
    except OSError:
        return "I can not read that folder."
    home = Path.home().resolve()
    if d == d.parent or d == home or d in home.parents:
        return "That is not a folder only Legacy Player uses, so I will not clear it."
    if d.name.lower() in {"documents", "desktop", "downloads", "pictures", "music", "videos", "windows", "program files", "program files (x86)"}:
        return "That is one of your own folders, so I will not clear it."
    if d.is_dir() and any(d.iterdir()) and not ((d / "user_data.json").is_file() or (d / ".legacy-player").is_file()
                                              or any((d / n).is_dir() for n in ("emulators", "server", "retroarch_append", "save_backups"))):
        return "That folder does not look like Legacy Player's own, so I will not clear it."
    return None


def _holds_saves(folder: Path, keep_paths) -> bool:
    """An emulator folder that also keeps the player's saves (a portable Dolphin's User/GC, a saves or states folder)."""
    for k in keep_paths or []:
        if k and _inside(Path(k), folder):
            return True
    for sub in (("User", "GC"), ("User", "StateSaves"), ("saves",), ("states",), ("memcards",)):
        d = folder.joinpath(*sub)
        try:
            if d.is_dir() and any(d.iterdir()):
                return True
        except OSError:
            pass
    return False


def plan(data_dir: Path, custom_save_root: str = "", custom_backup_root: str = "", console_ids=()) -> dict:
    data_dir = Path(data_dir)
    items = []

    def add(key, label, why, paths, keepable=False):
        paths = [p for p in paths if p.exists() or p.is_symlink()]
        if not paths and key != "program":
            return
        items.append({"key": key, "label": label, "why": why, "keepable": keepable,
                      "paths": [str(p) for p in paths], "mb": _mb(sum(_size(p) for p in paths))})

    add("emulators", "Emulators Legacy Player downloaded", "Only the ones it installed itself into its own folder.", [data_dir / "emulators"])
    known = {"emulators", *KEEPABLE}
    rest = [p for p in sorted(data_dir.iterdir()) if p.name not in known] if data_dir.is_dir() else []
    add("library", "Settings, library list, covers and server info", "Your name, favorites, collections, custom covers and the library list.", rest)
    add("saves", "Your game saves and backups", "Progress made in games, plus the backups Legacy Player made.",
        [data_dir / "saves", data_dir / "save_backups"], keepable=True)
    logs = log_folder()
    if logs:
        add("logs", "Activity log", "A small text file for troubleshooting.", [logs])
    exe = program_file()
    items.append({"key": "program", "label": "The Legacy Player program", "keepable": False,
                  "why": "The program file you downloaded." if exe else "You are running from source, so there is no program file to remove; delete the folder yourself if you want it gone.",
                  "paths": [str(exe)] if exe else [], "mb": _mb(_size(exe)) if exe else 0.0, "available": bool(exe)})
    kept_elsewhere = []
    if custom_save_root and not _inside(Path(custom_save_root), data_dir):
        kept_elsewhere.append({"label": "Save folder you chose", "path": custom_save_root})
    if custom_backup_root and not _inside(Path(custom_backup_root), data_dir):
        kept_elsewhere.append({"label": "Backup folder you chose", "path": custom_backup_root})
    return {"data_dir": str(data_dir), "items": items, "never_touched": kept_elsewhere, "refuse": check_data_dir(data_dir),
            "created": created_folders(custom_save_root, custom_backup_root, console_ids, data_dir),
            "total_mb": round(sum(i["mb"] for i in items), 1)}


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except (OSError, ValueError):
        return False


def _remove(path: Path, problems: list) -> None:
    def onerror(func, p, exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError as err:
            problems.append(f"{p} ({err.strerror or err})")
    try:
        if path.is_symlink() or path.is_file():
            try:
                path.unlink()
            except OSError:
                os.chmod(path, 0o600)
                path.unlink()
        elif path.is_dir():
            shutil.rmtree(path, onerror=onerror)
    except OSError as err:
        problems.append(f"{path} ({err.strerror or err})")


def _remove_created(created: list[dict], problems: list) -> int:
    freed = 0
    for c in created:
        if c["kind"] == "saves":
            _remove(Path(c["path"]), problems)
        else:
            for f in c.get("files", []):
                _remove(Path(f), problems)
        freed += int(c["mb"] * 100)
    return freed                                      # the folders the player chose stay; only what we made goes


def execute(data_dir: Path, keep_saves: bool, remove_program: bool, created: list[dict] | None = None, delete_created: bool = False,
            keep_paths=()) -> dict:
    """Do the clean-up. Returns a report with one row per step so the doctor can narrate it."""
    data_dir = Path(data_dir)
    why = check_data_dir(data_dir)
    if why:
        raise ValueError(why)
    steps, problems_all = [], []
    pl = plan(data_dir)
    deferred = []
    for item in pl["items"]:
        key = item["key"]
        if key == "program":
            continue
        if item["keepable"] and keep_saves:
            steps.append({"key": key, "label": item["label"], "status": "kept", "mb": item["mb"]})
            continue
        if key == "logs":
            deferred.append(Path(item["paths"][0]))      # the log file is open right now: removed once we close
            steps.append({"key": key, "label": item["label"], "status": "after_close", "mb": item["mb"]})
            continue
        problems = []
        held = []
        for p in item["paths"]:
            if key == "emulators" and keep_saves and Path(p).is_dir():
                for child in sorted(Path(p).iterdir()):         # an emulator folder that also holds the player's saves stays
                    if child.is_dir() and _holds_saves(child, keep_paths):
                        held.append(child.name)
                    else:
                        _remove(child, problems)
                try:
                    Path(p).rmdir()
                except OSError:
                    pass
            else:
                _remove(Path(p), problems)
        problems_all += problems
        steps.append({"key": key, "label": item["label"], "status": "problem" if problems else "removed", "mb": item["mb"], "kept_with_saves": held})
    if created:
        if delete_created:
            problems = []
            _remove_created(created, problems)
            problems_all += problems
            steps.append({"key": "created", "label": "Save folders I made in places you chose", "status": "problem" if problems else "removed",
                          "mb": round(sum(c["mb"] for c in created), 1)})
        else:
            steps.append({"key": "created", "label": "Save folders I made in places you chose", "status": "kept",
                          "mb": round(sum(c["mb"] for c in created), 1)})
    exe = program_file() if remove_program else None
    if remove_program:
        steps.append({"key": "program", "label": "The Legacy Player program", "mb": pl["items"][-1]["mb"],
                      "status": "after_close" if exe else "skipped"})
    purge = None
    if not keep_saves:
        purge = data_dir

    else:
        try:
            data_dir.rmdir()
        except OSError:
            pass
    if exe or deferred or purge:
        _spawn_cleanup(exe, deferred, purge)
    freed = round(sum(s["mb"] for s in steps if s["status"] in ("removed", "after_close")), 1)
    return {"steps": steps, "problems": problems_all, "freed_mb": freed, "kept_saves": bool(keep_saves), "kept_created": bool(created) and not delete_created,
            "program_pending": bool(exe), "never_touched": pl["never_touched"]}


def _hidden_flags() -> int:
    """Run the cleanup script with a hidden console and nothing else. Not DETACHED_PROCESS: that makes Windows ignore
    CREATE_NO_WINDOW, so every command in the script (each `ping`) would open its own visible console window."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def _spawn_cleanup(exe: Path | None, others: list, purge: Path | None) -> None:
    """After Legacy Player closes, remove the files that were in use. Retries for a while, then gives up quietly."""
    paths = ([exe] if exe else []) + list(others) + ([purge] if purge else [])
    try:
        if os.name == "nt":
            def q(value) -> str:      # percent signs would be expanded by the batch interpreter
                return str(value).replace("%", "%%")
            lines = ["@echo off", "set n=0", ":again", "ping -n 3 127.0.0.1 >nul", "set /a n+=1"]
            for p in paths:
                if p == exe:
                    lines.append(f'del /f /q "{q(p)}" >nul 2>&1')
                else:
                    lines.append(f'rmdir /s /q "{q(p)}" >nul 2>&1')
            if exe:
                lines.append(f'if exist "{q(exe)}" if %n% lss 300 goto again')
            lines += ['(goto) 2>nul & del "%~f0"']
            fd, bat = tempfile.mkstemp(suffix=".bat", prefix="lp-clean-")
            with os.fdopen(fd, "w") as f:
                f.write("\r\n".join(lines) + "\r\n")
            flags = _hidden_flags()
            subprocess.Popen(["cmd", "/c", bat], creationflags=flags, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            quoted = " ".join("'" + str(p).replace("'", "'\\''") + "'" for p in paths)
            subprocess.Popen(["sh", "-c", f"sleep 4; rm -rf {quoted}"], start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
