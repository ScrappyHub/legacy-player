"""Managed save folders: one tidy folder per console that RetroArch is told to use.

<save root>/<console>/saves   in-game saves (.srm, memory cards)
<save root>/<console>/states  save states
Other emulators keep their own folders; the launcher shows where those usually are and lets
you point backups at them.
"""
from __future__ import annotations

from pathlib import Path

# Typical default locations. They are hints only, not read or changed.
EMULATOR_HINTS = {
    "dolphin": "Documents\\Dolphin Emulator\\GC (memory cards) and \\StateSaves",
    "pcsx2": "Documents\\PCSX2\\memcards and \\sstates",
    "ppsspp": "Documents\\PPSSPP\\PSP\\SAVEDATA",
    "mgba": "next to the game file (.sav)",
    "duckstation": "Documents\\DuckStation\\memcards and \\savestates",
}


def default_root(data_dir: Path) -> Path:
    return Path(data_dir) / "saves"


def console_dir(root: Path, console_id: str) -> Path:
    return Path(root) / console_id


def ensure(root: Path, console_ids) -> None:
    for console_id in console_ids:
        for sub in ("saves", "states"):
            (console_dir(root, console_id) / sub).mkdir(parents=True, exist_ok=True)


def _q(path: Path | str) -> str:
    text = str(path)
    if '"' in text or "\n" in text or "\r" in text:
        raise ValueError("that folder path contains characters RetroArch cannot read")
    return f'"{text}"'


def retroarch_append_config(data_dir: Path, root: Path, console_id: str, exe: str,
                            extra_lines: list[str] | None = None) -> Path:
    """Write the per-console config passed to RetroArch with --appendconfig."""
    ensure(root, [console_id])
    base = console_dir(root, console_id)
    exe_dir = Path(exe).resolve().parent
    lines = [
        f"savefile_directory = {_q(base / 'saves')}",
        f"savestate_directory = {_q(base / 'states')}",
        'savefiles_in_content_dir = "false"',
        'savestates_in_content_dir = "false"',
        'sort_savefiles_enable = "false"',
        'sort_savestates_enable = "false"',
    ]
    if (exe_dir / "info").is_dir():
        lines.append(f"libretro_info_path = {_q(exe_dir / 'info')}")
    lines += extra_lines or []
    target = Path(data_dir) / "retroarch_append" / f"{console_id}.cfg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
