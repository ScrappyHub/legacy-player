"""Controller and keyboard settings for Dolphin (GameCube).

Dolphin keeps pad settings in its own `Config/GCPadNew.ini`. When a pad is assigned to a player in Legacy Player
(or a non-default keyboard layout is chosen for player 1), only that player's [GCPadN] section is replaced before
Dolphin starts; the players set up in Dolphin itself keep their sections. The first time, the file you had is copied
to `GCPadNew.ini.legacy-player-backup`, and `restore()` puts it back. Nothing else in Dolphin's folder is touched.
Wii remotes are left to Dolphin. The settings folder is found the way Dolphin finds it: portable.txt, then the
registry (LocalUserConfig / UserConfigPath), then the real Documents folder (even when moved to OneDrive), then AppData.

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


FOLDERID_DOCUMENTS = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"


def documents_dir() -> Path:
    """The real Documents folder. On Windows it is asked for by its known-folder id, so a Documents folder moved to
    OneDrive (or anywhere else) is found; elsewhere, or if that fails, ~/Documents."""
    home = Path(os.path.expanduser("~"))
    if sys.platform == "win32":
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                            ("Data4", ctypes.c_ubyte * 8)]

            u = uuid.UUID(FOLDERID_DOCUMENTS)
            guid = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
            out = ctypes.c_wchar_p()
            shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
            shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
            if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0 and out.value:
                path = Path(out.value)
                ole32.CoTaskMemFree(out)
                return path
            if out:
                ole32.CoTaskMemFree(out)
        except (OSError, AttributeError, ValueError):
            pass
    return home / "Documents"


def _registry_dirs(exe: Path) -> list[Path]:
    """Dolphin on Windows honours HKCU\\Software\\Dolphin Emulator: LocalUserConfig = 1 means "use the User folder next to
    Dolphin.exe", UserConfigPath names a folder outright."""
    if sys.platform != "win32":
        return []
    found: list[Path] = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Dolphin Emulator") as key:
            try:
                local, _ = winreg.QueryValueEx(key, "LocalUserConfig")
                if str(local).strip() not in ("", "0"):
                    found.append(exe.parent / "User")
            except OSError:
                pass
            try:
                path, _ = winreg.QueryValueEx(key, "UserConfigPath")
                if isinstance(path, str) and path.strip():
                    found.append(Path(os.path.expandvars(path.strip())))
            except OSError:
                pass
    except (OSError, ImportError):
        pass
    return found


def user_dirs(exe: str | Path) -> list[Path]:
    """Where Dolphin may keep its settings, most likely first."""
    exe = Path(exe)
    found = []
    if (exe.parent / "portable.txt").exists():
        found.append(exe.parent / "User")
    home = Path(os.path.expanduser("~"))
    if sys.platform == "win32":
        found += [d for d in _registry_dirs(exe) if d not in found]
        found += [documents_dir() / "Dolphin Emulator", Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "Dolphin Emulator"]
    elif sys.platform == "darwin":
        found.append(home / "Library" / "Application Support" / "Dolphin")
    else:
        found += [home / ".config" / "dolphin-emu", home / ".local" / "share" / "dolphin-emu"]
    return found


def find_user_dir(exe: str | Path) -> Path | None:
    """The settings folder Dolphin is really using. Where two exist, the one whose Dolphin.ini was changed last wins."""
    dirs = [d for d in user_dirs(exe) if (d / "Config").is_dir()]
    if not dirs:
        return None
    if (Path(exe).parent / "portable.txt").exists() and dirs[0] == Path(exe).parent / "User":
        return dirs[0]
    for chosen in _registry_dirs(Path(exe)):            # the registry settles it when it names a folder that exists
        if chosen in dirs:
            return chosen
    def stamp(d: Path) -> float:
        try:
            return (d / "Config" / "Dolphin.ini").stat().st_mtime
        except OSError:
            return -1.0
    return max(dirs, key=stamp)


def _keyboard_device() -> str:
    return "DInput/0/Keyboard Mouse" if sys.platform == "win32" else ("Quartz/0/Keyboard & Mouse" if sys.platform == "darwin" else "XInput2/0/Virtual core pointer")


def _key(name: str) -> str:
    return KEY_NAME.get(name, name.upper())


def pad_section(number: int, profile: dict) -> tuple[list[str], list[str]]:
    """GCPad lines for a standard (XInput-style) pad. Returns (lines, notes)."""
    if not profile.get("standard"):
        return [], ["This pad is not in the standard layout, so Dolphin's own setting is left alone."]
    notes = []
    lines = [f"[GCPad{number}]", f"Device = XInput/{pads.device_index(profile, number)}/Gamepad"]
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


def _sections(text: str) -> list[tuple[str | None, list[str]]]:
    """The ini as (lower-case section name or None for lines before the first section, its lines), in order.
    Our own marker comment is dropped."""
    out: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.splitlines():
        if line.strip() == MARK:
            continue
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            out.append((stripped[1:-1].strip().lower(), [line]))
        else:
            out[-1][1].append(line)
    return out


def merge(existing: str, managed: str) -> str:
    """`existing` with only the [GCPadN] sections that `managed` has replaced (or added); every other section, such
    as the players set up in Dolphin itself, is kept as it was."""
    ours = {}
    for name, lines in _sections(managed):
        if name:
            while lines and not lines[-1].strip():
                lines = lines[:-1]
            ours[name] = lines
    out: list[str] = [MARK]
    done = set()
    for name, lines in _sections(existing):
        if name in ours:
            if name not in done:
                out += ours[name] + [""]
                done.add(name)
            continue
        while name is None and lines and not lines[0].strip():
            lines = lines[1:]
        out += lines
    for name, lines in ours.items():
        if name not in done:
            if out and out[-1].strip():
                out.append("")
            out += lines + [""]
    return "\n".join(out).rstrip("\n") + "\n"


def apply(exe: str | Path, player_pads: dict, pad_profiles: dict, keyboard_cfg: dict | None) -> dict:
    """Write the managed pad sections for this launch into Dolphin's GCPadNew.ini, leaving every other player's
    section alone. Never raises: a problem just means Dolphin keeps its own settings."""
    try:
        text, notes = build(player_pads, pad_profiles, keyboard_cfg)
        user = find_user_dir(exe)
        if user is None:
            return {"applied": False, "notes": notes, "why": "Dolphin has not made its settings folder yet. Open Dolphin once, then try again."}
        target = user / "Config" / "GCPadNew.ini"
        backup = target.with_name(BACKUP)
        if not text:
            return {"applied": False, "notes": notes, "why": "Nothing assigned for Dolphin."}
        current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        if target.exists() and not backup.exists() and not current.startswith(MARK):
            backup.write_text(current, encoding="utf-8", newline="\n")     # keep the player's own file once, never our own
        # Start from the player's own file (the backup when there is one, so sections we wrote for a player who is no
        # longer assigned go back to theirs) and replace only the sections written now.
        base = backup.read_text(encoding="utf-8", errors="replace") if backup.exists() else current
        tmp = target.with_suffix(".ini.lp-tmp")
        tmp.write_text(merge(base, text), encoding="utf-8", newline="\n")
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
