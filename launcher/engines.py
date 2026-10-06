"""Engine registry for the owned shell.

An *engine* is an emulator program Legacy Player runs inside its shell. For each one this
file records where it officially comes from, how to recognise it on disk, and which BIOS or
firmware it needs from the user's own consoles. Nothing here touches the network; see
launcher/installer.py for downloads (which need the user's explicit go-ahead).
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

# official_source kinds: "github" (releases API, asset matched by regex) or "page" (manual).
ENGINES: dict[str, dict] = {
    "retroarch": {"name": "RetroArch", "consoles": ["atari", "nes", "snes", "genesis", "gb", "gbc", "gba", "ps1", "n64", "ds"],
                  "source": {"kind": "page", "url": "https://www.retroarch.com/?page=platforms", "note": "Setup installs it from buildbot.libretro.com."},
                  "license": "GPL-3.0"},
    "dolphin": {"name": "Dolphin", "consoles": ["gamecube", "wii"],
                "source": {"kind": "page", "url": "https://dolphin-emu.org/download/", "note": "Dolphin publishes builds on its own site, not GitHub releases."},
                "license": "GPL-2.0"},
    "pcsx2": {"name": "PCSX2", "consoles": ["ps2"],
              "source": {"kind": "github", "repo": "PCSX2/pcsx2", "asset": r"pcsx2-v[\d.]+-windows-x64-Qt\.7z$"},
              "license": "GPL-3.0", "bios": "ps2"},
    "ppsspp": {"name": "PPSSPP", "consoles": ["psp"],
               "source": {"kind": "github", "repo": "hrydgard/ppsspp", "asset": r"ppsspp_win\.zip$",
                          "page": "https://www.ppsspp.org/download/"},
               "license": "GPL-2.0"},
    "azahar": {"name": "Azahar", "consoles": ["3ds"],
               "source": {"kind": "github", "repo": "azahar-emu/azahar", "asset": r"azahar-[\d.]+-windows-msvc\.zip$"},
               "license": "GPL-2.0"},
    "mgba": {"name": "mGBA", "consoles": ["gb", "gbc", "gba"],
             "source": {"kind": "github", "repo": "mgba-emu/mgba", "asset": r"mGBA-[\d.]+-win64\.7z$"},
             "license": "MPL-2.0"},
    "melonds": {"name": "melonDS", "consoles": ["ds"],
                "source": {"kind": "github", "repo": "melonDS-emu/melonDS", "asset": r"melonDS-windows-x86_64\.zip$"},
                "license": "GPL-3.0", "bios": "ds"},
    "duckstation": {"name": "DuckStation", "consoles": ["ps1"],
                    "source": {"kind": "github", "repo": "stenzek/duckstation", "asset": r"duckstation-windows-x64-release\.zip$"},
                    "license": "CC-BY-NC-ND-4.0", "bios": "ps1"},
    "bsnes": {"name": "bsnes", "consoles": ["snes"],
              "source": {"kind": "github", "repo": "bsnes-emu/bsnes", "asset": r"bsnes-windows\.zip$"},
              "license": "GPL-3.0"},
    "snes9x": {"name": "Snes9x", "consoles": ["snes"],
               "source": {"kind": "github", "repo": "snes9xgit/snes9x", "asset": r"snes9x-[\d.]+-win32-x64\.zip$"},
               "license": "Snes9x (non-commercial)"},
    "mesen": {"name": "Mesen", "consoles": ["nes", "snes", "gb", "gbc"],
              "source": {"kind": "github", "repo": "SourMesen/Mesen2", "asset": r"Mesen_Windows\.zip$"},
              "license": "GPL-3.0"},
    "mupen": {"name": "Mupen64Plus", "consoles": ["n64"],
              "source": {"kind": "page", "url": "https://mupen64plus.org/", "note": "No single official Windows GUI build on GitHub releases."},
              "license": "GPL-2.0"},
    "xemu": {"name": "xemu", "consoles": ["xbox"],
             "source": {"kind": "github", "repo": "xemu-project/xemu", "asset": r"xemu-win-x86_64-release\.zip$"},
             "license": "GPL-2.0", "bios": "xbox"},
    "xenia": {"name": "Xenia Canary", "consoles": ["x360"],
              "source": {"kind": "github", "repo": "xenia-canary/xenia-canary-releases", "asset": r"xenia_canary_windows\.zip$"},
              "license": "BSD-3-Clause"},
    "rpcs3": {"name": "RPCS3", "consoles": ["ps3"],
              "source": {"kind": "github", "repo": "RPCS3/rpcs3-binaries-win", "asset": r"rpcs3-v[\d.]+-[0-9a-f]+_win64\.7z$"},
              "license": "GPL-2.0", "bios": "ps3"},
}

HOMEPAGES = {
    "retroarch": "https://www.retroarch.com", "dolphin": "https://dolphin-emu.org", "pcsx2": "https://pcsx2.net",
    "ppsspp": "https://www.ppsspp.org", "azahar": "https://azahar-emu.org", "mgba": "https://mgba.io",
    "melonds": "https://melonds.kuribo64.net", "duckstation": "https://github.com/stenzek/duckstation",
    "bsnes": "https://github.com/bsnes-emu/bsnes", "snes9x": "https://www.snes9x.com", "mesen": "https://www.mesen.ca",
    "mupen": "https://mupen64plus.org", "xemu": "https://xemu.app", "xenia": "https://xenia.jp", "rpcs3": "https://rpcs3.net",
}
# Engines whose license does not allow us to redistribute builds (users fetch them themselves).
NOT_REDISTRIBUTABLE = {"duckstation", "snes9x"}

# A third-party mirror the user may choose instead of the official release. We do not fetch
# from it automatically (it asks for a browser and is not the project's own channel).
MIRROR = {"name": "Vimm's Lair (Emulation Lair)", "url": "https://vimm.net/?p=emulators",
          "note": "Third-party mirror of emulator builds. Download in your browser, then add the folder in Emulators. Not verified by this app."}

# Files the user must dump from hardware they own. Legacy Player only *finds* them.
BIOS: dict[str, dict] = {
    "ps2": {"name": "PlayStation 2 BIOS", "for": "PCSX2", "patterns": ("scph*.bin", "ps2-*.bin", "*.bin"),
            "sizes": (4 * 1024 * 1024,), "folders": ("PCSX2/bios", "Documents/PCSX2/bios"),
            "how": "Dump it from your own PS2 with a tool such as biosdrain (a USB stick and a FreeMcBoot card). PCSX2 refuses to start without it."},
    "ps1": {"name": "PlayStation BIOS", "for": "DuckStation / RetroArch", "patterns": ("scph*.bin", "ps-*.bin", "psx*.bin"),
            "sizes": (512 * 1024,), "folders": ("DuckStation/bios", "Documents/DuckStation/bios", "RetroArch/system"),
            "how": "Dump it from your own PlayStation (for example with the Caetla or a modchip + serial cable method). Common file names look like scph1001.bin."},
    "ds": {"name": "Nintendo DS firmware and BIOS", "for": "melonDS (optional in modern builds)", "patterns": ("bios7.bin", "bios9.bin", "firmware.bin"),
           "sizes": (16 * 1024, 4 * 1024, 256 * 1024, 512 * 1024), "folders": ("melonDS", "AppData/Roaming/melonDS"),
           "how": "melonDS can run without them. For the real firmware, dump it from your own DS with a flashcart homebrew such as dsbf_dump."},
    "xbox": {"name": "Xbox BIOS and MCPX ROM", "for": "xemu", "patterns": ("mcpx*.bin", "complex*.bin", "*.bin"),
             "sizes": (512, 256 * 1024, 1024 * 1024), "folders": ("xemu",),
             "how": "Dump from your own Xbox (xemu's guide covers this). xemu also needs an HDD image you make yourself."},
    "ps3": {"name": "PS3 system software", "for": "RPCS3", "patterns": ("PS3UPDAT.PUP",), "sizes": (),
            "folders": ("Downloads", "RPCS3"),
            "how": "This one is legitimately downloadable from Sony's PlayStation support site (PS3UPDAT.PUP). RPCS3 installs it from File > Install Firmware."},
}


def _candidate_roots() -> list[Path]:
    """Where emulator programs usually live. Nothing outside these is read."""
    roots: list[Path] = []
    home = Path.home()
    if sys.platform == "win32":
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData", "ProgramData"):
            value = os.environ.get(var)
            if value:
                roots.append(Path(value))
        roots += [home / "Desktop", home / "Downloads", home / "Documents", home / "Dev", home / "AppData" / "Roaming"]
        for drive in "DEFGHP":
            if Path(f"{drive}:\\").exists():
                roots += [Path(f"{drive}:\\Emulators"), Path(f"{drive}:\\Games")]
    else:
        roots += [Path("/usr/bin"), Path("/usr/local/bin"), Path("/opt"), Path("/Applications"),
                  home / ".local" / "bin", home / "Applications", home / "Downloads"]
    return [r for r in roots if r.is_dir()]


def _program_files_hint(exe: str) -> str:
    return exe.lower()


def scan_computer(wanted: dict[str, list[str]], extra_roots: list[Path] | None = None,
                  max_depth: int = 4, budget: int = 60000) -> dict[str, str]:
    """Find emulator executables under the usual program folders. Read-only; bounded.

    wanted: emulator id -> executable file names. Returns emulator id -> path for hits."""
    lookup = {name.lower(): emulator_id for emulator_id, names in wanted.items() for name in names}
    found: dict[str, str] = {}
    seen = 0
    skip_dirs = {"windows", "$recycle.bin", "system volume information", "node_modules", ".git", "__pycache__"}
    for root in list(extra_roots or []) + _candidate_roots():
        root = Path(root)
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            seen += 1
            if seen > budget:
                return found
            rel_depth = len(Path(dirpath).relative_to(root).parts)
            if rel_depth >= max_depth:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames if d.lower() not in skip_dirs]
            for name in filenames:
                emulator_id = lookup.get(name.lower())
                if emulator_id and emulator_id not in found:
                    found[emulator_id] = str(Path(dirpath) / name)
    return found


def sha256_of(path: Path, limit: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            if stream.tell() > limit:
                break
    return digest.hexdigest()


def find_bios(kind: str, search_roots: list[Path], extra_dirs: list[Path] | None = None, budget: int = 20000) -> list[dict]:
    """Look for BIOS/firmware files the user already has. Read-only; nothing is copied."""
    spec = BIOS[kind]
    hits: list[dict] = []
    seen_paths: set[str] = set()
    candidates: list[Path] = list(extra_dirs or [])
    home = Path.home()
    for folder in spec["folders"]:
        candidates += [home / folder, home / "Documents" / folder, Path(os.environ.get("ProgramData", "/nonexistent")) / folder]
    candidates += [Path(r) / sub for r in search_roots for sub in ("bios", "BIOS", "system", "firmware", ".")]
    seen = 0
    for folder in candidates:
        if not folder.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(folder):
            seen += 1
            if seen > budget:
                return hits
            if len(Path(dirpath).relative_to(folder).parts) >= 3:
                dirnames[:] = []
            for name in filenames:
                path = Path(dirpath) / name
                low = name.lower()
                if not any(Path(low).match(p.lower()) for p in spec["patterns"]):
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if spec["sizes"] and size not in spec["sizes"]:
                    continue
                if str(path) in seen_paths:
                    continue
                seen_paths.add(str(path))
                hits.append({"path": str(path), "size": size, "sha256": sha256_of(path)[:16]})
    return hits
