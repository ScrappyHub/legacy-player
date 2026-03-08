# Legacy Player Runtime

## Purpose

The runtime is the shared multiplayer orchestration layer of Legacy Player.

It is responsible for coordinating sessions, synchronization behavior, replay capture, desync detection, and controlled runtime assistance across supported adapters and game packs.

The runtime must remain game-agnostic at the core.

It should not hardcode platform-specific behavior or game-specific rules.

---

## Responsibilities

The runtime is responsible for:

- session lifecycle orchestration
- readiness and boundary coordination
- synchronization policy execution
- replay event capture
- desync detection and diagnostics
- compatibility validation flow
- coordination of controlled patch/runtime assistance

---

## Internal modules

The runtime is organized into the following module areas:

### `session/`

Session creation, participant membership, readiness state, topology metadata, and lifecycle flow.

### `sync/`

Synchronization strategy, input timing policy, boundary enforcement, and active simulation coordination.

### `state/`

Shared state observation contracts, runtime-visible state markers, and compatibility-relevant runtime surfaces.

### `desync/`

Mismatch detection, divergence reporting, failure reason handling, and diagnostic event capture.

### `replay/`

Replay event capture, session metadata recording, state hash markers, and replay package generation.

### `patch/`

Controlled runtime assistance coordination for game packs that require transition barriers, ownership remaps, or other online orchestration help.

---

## Design rule

The runtime must be built as shared infrastructure.

It must not become a container for one-off game hacks.

If game-specific behavior is needed, it belongs in a game pack.

If platform-specific behavior is needed, it belongs in an adapter.

---

## First implementation role

The first runtime proof should be able to:

- create and model a session
- hold a synchronized ready barrier
- load a matching adapter and game pack
- record replay metadata
- emit explicit mismatch and failure diagnostics

This is enough to prove the runtime foundation is real.
