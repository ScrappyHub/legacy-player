"""Controller and keyboard settings for Dolphin (GameCube).

Dolphin keeps pad settings in its own `Config/GCPadNew.ini`. When a pad is assigned to a player in Legacy Player
(or a non-default keyboard layout is chosen for player 1), the matching sections are written there before Dolphin
starts. The first time, the file you had is copied to `GCPadNew.ini.legacy-player-backup`, and `restore()` puts it
back. Nothing else in Dolphin's folder is touched. Wii remotes are left to Dolphin.

Names follow Dolphin's own: XInput pads are `XInput/<n>/Gamepad`, the keyboard is `DInput/0/Keyboard Mouse` on
Windows. They are marked unverified until checked against a real Dolphin on Windows (see docs/WINDOWS_CHECKLIST.md).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import keyboard, pads

BACKUP = "GCPadNew.ini.legacy-player-backup"
MARK = "; written by Legacy Player"

# physical XInput bit (see pads.XINPUT_BIT) -> Dolphin's XInput control name
XINPUT_NAME = {12: "Button A", 13: "Button B", 14: "Button X", 15: "Button Y", 8: "Shoulder L", 9: "Shoulder R",
               5: "Back", 4: "Start", 6: "Thumb L", 7: "Thumb R", 0: "Pad N", 1: "Pad S", 2: "Pad W", 3: "Pad E"}
# GameCube control -> the standard control (pads.STANDARD_NAMES) it follows on a standard pad
GC_FROM_STANDARD = {"Buttons/A": 0, "Buttons/B": 2, "Buttons/X": 1, "Buttons/Y": 3, "Buttons/Z": 5, "Buttons/Start": 9,
                    "D-Pad/Up": 12, "D-Pad/Down": 13, "D-Pad/Left": 14, "D-Pad/Right": 15}
KEY_NAME = {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT", "enter": "RETURN", "space": "SPACE", "backspace": "BACK",
            "tab": "TAB", "shift": "LSHIFT", "rshift": "RSHIFT", "ctrl": "LCONTROL", "rctrl": "RCONTROL", "alt": "LMENU", "ralt": "RMENU"}
# RetroPad role -> GameCube control (the GameCube has no Select, so it becomes Z)
GC_FROM_ROLE = {"a": "Buttons/A", "b": "Buttons/B", "x": "Buttons/X", "y": "Buttons/Y", "start": "Buttons/Start", "select": "Buttons/Z",
                "l": "Triggers/L", "r": "Triggers/R", "up": "D-Pad/Up", "down": "D-Pad/Down", "left": "D-Pad/Left", "right": "D-Pad/Right"}


def user_dirs(exe: str | Path) -> list[Path]:
    """Where Dolphin may keep its settings, most likely first."""
    exe = Path(exe)
    found = []
    if (exe.parent / "portable.txt").exists():
        found.append(exe.parent / "User")
    home = Path(os.path.expanduser("~"))
    if sys.platform == "win32":
        found += [home / "Documents" / "Dolphin Emulator", Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "Dolphin Emulator"]
    elif sys.platform == "darwin":
        found.append(home / "Library" / "Application Support" / "Dolphin")
    else:
        found += [home / ".config" / "dolphin-emu", home / ".local" / "share" / "dolphin-emu"]
    return found


def find_user_dir(exe: str | Path) -> Path | None:
    for d in user_dirs(exe):
        if (d / "Config").is_dir():
            return d
    return None


def _keyboard_device() -> str:
    return "DInput/0/Keyboard Mouse" if sys.platform == "win32" else ("Quartz/0/Keyboard & Mouse" if sys.platform == "darwin" else "XInput2/0/Virtual core pointer")


def _key(name: str) -> str:
    return KEY_NAME.get(name, name.upper())


def pad_section(number: int, profile: dict) -> tuple[list[str], list[str]]:
    """GCPad lines for a standard (XInput-style) pad. Returns (lines, notes)."""
    if not profile.get("standard"):
        return [], ["This pad is not in the standard layout, so Dolphin's own setting is left alone."]
    notes = []
    lines = [f"[GCPad{number}]", f"Device = XInput/{number - 1}/Gamepad"]
    for gc, slot in GC_FROM_STANDARD.items():
        binding = pads.translate(profile, slot)
        if binding is None:
            continue
        if binding["t"] != "b" or binding["i"] not in pads.XINPUT_BIT:
            notes.append(f"{gc} uses an axis, so Dolphin's own setting is kept.")
            continue
        bit = pads.XINPUT_BIT[binding["i"]]
        lines.append(f"{gc} = `{XINPUT_NAME[bit]}`")
    lines += ["Main Stick/Up = `Left Y+`", "Main Stick/Down = `Left Y-`", "Main Stick/Left = `Left X-`", "Main Stick/Right = `Left X+`",
              "C-Stick/Up = `Right Y+`", "C-Stick/Down = `Right Y-`", "C-Stick/Left = `Right X-`", "C-Stick/Right = `Right X+`",
              "Triggers/L = `Trigger L`", "Triggers/R = `Trigger R`", "Triggers/L-Analog = `Trigger L`", "Triggers/R-Analog = `Trigger R`",
              "Options/Always Connected = True"]
    return lines, notes


def keyboard_section(number: int, cfg: dict | None) -> list[str]:
    keys = keyboard.resolved(cfg)
    lines = [f"[GCPad{number}]", f"Device = {_keyboard_device()}"]
    for role, gc in GC_FROM_ROLE.items():
        lines.append(f"{gc} = {_key(keys[role])}")
    for role, stick in (("up", "Main Stick/Up"), ("down", "Main Stick/Down"), ("left", "Main Stick/Left"), ("right", "Main Stick/Right")):
        lines.append(f"{stick} = {_key(keys[role])}")
    lines.append("Options/Always Connected = True")
    return lines


def build(player_pads: dict, pad_profiles: dict, keyboard_cfg: dict | None) -> tuple[str, list[str]]:
    """The managed text, or "" when nothing is assigned. Players without a choice are left to Dolphin."""
    blocks, notes = [], []
    for player in range(1, pads.MAX_PLAYERS + 1):
        key = player_pads.get(str(player))
        profile = pad_profiles.get(key) if key else None
        if profile:
            lines, n = pad_section(player, profile)
            notes += n
            if lines:
                blocks.append("\n".join(lines))
                continue
        if player == 1 and keyboard_cfg and keyboard_cfg.get("layout", "default") != "default":
            blocks.append("\n".join(keyboard_section(1, keyboard_cfg)))
    return ("\n".join([MARK] + [b + "\n" for b in blocks]) if blocks else ""), notes


def apply(exe: str | Path, player_pads: dict, pad_profiles: dict, keyboard_cfg: dict | None) -> dict:
    """Write the managed pad file for this launch. Never raises: a problem just means Dolphin keeps its own settings."""
    try:
        text, notes = build(player_pads, pad_profiles, keyboard_cfg)
        user = find_user_dir(exe)
        if user is None:
            return {"applied": False, "notes": notes, "why": "Dolphin has not made its settings folder yet. Open Dolphin once, then try again."}
        target = user / "Config" / "GCPadNew.ini"
        backup = target.with_name(BACKUP)
        if not text:
            return {"applied": False, "notes": notes, "why": "Nothing assigned for Dolphin."}
        if target.exists() and not backup.exists():
            current = target.read_text(encoding="utf-8", errors="replace")
            if not current.startswith(MARK):          # keep the player's own file once, never our own
                backup.write_text(current, encoding="utf-8", newline="\n")
        tmp = target.with_suffix(".ini.lp-tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, target)
        return {"applied": True, "notes": notes, "file": str(target)}
    except OSError as exc:
        return {"applied": False, "notes": [], "why": f"Could not write Dolphin's pad file: {exc}"}


def restore(exe: str | Path) -> dict:
    """Put the player's own GCPadNew.ini back (or remove ours if there was none)."""
    user = find_user_dir(exe)
    if user is None:
        return {"restored": False, "why": "No Dolphin settings folder found."}
    target = user / "Config" / "GCPadNew.ini"
    backup = target.with_name(BACKUP)
    try:
        if backup.exists():
            os.replace(backup, target)
            return {"restored": True}
        if target.exists() and target.read_text(encoding="utf-8", errors="replace").startswith(MARK):
            target.unlink()
            return {"restored": True}
    except OSError as exc:
        return {"restored": False, "why": str(exc)}
    return {"restored": False, "why": "Nothing of ours to undo."}
