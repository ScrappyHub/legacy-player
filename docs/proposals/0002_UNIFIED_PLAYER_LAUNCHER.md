# Proposal 0002 — Unified Player: library, launcher and community server

**Status:** Proposed (not approved; canonical files unchanged)
**Date:** 2026-10-06
**Depends on:** Proposal 0001 (classification)
**Affected service:** `legacy-player`

## Request

The operator wants Legacy Player to grow from a Dolphin-first multiplayer runtime into an
all-in-one player that: categorizes and launches a personal game library across
NES to PS3-era consoles; adapts controller mappings per console; stores favorites,
settings and save files; hosts self-run multiplayer servers (Windows, Linux, Raspberry Pi)
with encrypted private invite codes and join/leave/kick/disconnect notifications; and,
once proven, ships as one console-like application that embeds the emulator engines.

## Conflicts with current canonical text

Proposal 0001 lists as **not owned**: emulator execution/implementation, public matchmaking
identity, and internet-scale abuse prevention (Tier-0). This request touches all three.

## Proposed resolution

1. **Embed, do not reimplement.** Legacy Player stays out of emulator implementation. The
   "owned emulator" is a *shell* that launches and supervises existing cores
   (Dolphin, PCSX2, mGBA, RetroArch cores, etc.) through adapters. Any from-scratch core
   is a separate future proposal.
2. **Three new owned responsibilities:** (a) local game library and metadata (read-only
   scan of user-owned files; nothing copied or distributed); (b) per-console controller
   profile mapping; (c) private-group hosting: invites, join approval, kick, presence.
3. **Still not owned:** public matchmaking, accounts and internet-scale abuse prevention.
   Hosting is private-group, operator-run, invite-only.
4. **Legal posture unchanged:** no ROMs, ISOs, BIOS or firmware bundled. The library only
   indexes files the user already has (see `LEGAL_POSITION.md`).

## Phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Server: invites, approval, kick, leave, presence, notifications, TLS, stop/restart/resume | Implemented in this change |
| 2 | Library scanner + launcher UI: console categories, favorites, settings, save backups, per-console controller profiles, room UI | Implemented (see `docs/LIBRARY_AND_LAUNCHER_v1.md`) |
| 3 | Adapters beyond Dolphin and per-platform netplay | 3a implemented: RetroArch native-netplay launch for NES/SNES/GB/GBC/GBA/Genesis/Atari. 3b implemented: guided Dolphin NetPlay for GameCube/Wii and a Setup page that checks and installs RetroArch and cores. 3c implemented: any-pad identify/map, managed save folders, encrypted RetroArch tunnel. Still planned: other consoles |
| 4 | Unified shell packaging as a console-like app | See proposals 0003 and 0004. Started: PyInstaller app (`build_exe.bat`), app window, embedded server control. Embedding emulator engines remains future work |

## Honest limits to record

- Lockstep multiplayer is not equally feasible on every console. NES-SNES-GBA via
  deterministic cores are strong; GameCube/Wii/PS2 depend on per-game packs; PS3/Xbox 360
  are not realistic near term. Support is tiered per game pack (A/B/C), never claimed globally.
- Frames are not snapshotted across a server restart. Seats, credentials, invites and
  notifications survive; an interrupted active match returns to the ready barrier.
- Invite codes are bearer secrets (50 bits, expiring, use-limited, rate-limited, stored as
  keyed hashes). They are encrypted in transit only when the server runs with TLS.

## Compatibility impact

Additive wire operations (`invite`, `revoke_invites`, `join` via `invite_code`, `join_status`,
`decide_join`, `kick`, `leave`, `heartbeat`, `events`); the original `join_code` flow still works.
Join codes and credentials are now stored as digests. Registry/service-map updates are
deferred until this proposal is approved.
