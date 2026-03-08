# Legacy Player Runtime Spec v1

## Purpose

The Legacy Player runtime is the central multiplayer orchestration layer of the project.

It is responsible for coordinating online sessions for legacy games across adapters and game packs.

The runtime must be reusable, game-agnostic at the core, and strict about boundaries between shared infrastructure and game-specific logic.

---

## Design goals

The runtime must:

- manage multiplayer sessions
- coordinate peers and readiness
- synchronize input or simulation boundaries
- inspect and validate critical state
- support replay logging
- support desync detection
- allow controlled game-pack-driven assistance
- remain reusable across platforms and game classes

---

## Non-goals

The runtime is not:

- a ROM distribution layer
- a proprietary game asset layer
- a generic cheat engine
- a replacement for emulator implementation itself
- a promise of universal support for all titles

---

## Runtime responsibilities

### Session orchestration

The runtime must support:

- session creation
- session join/leave
- host/direct/relay metadata
- readiness barriers
- session identity
- participant metadata

### Compatibility validation

The runtime must be able to validate:

- game identity
- version/region profile
- adapter compatibility
- emulator compatibility
- game pack compatibility
- optional save/profile compatibility

### Synchronization

The runtime must support a primary synchronization strategy.

Initial expected strategy:

- deterministic input lockstep

Possible future strategies:

- rollback
- hybrid lockstep/rollback
- checkpoint-assisted recovery

### State observation

The runtime must be able to receive and reason over:

- current scene/phase
- player membership state
- critical memory region values
- state hashes
- simulation markers
- known transition points

### Desync handling

The runtime must support:

- early mismatch detection
- state divergence reporting
- diagnostic artifact generation
- clean session stop policies
- future safe-boundary recovery support

### Replay support

The runtime must support:

- session metadata recording
- input log recording
- state hash checkpoints
- deterministic event markers
- replay package export

---

## Runtime boundaries

The runtime must not hardcode game logic into the shared core.

Game-specific logic belongs in game packs.

Platform-specific emulator logic belongs in platform adapters.

This separation is mandatory.

---

## Initial session lifecycle

1. Session created
2. Players join
3. Adapter identifies platform/game/version
4. Game pack is selected
5. Compatibility checks run
6. Ready barrier reached
7. Session enters active simulation
8. Runtime records inputs and state markers
9. Runtime detects mismatches or completes session
10. Replay/log artifacts are finalized

---

## Required internal modules

The runtime should contain at minimum:

- session module
- sync module
- state module
- desync module
- replay module
- patch coordination module

---

## Failure policy

The runtime must fail clearly when:

- no matching adapter exists
- no matching game pack exists
- incompatible versions are detected
- critical state mismatches occur
- required synchronization boundaries are violated

The runtime should prefer clean, explainable failure over undefined behavior.

---

## Replay policy

Replay artifacts should be treated as first-class outputs.

A replay should be able to support:

- review
- debugging
- tournament archival
- future spectator tools
- long-term preservation use cases

---

## Strategic note

The runtime is the real heart of Legacy Player.

If designed correctly, it can later inform multiplayer foundations for CDE and related future systems.
