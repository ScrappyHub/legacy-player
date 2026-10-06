"""RetroArch native-netplay launch adapter.

This is a *launch* adapter: it starts RetroArch with its own netplay (host or
client) and leaves frame synchronisation to RetroArch and the libretro core.
It does not implement Legacy Player's lockstep ControllerAdapter. Legacy Player
supplies the room, the invite, the compatibility check and the host address.

Command-line flags (-L, --host, --connect, --port, --nick, --appendconfig) were verified
against a real RetroArch 1.18 (host + 3 guests, Nestopia core, 60 s soak, no desync).
RetroArch refuses netplay unless the core's .info file says savestate_features =
"deterministic", which is why Setup installs the core info files.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

# console id -> libretro core file stems, best first.
CORES: dict[str, tuple[str, ...]] = {
    "nes": ("nestopia_libretro", "mesen_libretro", "fceumm_libretro"),
    "snes": ("snes9x_libretro", "bsnes_libretro"),
    "gb": ("gambatte_libretro", "mgba_libretro"),
    "gbc": ("gambatte_libretro", "mgba_libretro"),
    "gba": ("mgba_libretro", "vba_next_libretro"),
    "genesis": ("genesis_plus_gx_libretro", "picodrive_libretro"),
    "atari": ("stella_libretro",),
}
CORE_SUFFIXES = {"win32": ".dll", "darwin": ".dylib"}


class NetplayError(RuntimeError):
    pass


def find_core(retroarch_exe: str, console_id: str) -> str:
    stems = CORES.get(console_id)
    if not stems:
        raise NetplayError(f"RetroArch netplay is not set up for this console ({console_id}).")
    suffix = CORE_SUFFIXES.get(sys.platform, ".so")
    exe_dir = Path(retroarch_exe).resolve().parent
    home = Path.home()
    for folder in (
        exe_dir / "cores", exe_dir.parent / "cores", exe_dir.parent / "lib" / "libretro",
        home / ".config" / "retroarch" / "cores",
        home / ".var" / "app" / "org.libretro.RetroArch" / "config" / "retroarch" / "cores",
        home / "Library" / "Application Support" / "RetroArch" / "cores",
    ):
        for stem in stems:
            candidate = folder / f"{stem}{suffix}"
            if candidate.is_file():
                return str(candidate)
    raise NetplayError(
        f"No RetroArch core found for this console. Install one of {', '.join(stems)} "
        f"(RetroArch > Load Core > Download a Core) so it appears in {exe_dir / 'cores'}."
    )


def _check_port(port: int) -> int:
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise NetplayError("port must be a whole number from 1024 to 65535")
    return port


def _nick(nick: str) -> str:
    cleaned = "".join(c for c in nick if c.isalnum() or c in "-_ ")[:24].strip()
    return cleaned or "Player"


def build_host_command(exe: str, core: str, rom: str, port: int = 55435, nick: str = "Host",
                       extra: list[str] | None = None) -> list[str]:
    return [exe, "-L", core, rom, "--host", "--port", str(_check_port(port)), "--nick", _nick(nick)] + list(extra or [])


def build_solo_command(exe: str, core: str, rom: str, extra: list[str] | None = None) -> list[str]:
    return [exe, "-L", core, rom] + list(extra or [])


def build_guest_command(exe: str, core: str, rom: str, address: str, port: int, nick: str = "Guest",
                        extra: list[str] | None = None) -> list[str]:
    if not address or address.startswith("-") or any(c.isspace() for c in address):
        raise NetplayError("invalid host address")
    return [exe, "-L", core, rom, "--connect", address, "--port", str(_check_port(port)), "--nick", _nick(nick)] + list(extra or [])


def detect_lan_address() -> str:
    """Best-effort LAN address of this computer (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
