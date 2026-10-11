# Legacy Player

A self-hosted, console-like launcher for legacy games. It finds your games, starts them in the right emulator, maps your
controllers, backs up your saves, and lets friends play together online with one server code and room invite codes.

Legacy Player does not include any game content, BIOS files or emulators. You use your own legally obtained games; the app
can download emulators from their official release pages when you ask it to.

## Install (Windows)

PowerShell, no administrator needed. Either one line:

```powershell
irm https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/install.ps1 | iex
```

From **Command Prompt (cmd)**, **Windows Terminal**, **Git Bash** or **WSL** (anything that can run `powershell.exe`), the same install in one line:

```
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/install.ps1 | iex"
```

(In Git Bash or WSL write `powershell.exe` instead of `powershell`.) Legacy Player is a Windows app, so there is no macOS or Linux install.

or, through git, with the small `lp` command that comes with the repository:

```powershell
git clone https://github.com/Alpallyoop/legacy-player
cd legacy-player
.\lp.cmd install        # newest release; or  .\lp.cmd install v0.7.43  for one exact version
.\lp.cmd run            # later:  .\lp.cmd update | version | path | uninstall | help
```

In PowerShell type `.\lp.cmd`: a plain `.\lp` runs `lp.ps1`, which Windows' default execution policy (Restricted) refuses
to run. `lp.cmd` starts it with `-ExecutionPolicy Bypass` for you. In Command Prompt plain `lp install` works. Without
`lp.cmd`: `powershell -ExecutionPolicy Bypass -File .\lp.ps1 install`.

Both download the release from [Releases](https://github.com/Alpallyoop/legacy-player/releases), check its SHA-256, install to
`%LOCALAPPDATA%\Programs\LegacyPlayer`, add a Start menu shortcut and open the app. Or download the files yourself: each
release has `LegacyPlayer-<version>-win64.zip` (the exe plus a read-me) and the bare `LegacyPlayer-<version>-win64.exe`, each
with a `.sha256` and a combined `SHA256SUMS.txt`. Releases are signed only once a code-signing certificate has been added (see
`docs/RELEASE.md`); until then Windows SmartScreen says "unknown publisher": More info, then Run anyway. Every release lists its
SHA-256 hashes and carries a GitHub build attestation. See `docs/RELEASE.md`.

## What it does

- **Library:** scans your folders, recognises 18 consoles (NES to PS3), covers, collections, favorites, per-game settings.
  Each game shows how many people can play it and whether it is single-player, co-op or versus.
- **Emulators:** finds or installs them (RetroArch, Dolphin, mGBA, DuckStation, PCSX2 and others), full-screen and
  controller options per emulator, Dolphin pad profiles written for you (and restorable).
- **Quick play:** hover a game's cover and it splits into Play and Online (host a room or join with a code).
- **Play options:** before a game opens (or any time from "Play with options…"): full screen or a window, which screen,
  resolution, borderless, vsync, sharp pixels and the rest, plus "Optimize for my computer". Remember it per emulator or be asked.
- **Legacy Player World themes:** eight original places (Martin's Meadow, Pixel Harbor, Ember Peaks, Frostfall, Mirage Dunes,
  Glimmerwood, Neon Arcade, Cloudtop Isles), each with its own day and night colours and an animated 8-bit scene behind
  the app. Day, Night, or Follow my clock (day from 7:00 to 19:00).
- **Game cards:** in Console mode each game opens a card with region, revision, players, release date, makers and a
  description (looked up from Wikipedia/Wikidata only when you ask; you can write your own).
- **Friends (optional):** a separate friends service with friend codes, who is online, room invites and messages. No accounts.
  Only friends can message you; requests need your code and can be switched off. Report a player or a single message,
  block, and a word filter you can turn on or off (Settings > Friends). Run your own service with one click (Friends >
  Run a friends service on this computer): encrypted, router port opened for you, and you moderate it right there
  (reports, time-outs, bans, word filter). No commands (`docs/HOSTING_PUBLIC_SERVER.md`).
- **Updates:** Account > Update everything (or Check for updates) downloads the new Legacy Player, checks it, and
  restarts on it. A copy run from a git folder pulls and restarts instead.
- **See an issue or a problem?** on the Home page writes a categorised report (scrubbed first). It is sent only when a
  report address is set (Settings > Privacy > Send reports to). Released builds have none built in, so until one is set the
  report stays on your computer (Settings > Problem reports).
- **Games open where you want:** in front of Legacy Player, full screen or windowed, on the screen you pick (asked once per emulator,
  changeable under Display and video > Where games open).
- **In-game overlay:** press Ctrl+Shift+L, or hold Back + Start on an Xbox-style controller, for a small window over any game with
  Force quit, full screen/windowed and your room code. Both binds can be changed in Settings. Force quit also sits next to
  "game running" in the app.
- **Controllers:** pad and keyboard mapping per console, up to four players.
- **Saves:** finds each emulator's save files, one-click backups and restores.
- **Play together:** everything is on the Servers page: join a friend's server, your server and Server info (with the
  network test) side by side, and the rooms below.
  - Start the server with "Let friends connect". The app asks your router (UPnP) to open the port, adds the Windows
    Firewall rule, and puts your public address in a short server code (`LP-...`). Friends paste the code to connect.
  - Rooms have invite codes, approval, a waiting line and open rooms. Game traffic is encrypted between players.
  - If your connection cannot be reached from outside (hotspot, provider-shared address), the app moves to a shared relay
    server when one is set (see `docs/HOSTING_PUBLIC_SERVER.md`).
