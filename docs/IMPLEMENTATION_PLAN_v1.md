# Legacy Player Implementation Plan v1

## Purpose

This document defines the initial implementation path for Legacy Player.

It turns the public architecture and project framing into a practical build sequence that can move the project from fresh repo state into first technical proof.

This plan is intentionally narrow.

Legacy Player will not begin as a universal solution for all legacy games. It will begin as a disciplined runtime with one adapter path and one first-class game target.

---

## First implementation objective

The first implementation objective is:

**prove that Legacy Player can orchestrate a real online session for one legacy game through an emulator adapter, with explicit compatibility checks, synchronization boundaries, and replay/diagnostic capture.**

This first proof matters more than wide platform coverage.

---

## Initial scope lock

### Platform

- GameCube

### Emulator

- Dolphin

### Game class

- Party games

### First flagship target

- Mario Party 4 or Mario Party 6

### Session model

- private self-hosted sessions first
- no public discovery requirement for initial proof

### Synchronization model

- deterministic input lockstep
- runtime-assisted synchronization barriers where required

---

## Why this scope

This scope is intentionally chosen because it is realistic and high value.

Party games provide:

- discrete session phases
- obvious scene boundaries
- simpler readiness transitions
- less punishing latency expectations than frame-exact fighters
- strong community recognition

This makes them a strong first proof target.

---

## Implementation principles

The first implementation must follow these rules.

### Rule 1 — Keep runtime, adapter, and game-pack logic separate

Do not allow:
- game-specific logic inside the shared runtime
- emulator-specific assumptions inside game packs
- runtime policy leaking into adapter internals

### Rule 2 — Replay and diagnostics are first-class from day one

Even the earliest prototype should record:
- session metadata
- readiness transitions
- key synchronization boundaries
- state mismatch events
- failure reasons

### Rule 3 — Build for explainable failure

The system must prefer:

- "unsupported"
- "incompatible"
- "mismatch detected"
- "boundary violation"

over undefined behavior or silent drift.

### Rule 4 — Narrow before broad

One real supported path is more valuable than many weak claims.

---

## Initial implementation phases

## Phase 0 — Repo skeleton and contracts

Goals:

- create runtime folder structure
- create adapter folder structure
- create game pack folder structure
- publish interface documents
- publish initial first-target document

Outputs:

- repo structure established
- interfaces defined
- first technical path documented

Status target:

- public repo can clearly explain what will be built next

---

## Phase 1 — Core runtime skeleton

Goals:

- establish session runtime module boundaries
- establish replay event model
- establish desync event model
- establish compatibility validation flow
- establish ready-state barrier flow

Minimum outputs:

- runtime/session module skeleton
- runtime/sync module skeleton
- runtime/state module skeleton
- runtime/desync module skeleton
- runtime/replay module skeleton
- basic runtime event schema draft

Success condition:

- runtime can model a session lifecycle in code even before a live emulator is integrated

---

## Phase 2 — Dolphin adapter foundation

Goals:

- define Dolphin adapter contract
- identify supported game instance
- expose basic game identity and version fingerprint
- expose basic memory/state read surfaces
- expose controller/input interception surfaces

Minimum outputs:

- adapters/dolphin module skeleton
- game identification logic
- adapter status reporting
- memory probe proof
- session-compatible adapter interface implementation

Success condition:

- Legacy Player can attach to a Dolphin-driven target and identify the game/profile in a structured way

---

## Phase 3 — First game pack foundation

Goals:

- create first Mario Party game pack
- define scene model
- define synchronization boundaries
- define compatibility rules
- define initial replay markers

Minimum outputs:

- game_packs/mario_party_x pack skeleton
- identity profile
- state model
- boundary model
- compatibility rule set

Success condition:

- runtime can load the game pack and reason about expected states and boundaries

---

## Phase 4 — First orchestrated session proof

Goals:

- create private session
- join participants
- validate compatibility
- reach synchronized ready state
- detect first meaningful boundary transitions
- record replay metadata
- log diagnostics

Minimum outputs:

- first session lifecycle implementation
- ready barrier proof
- first active-session proof
- replay event output
- mismatch or boundary failure output

Success condition:

- a real controlled multiplayer proof exists, even if limited

---

## Phase 5 — Runtime-assisted support

Goals:

- add menu synchronization barriers
- add scene transition coordination
- add controller slot ownership rules
- add critical state checks
- add first mismatch detection behavior

Minimum outputs:

- runtime-assisted boundary coordination
- first state hash/checkpoint logic
- first desync diagnostic flow

Success condition:

- system can help stabilize multiplayer instead of only observing it

---

## Phase 6 — Replay and diagnostics strengthening

Goals:

- define replay package shape
- define diagnostic artifact shape
- define mismatch reporting structure
- define state marker history model

Minimum outputs:

- replay package draft
- desync event format
- session summary format
- replay inspector planning surface

Success condition:

- every session produces useful artifacts for debugging and growth


---

Immediate build sequence

The immediate next work should happen in this order:

lock adapter interface

lock game-pack interface

lock first target document

create runtime skeleton

create Dolphin adapter skeleton

create first Mario Party game pack skeleton

build memory probe proof

build first session orchestration proof

strengthen replay and diagnostics

This order should remain stable until first proof exists.

Explicit non-goals for first proof

The first proof does not need:

public matchmaking

polished UI

broad platform support

hardware bridge support

universal patching

tournament features

rollback netcode

support for many games

The first proof needs one narrow success.

First proof definition of success

Legacy Player first proof is successful when all of the following are true:

the runtime can create and model a multiplayer session

the Dolphin adapter can identify a supported game and expose structured state

the first Mario Party game pack can declare boundaries and compatibility rules

the runtime can hold a synchronized ready barrier before active play

the system records replay and diagnostic metadata

failure conditions are explicit and explainable


---

## Initial folder implementation target

```text
legacy-player/
├─ docs/
├─ runtime/
│  ├─ session/
│  ├─ sync/
│  ├─ state/
│  ├─ desync/
│  ├─ replay/
│  └─ patch/
├─ adapters/
│  └─ dolphin/
├─ game_packs/
│  └─ mario_party_4/
├─ server/
│  ├─ lobby/
│  ├─ relay/
│  └─ api/
└─ tools/
   ├─ memory_probe/
   ├─ replay_inspector/
   └─ pack_builder/
