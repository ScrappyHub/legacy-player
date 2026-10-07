"""Checks the Windows-only parts of Legacy Player on a real machine. Safe to run: it only touches temporary files.

    python tools/windows_selfcheck.py

Each line is PASS, FAIL or SKIP (SKIP = it does not apply on this computer). Anything it cannot judge by itself is
listed at the end as a short thing to look at, and in docs/WINDOWS_CHECKLIST.md. Exit code 0 means no FAIL.
"""
from __future__ import annotations

import struct
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
WIN = sys.platform == "win32"
results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    print(f"{status:<5} {name}" + (f"  - {detail}" if detail else ""), flush=True)


def check_specs() -> None:
    from launcher import sysinfo
    info = sysinfo.collect()
    if not info.get("os"):
        return record("computer specs read", "FAIL", "no operating system name came back")
    gpus = [g.get("name") for g in info.get("gpus", [])]
    if WIN and not gpus:
        return record("computer specs read", "FAIL", "PowerShell gave no graphics card (is PowerShell blocked?)")
    record("computer specs read", "PASS", f'{info.get("cpu") or "cpu ?"}; {info.get("ram_gb")} GB; {", ".join(gpus) or "no gpu listed"}')


def check_recycle() -> None:
    from launcher.app import LauncherApp
    folder = Path(tempfile.mkdtemp(prefix="lp-check-"))
    target = folder / "recycle-me.txt"
    target.write_text("Legacy Player self-check. Safe to delete.")
    try:
        where = LauncherApp._trash([target])
    except OSError as exc:
        return record("move to Recycle Bin", "FAIL" if WIN else "SKIP", str(exc))
    if target.exists():
        return record("move to Recycle Bin", "FAIL", "the file is still in its folder")
    record("move to Recycle Bin", "PASS", f"moved to {where} (open it and look for recycle-me.txt)")


def check_icon() -> None:
    ico = ROOT / "launcher" / "ui" / "legacy-player.ico"
    if not ico.exists():
        return record("program icon file", "FAIL", "launcher/ui/legacy-player.ico is missing")
    data = ico.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    sizes = sorted({(data[6 + 16 * i] or 256) for i in range(count)})
    if kind != 1 or count < 4 or 16 not in sizes or 256 not in sizes:
        return record("program icon file", "FAIL", f"unexpected icon contents: {count} images, sizes {sizes}")
    bat = (ROOT / "build_exe.bat").read_text(errors="replace") if (ROOT / "build_exe.bat").exists() else ""
    record("program icon file", "PASS" if "--icon" in bat else "FAIL", f"{count} sizes {sizes}" + ("" if "--icon" in bat else "; build_exe.bat does not pass --icon"))


def check_tray() -> None:
    if not WIN:
        return record("tray icon", "SKIP", "Windows only")
    from launcher.tray import NativeTray
    tray = NativeTray("Legacy Player self-check", lambda: [("exit", "Close this check", True)], lambda command: None)
    if not tray.start():
        return record("tray icon", "FAIL", "Windows would not create the notification-area icon")
    tray.notify("Legacy Player", "Self-check: you should see this balloon and the icon.")
    time.sleep(3)
    tray.stop()
    record("tray icon", "PASS", "icon created and balloon sent (look at the notification area while this ran)")


def check_cleanup() -> None:
    from launcher import selfuninstall
    folder = Path(tempfile.mkdtemp(prefix="lp-check-"))
    fake_exe = folder / "legacy-player-check.exe"
    fake_exe.write_bytes(b"MZ" + b"0" * 100)
    leftover = folder / "logs"
    leftover.mkdir()
    (leftover / "a.log").write_text("x")
    selfuninstall._spawn_cleanup(fake_exe, [], leftover)
    deadline = time.time() + 25
    while time.time() < deadline and (fake_exe.exists() or leftover.exists()):
        time.sleep(1)
    gone = not fake_exe.exists() and not leftover.exists()
    record("cleanup script removes the program and its log folder", "PASS" if gone else "FAIL", "" if gone else "something was still there after 25 seconds")


def main() -> int:
    print(f"Legacy Player Windows self-check on {sys.platform}\n")
    for fn in (check_specs, check_icon, check_recycle, check_tray, check_cleanup):
        try:
            fn()
        except Exception as exc:       # one broken check must not hide the rest
            record(fn.__name__.replace("check_", "").replace("_", " "), "FAIL", f"{type(exc).__name__}: {exc}")
    print("\nLook at by hand (see docs/WINDOWS_CHECKLIST.md):")
    print(" - right-click the tray icon: the menu opens, Start/Stop server and Make a fresh code work, Exit quits")
    print(" - Copy buttons (server code, invite code): paste somewhere to confirm")
    print(" - the exe's icon in Explorer, taskbar and tray is Martin")
    print(" - Dolphin: a pad assigned in Controllers works in a GameCube game")
    failed = [r for r in results if r[1] == "FAIL"]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks fine" + (f", {len(failed)} FAILED" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
