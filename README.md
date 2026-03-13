
# Legacy Player

Self-hosted multiplayer infrastructure for legacy games.

Legacy Player is a Venture Lab instrument for bringing stable online multiplayer to classic games that originally supported local-only play. It does this through emulator adapters, game-specific runtime orchestration, deterministic session synchronization, replay logging, and self-hosted server infrastructure.

Legacy Player does **not** include game content. It is an interoperability and multiplayer runtime project.

---

## What this is

Legacy Player is a multiplayer simulation orchestration runtime for legacy games.

It is designed to support:

- self-hosted online sessions
- emulator-integrated multiplayer
- game-specific synchronization adapters
- deterministic replay logging
- desync detection and diagnostics
- memory and state inspection
- runtime patch assistance for games that need multiplayer help

Legacy Player begins with legacy games and emulator integrations, but it also serves as a multiplayer research foundation for future systems such as Clio Development Engine (CDE).

---

## Why this exists

Many older games were designed for:

- couch multiplayer
- split-screen play
- local controller ports
- no internet latency
- no remote synchronization layer

Some emulator netplay solutions already exist, but they are usually:

- emulator-specific
- difficult to configure
- not self-host infrastructure oriented
- not game-aware
- not designed as a reusable multiplayer runtime

Legacy Player exists to provide a stronger foundation:

- a common session runtime
- platform adapters
- game packs
- self-hostable infrastructure
- replay and diagnostics surfaces

---

## Core idea

Legacy Player is not "one universal plugin that magically works for all games."

Legacy Player is:

- a common multiplayer runtime
- plus platform adapters
- plus game-specific strategy packs
- plus self-host server infrastructure

This lets the project scale in a disciplined way.

---

## Project goals

Legacy Player aims to provide:

- self-hosted multiplayer for legacy games
- a reusable runtime for session orchestration
- deterministic input synchronization
- desync detection and recovery surfaces
- runtime patch assistance where needed
- replay logging and spectator foundations
- a research path toward future multiplayer systems

---

## Initial focus

Initial MVP direction:

- Platform: GameCube
- Emulator: Dolphin
- First game class: party games
- First flagship target: Mario Party

Why this path:

- strong community interest
- discrete game phases
- clearer synchronization boundaries
- easier first multiplayer proof than frame-exact competitive fighters

---

## Architecture

Legacy Player consists of four major layers:

1. Core runtime
2. Platform adapters
3. Game packs
4. Self-hosted server infrastructure

See:

- `docs/ARCHITECTURE.md`
- `docs/RUNTIME_SPEC_v1.md`
- `docs/GAME_PACK_SPEC_v1.md`

---

## Support tiers

Legacy Player support is expected to evolve in three tiers.

### Tier A — Native Sync

Games that already behave well under emulator-assisted lockstep.

Legacy Player adds:

- session hosting
- self-hosted relay/lobby services
- compatibility validation
- replay logs
- diagnostics

### Tier B — Runtime Assisted

Games that mostly work but need online orchestration help.

Legacy Player adds:

- menu synchronization barriers
- controller ownership remapping
- memory/state checks
- scene transition coordination
- selective runtime patching

### Tier C — Full Multiplayer Conversion

Games that need heavy orchestration to become remotely playable.

Legacy Player may add:

- deep runtime assistance
- state coordination logic
- custom sync boundaries
- stronger recovery/resync flows
- specialized game pack hooks


---

Long-term significance

Legacy Player is not only a retro multiplayer project.

It is also:

a multiplayer research platform

a replay and diagnostics platform

a self-hosted gaming infrastructure project

a precursor to future multiplayer systems in CDE

By solving multiplayer outside the engine first, Legacy Player helps establish stronger multiplayer foundations for future game development.

Legal position

Legacy Player is an interoperability project.

It does not:

distribute copyrighted game data

include proprietary assets

ship ROMs or ISOs

claim ownership of game IP

require redistribution of game binaries

Users are expected to use their own legally obtained game data and emulator environments.

See docs/LEGAL_POSITION.md.

Status

Fresh repo bootstrap.

Initial work to lock:

architecture

runtime spec

game pack spec

legal position

roadmap

After spec lock, the first implementation target is a Dolphin adapter and a first party-game game pack.

Venture Lab role

Legacy Player is a Venture Lab project with both product and research value.

It is intended to become:

a real multiplayer instrument for classic games

a self-hosted community infrastructure surface

a multiplayer knowledge foundation for Clio Development Engine (CDE)


---

## Repository structure

```text
legacy-player/
├─ README.md
├─ LICENSE
├─ .gitignore
├─ docs/
│  ├─ VENTURE_LAB_PITCH.md
│  ├─ ARCHITECTURE.md
│  ├─ RUNTIME_SPEC_v1.md
│  ├─ GAME_PACK_SPEC_v1.md
│  ├─ LEGAL_POSITION.md
│  └─ ROADMAP.md
├─ runtime/
│  ├─ session/
│  ├─ sync/
│  ├─ state/
│  ├─ patch/
│  ├─ desync/
│  └─ replay/
├─ adapters/
│  ├─ dolphin/
│  ├─ mgba/
│  └─ retroarch/
├─ game_packs/
│  ├─ mario_party_4/
│  └─ mario_party_6/
├─ server/
│  ├─ lobby/
│  ├─ relay/
│  └─ api/
└─ tools/
   ├─ memory_probe/
   ├─ replay_inspector/
   └─ pack_builder/

---
=======
\## Current Legacy Player milestone



Legacy Player now has a working emulator observation foundation for Mario Party 4 on Dolphin.



Proven capabilities:



\- Dolphin process attach

\- game fingerprint detection

\- GMPE01 / USA profile identification

\- active window title selection

\- readable host memory region inventory

\- candidate dynamic region selection

\- repeated region sampling with stable hashes

\- mutation-capture tooling for controlled in-game state discovery



This is the observation and modeling foundation required before full multiplayer synchronization and self-hosted session transport.

(Add Dolphin probe, memory discovery, and mutation capture for Mario Party 4)
