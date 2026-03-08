
---

# Path: `docs/ADAPTER_INTERFACE_v1.md`

```md
# Legacy Player Adapter Interface v1

## Purpose

This document defines the conceptual interface for Legacy Player platform adapters.

An adapter is the bridge between the Legacy Player runtime and a platform environment such as an emulator or future hardware bridge.

Adapters must expose structured capabilities to the runtime without leaking platform-specific complexity into the shared runtime core.

---

## Design principles

Adapters must follow these principles:

- expose structured capabilities
- isolate platform-specific logic
- avoid embedding game-specific policy into the adapter core
- support game identity and state observation
- support controlled input and session surfaces
- remain replaceable without forcing runtime redesign

---

## Adapter responsibilities

An adapter is responsible for providing the runtime with access to platform-relevant information and control surfaces.

Core responsibilities include:

- platform identification
- game identification
- version/region fingerprint reporting
- emulator or platform compatibility reporting
- memory/state observation
- input/controller observation
- controlled runtime hook surfaces
- session readiness signals where available

Adapters do not own multiplayer policy.

Adapters do not own replay policy.

Adapters do not define full game behavior rules.

---

## Required capability groups

Every adapter should declare its capabilities in structured form.

### 1. Identity capabilities

The adapter must be able to report:

- adapter name
- adapter version
- platform name
- emulator/runtime name
- emulator/runtime version if available

It should also be able to identify the active title where possible.

### 2. Game fingerprint capabilities

The adapter should expose a game fingerprint model that may include:

- title identity
- region
- revision/version
- content/profile hash or equivalent fingerprint
- compatibility hints

This fingerprint is used by the runtime to select a matching game pack.

### 3. Memory/state observation capabilities

The adapter should expose controlled access to:

- current scene or inferred phase if discoverable
- memory regions of interest
- state variables needed by game packs
- readiness or state markers
- state hash support if possible

The adapter should expose these through structured calls rather than unbounded arbitrary assumptions in the runtime.

### 4. Input/controller capabilities

The adapter should expose:

- active player slots
- controller ownership information if available
- input observation hooks
- controlled input injection or forwarding surfaces where appropriate

### 5. Runtime assistance capabilities

Where supported, the adapter may expose:

- pause/freeze assistance
- frame pacing hooks
- transition barrier hooks
- runtime patch application surfaces
- checkpoint markers

These must remain controlled and explicit.

### 6. Diagnostics capabilities

The adapter should expose:

- capability status
- unsupported feature reasons
- attach/read failures
- compatibility warnings
- adapter health signals

---

## Runtime-to-adapter relationship

The runtime should be able to ask the adapter questions such as:

- what platform are you attached to
- what game is active
- what version/profile is active
- what capabilities do you support
- can you expose requested state fields
- can you support requested session actions
- what failed and why

This relationship should remain declarative and structured.

---

## Adapter-to-game-pack relationship

Game packs depend on adapters to expose the platform surfaces needed for game-specific orchestration.

The adapter should not hardcode the full game pack logic.

Instead:

- the adapter exposes observables and controlled hooks
- the game pack interprets game-specific meaning
- the runtime coordinates the session using both

This separation is mandatory.

---

## Expected adapter lifecycle

A typical adapter lifecycle is:

1. initialize adapter
2. attach to platform environment
3. report adapter/platform identity
4. detect active game fingerprint
5. report supported capabilities
6. expose state and input surfaces
7. support runtime session orchestration
8. emit diagnostics and detach cleanly

---

## Failure behavior

Adapters must fail clearly.

Clear failure examples include:

- adapter unavailable
- emulator unsupported
- game unrecognized
- required capability unavailable
- memory observation unavailable
- controller ownership not supported

Adapters should not pretend support exists when it does not.

---

## First target adapter

The first real adapter target is:

- Dolphin adapter
- GameCube first
- party-game support first

This adapter should aim to prove:

- active title identification
- version/region fingerprinting
- basic state observation
- session-compatible capability reporting

---

## Future adapters

Potential future adapters include:

- mGBA
- RetroArch
- hardware bridge adapters

The interface should remain stable enough that future adapters can plug into the same runtime expectations without redesigning the core architecture.

---

