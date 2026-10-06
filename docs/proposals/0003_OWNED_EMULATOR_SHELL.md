# Proposal 0003: The owned emulator shell (Phase 4)

Status: proposed, first slice implemented. Builds on 0002 (phases 1-3 implemented).

## Goal (from the product owner)

One program the player opens, that looks and behaves like a console: every supported
system runs *inside* it, it finds or fetches the engines it needs, it knows which BIOS files
a console needs and where the player's own copies are, and it never reaches the network
or scans the computer without the player saying so.

## What "owned emulator" means, honestly

Writing new emulation cores for 18 consoles is not realistic; the community cores took
decades. "Owned" here means Legacy Player owns the **shell**: the library, the controller
model, saves, multiplayer, the engine registry and the lifecycle of each engine. The engines
stay the upstream projects, under their own licenses, run as child processes today.

Two routes exist to bring engines *in-process* later, and the registry is built to allow both:

1. **libretro frontend** (recommended next step). RetroArch's cores are plain shared
   libraries with a stable C API. A Legacy Player frontend (loading cores with ctypes, with
   SDL2 for video/audio/input) would give one window, one controller model, save states and
   netplay hooks for every libretro core: NES, SNES, GB/GBC/GBA, Genesis, Atari, PS1, N64,
   DS, PSP (PPSSPP core), GameCube/Wii (Dolphin core, experimental), 3DS (Citra core).
   Cost estimate: 4-6 weeks for a usable frontend; the netplay lockstep in `runtime/` is
   already designed for exactly this input model.
2. **Standalone engines as managed children** (what ships now). PCSX2, RPCS3, xemu and
   Xenia have no libretro core worth using; they stay separate programs the shell launches,
   configures (save folders, controller hints) and supervises.

## Implemented in this slice

- `launcher/engines.py`: registry of 15 engines with official source (GitHub repo + asset
  rule, or official page), licenses, consoles served, BIOS needs; read-only, bounded
  scan of the usual program folders (Program Files, LocalAppData, user folders, extra
  drives); BIOS finder by file pattern and size for PS2, PS1, DS, Xbox, PS3.
- `launcher/installer.py`: downloads from official GitHub releases only
  (api.github.com, github.com, GitHub's file hosts; off-site redirects refused; size caps;
  zip/7z unpack with path-escape checks; nothing executed afterwards).
- Consent gate: Settings > Privacy > "Allow internet downloads" (default **off**) plus a
  per-action confirm. The RetroArch Setup page uses the same gate. Scanning the computer
  is a button, never automatic.
- UI: **Engines** tab and **Console mode** (big tiles, d-pad/face buttons/keyboard).

## Not done, and why

- **BIOS downloads: will not be built.** PS2/PS1/Xbox/DS system software is the console
  makers' copyrighted code. The shell finds the player's own dumps and explains how to dump
  them. The one exception is the PS3 firmware, which Sony publishes for download; the shell
  points to RPCS3's installer for it.
- **Vimm's Lair as an engine source: not used.** Vimm's emulator mirror is third party;
  the shell only downloads from each project's own release channel so the integrity story
  is "TLS to the project", not "TLS to a mirror". A player can still drop a Vimm download
  into an emulator folder and add that folder in Emulators.
- **Dolphin, Mupen64Plus, RetroArch** have no suitable GitHub release asset; they link to
  their official download pages (RetroArch is handled by Setup from buildbot.libretro.com).
- Asset name rules in the registry are written from each project's current release naming
  and are **unverified until a real download** on a Windows machine; a mismatch gives a
  clear "no recognised package" message with the project page, never a wrong file.

## Canonical impact

No change to the service role, trust boundaries or schemas. New user-facing network
behaviour is opt-in and documented here; if the canonical IDENTITY/SPEC later states a
stricter no-network rule, the "Allow internet downloads" switch must default to off (it does)
and the Setup/Engines pages must remain the only callers of `launcher.installer` and
`launcher.setup.download`.
