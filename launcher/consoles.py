from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Console:
    id: str
    name: str
    maker: str
    order: int                      # chronological shelf order in the UI
    extensions: tuple[str, ...]     # unambiguous file types
    folder_hints: tuple[str, ...]   # folder names that identify this console
    emulators: tuple[str, ...]      # known emulator ids (see launcher.emulators)
    netplay: str                    # honest multiplayer feasibility label
    netplay_note: str
    controller: str                 # key into launcher.controllers.LAYOUTS
    save_style: str                 # "cartridge" (per-game file) | "memory-card" | "internal"


CONSOLES: tuple[Console, ...] = (
    Console("atari", "Atari", "Atari", 1, (".a26", ".a78", ".j64", ".lnx"), ("atari",), ("retroarch",),
            "strong", "Small deterministic cores; lockstep is realistic.", "atari", "internal"),
    Console("nes", "NES", "Nintendo", 2, (".nes", ".unf", ".fds"), ("nes", "famicom"), ("mesen", "retroarch"),
            "strong", "Deterministic; the best fit for input lockstep.", "nes", "cartridge"),
    Console("snes", "SNES", "Nintendo", 3, (".sfc", ".smc", ".fig"), ("snes", "super nintendo", "super famicom"),
            ("snes9x", "bsnes", "retroarch"), "strong", "Deterministic; the best fit for input lockstep.", "snes", "cartridge"),
    Console("genesis", "Genesis / Mega Drive", "Sega", 4, (".md", ".gen", ".smd"), ("genesis", "mega drive", "megadrive"),
            ("retroarch",), "strong", "Deterministic; lockstep is realistic.", "genesis", "cartridge"),
    Console("gb", "Game Boy", "Nintendo", 5, (".gb",), ("gameboy", "game boy"), ("mgba", "retroarch"),
            "strong", "Link-cable play can be emulated or run as lockstep.", "gb", "cartridge"),
    Console("gbc", "Game Boy Color", "Nintendo", 6, (".gbc",), ("gameboy color", "game boy color", "gbc"),
            ("mgba", "retroarch"), "strong", "Link-cable play can be emulated or run as lockstep.", "gb", "cartridge"),
    Console("ps1", "PlayStation", "Sony", 7, (".cue", ".pbp", ".chd", ".ccd", ".mdf"),
            ("ps1", "psx", "psone", "playstation"), ("duckstation", "retroarch"),
            "experimental", "RetroArch netplay (PCSX-ReARMed core); needs the same BIOS everywhere.", "ps1", "memory-card"),
    Console("n64", "Nintendo 64", "Nintendo", 8, (".z64", ".n64", ".v64"), ("64", "n64", "nintendo 64"),
            ("mupen", "retroarch"), "experimental", "RetroArch netplay (Mupen64Plus-Next core); least stable, expect desyncs.", "n64", "cartridge"),
    Console("gba", "Game Boy Advance", "Nintendo", 9, (".gba",), ("gameboy advanced", "game boy advance", "gba"),
            ("mgba", "retroarch"), "strong", "Deterministic core; lockstep is realistic.", "gba", "cartridge"),
    Console("gamecube", "GameCube", "Nintendo", 10, (".gcm", ".ciso", ".gcz", ".rvz"), ("gamecube", "gc", "game cube"),
            ("dolphin",), "per-game", "Dolphin only; each game needs its own game pack (Mario Party 4 is the first).",
            "gamecube", "memory-card"),
    Console("ps2", "PlayStation 2", "Sony", 11, (".cso", ".zso"), ("ps2", "playstation 2"), ("pcsx2",),
            "per-game", "Possible per game, but timing-sensitive; needs a game pack.", "ps2", "memory-card"),
    Console("xbox", "Xbox", "Microsoft", 12, (".xiso",), ("xbox",), ("xemu",),
            "experimental", "Emulation is young; multiplayer is not planned yet.", "xbox", "internal"),
    Console("ds", "Nintendo DS", "Nintendo", 13, (".nds", ".dsi"), ("ds", "nds", "nintendo ds"), ("melonds", "retroarch"),
            "experimental", "RetroArch netplay (melonDS core) keeps one game in lockstep; wireless play is not simulated.", "ds", "cartridge"),
    Console("psp", "PSP", "Sony", 14, (), ("psp",), ("ppsspp",),
            "per-game", "PPSSPP has ad-hoc multiplayer; support varies.", "psp", "memory-card"),
    Console("wii", "Wii", "Nintendo", 15, (".wbfs", ".wad", ".wia"), ("wii",), ("dolphin",),
            "per-game", "Dolphin only; needs a game pack per game.", "wii", "internal"),
    Console("x360", "Xbox 360", "Microsoft", 16, (".xex", ".xbla"), ("xbox 360", "xbox360", "360"), ("xenia",),
            "not-practical", "Emulation is still limited; multiplayer is not practical yet.", "x360", "internal"),
    Console("3ds", "Nintendo 3DS", "Nintendo", 17, (".3ds", ".cci", ".cia", ".cxi"), ("3ds", "nintendo 3ds"),
            ("azahar", "citra"), "experimental", "Emulation is limited; multiplayer is not planned yet.", "3ds", "cartridge"),
    Console("ps3", "PlayStation 3", "Sony", 18, (".pkg",), ("ps3", "playstation 3"), ("rpcs3",),
            "not-practical", "Emulation is demanding; multiplayer is not practical yet.", "ps3", "internal"),
)

BY_ID = {c.id: c for c in CONSOLES}

# Disc-image and archive types are shared by several consoles; the folder decides.
AMBIGUOUS_EXTENSIONS = {".iso", ".bin", ".img", ".zip", ".7z", ".rar", ".rom"}


def console_for_folder_name(name: str) -> Console | None:
    lowered = name.strip().lower()
    for console in CONSOLES:
        if lowered in console.folder_hints:
            return console
    return None


def console_for_extension(extension: str) -> Console | None:
    lowered = extension.lower()
    for console in CONSOLES:
        if lowered in console.extensions:
            return console
    return None