- **Problem reports (opt in):** off by default. If something fails, the app asks once and shows exactly what would be sent;
  names, IP addresses, codes and folder paths are removed first (`docs/proposals/2026-10-07-audit-and-fixes.md`).
- **Tools:** computer specs, network check, Dolphin memory probe (any GameCube or Wii game), storage by console, a doctor
  that checks what is missing, and an uninstaller that removes only what Legacy Player created. The doctor asks whether to keep or delete the save folders he made, and leaves you a prescription.
- Close the window with X and it stays in the tray with the server running; right-click the tray icon for server controls.

## Honest status

What is verified: the launcher, library, saves, settings, server, rooms and relay code are covered by automated tests
(more than 500) and a headless-browser click-through of every page.

What is not yet verified on real hardware: the Windows pieces (tray menu, Recycle Bin move, Dolphin pad names, firewall
rule, memory probe), opening a real router, a real shared server, and actual online play between two networks. Netplay
quality varies by console: NES, SNES, Genesis, Game Boy and GBA are the best fit; N64, PS1 and DS are experimental;
GameCube and Wii work per game and need a game pack (Mario Party 4 is the first). See `docs/NETPLAY_BY_CONSOLE.md`,
`docs/WINDOWS_CHECKLIST.md` and `docs/MULTIPLAYER_TEST_PLAN.md`.

## Run from source

Python 3.13+ (the Dolphin memory probe also needs `pip install psutil`; the packaged exe already has it):

```powershell
python -m launcher --games "D:\Games"       # opens the app; add folders inside it too
python -m server.cli start --port 8765       # a standalone server (see docs/HOSTING_PUBLIC_SERVER.md)
python -m unittest discover -s tests         # the tests
.\build_exe.bat                              # builds dist\LegacyPlayer.exe
powershell -File tools\package_release.ps1   # builds the release zip
```

## Repository layout

```text
launcher/     the app: library, emulators, controllers, saves, settings, tray, UI (launcher/ui/index.html)
server/       lobby and room service, relay, admin CLI, problem-report receiver
adapters/     emulator adapters (Dolphin, RetroArch) and netplay launch logic
runtime/      session, sync, state, desync and replay engine
frontend/     input and controller delivery
game_packs/   per-game data (Mario Party 4 first)
tools/        memory probe, release packaging, report reader, Windows self-check, contrast check
docs/         specs, plans, decisions, audits, release and test guides
tests/        automated tests
```

## How it is designed

Legacy Player is a common multiplayer runtime plus platform adapters plus per-game packs plus self-hostable
infrastructure. It is not one plugin that magically works for every game. Support comes in tiers:

- **Tier A, native sync:** games that already work under emulator lockstep. Legacy Player adds hosting, rooms,
  compatibility checks, diagnostics.
- **Tier B, runtime assisted:** games that need menu barriers, controller remapping or state checks.
- **Tier C, full conversion:** games that need heavy orchestration to become remotely playable.

Read `docs/ARCHITECTURE.md`, `docs/RUNTIME_SPEC_v1.md` and `docs/GAME_PACK_SPEC_v1.md`; the documentation index is
`docs/PROJECT_DOCUMENTATION_INDEX.md`.

## Legal position

Legacy Player is an interoperability project. It does not distribute copyrighted game data, proprietary assets, ROMs,
ISOs or BIOS files, claim ownership of any game, or require redistribution of game binaries. Users bring their own legally
obtained games and emulator environments. See `docs/LEGAL_POSITION.md`.

## Venture Lab role

Legacy Player is a Venture Lab project with product and research value: a real multiplayer instrument for classic games,
self-hosted community infrastructure, and a multiplayer knowledge base for the Clio Development Engine (CDE).

## License, privacy and security
MIT licensed (`LICENSE`; third-party notes in `THIRD_PARTY.md`). What the app does with information: `PRIVACY.md` (nothing leaves
your computer unless you choose). Reporting a vulnerability: `SECURITY.md`. Code signing: `docs/CODE_SIGNING_POLICY.md`.
