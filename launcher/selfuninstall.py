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


def plan(data_dir: Path, custom_save_root: str = "", custom_backup_root: str = "") -> dict:
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
    return {"data_dir": str(data_dir), "items": items, "never_touched": kept_elsewhere,
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


def execute(data_dir: Path, keep_saves: bool, remove_program: bool) -> dict:
    """Do the clean-up. Returns a report with one row per step so the doctor can narrate it."""
    data_dir = Path(data_dir)
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
        for p in item["paths"]:
            _remove(Path(p), problems)
        problems_all += problems
        steps.append({"key": key, "label": item["label"], "status": "problem" if problems else "removed", "mb": item["mb"]})
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
    return {"steps": steps, "problems": problems_all, "freed_mb": freed, "kept_saves": bool(keep_saves),
            "program_pending": bool(exe), "never_touched": pl["never_touched"]}


def _spawn_cleanup(exe: Path | None, others: list, purge: Path | None) -> None:
    """After Legacy Player closes, remove the files that were in use. Retries for a while, then gives up quietly."""
    paths = ([exe] if exe else []) + list(others) + ([purge] if purge else [])
    try:
        if os.name == "nt":
            lines = ["@echo off", "set n=0", ":again", "ping -n 3 127.0.0.1 >nul", "set /a n+=1"]
            for p in paths:
                if p == exe:
                    lines.append(f'del /f /q "{p}" >nul 2>&1')
                else:
                    lines.append(f'rmdir /s /q "{p}" >nul 2>&1')
            if exe:
                lines.append(f'if exist "{exe}" if %n% lss 300 goto again')
            lines += ['(goto) 2>nul & del "%~f0"']
            fd, bat = tempfile.mkstemp(suffix=".bat", prefix="lp-clean-")
            with os.fdopen(fd, "w") as f:
                f.write("\r\n".join(lines) + "\r\n")
            flags = getattr(subprocess, "DETACHED_PROCESS", 8) | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(["cmd", "/c", bat], creationflags=flags, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            quoted = " ".join("'" + str(p).replace("'", "'\\''") + "'" for p in paths)
            subprocess.Popen(["sh", "-c", f"sleep 4; rm -rf {quoted}"], start_new_session=True, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
