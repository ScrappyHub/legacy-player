# Legacy Player Architecture

## Overview

Legacy Player is a multiplayer simulation orchestration runtime for legacy games.

Its architecture is intentionally layered so the project can support many games and platforms without becoming an unmaintainable collection of one-off hacks.

---

## Architectural layers

### 1. Core Runtime

The core runtime provides shared multiplayer infrastructure.

Responsibilities include:

- session lifecycle
- peer coordination
- input synchronization
- readiness barriers
- compatibility validation
- desync detection
- replay logging
- diagnostics

The runtime must remain platform-agnostic.

---

### 2. Platform Adapters

Platform adapters connect Legacy Player to emulator or hardware environments.

Examples:

- Dolphin adapter
- mGBA adapter
- RetroArch adapter
- future hardware bridge adapters

Responsibilities include:

- memory access
- controller/input interception
- emulator state inspection
- game identity and fingerprint reporting
- runtime hook compatibility

---

### 3. Game Packs

Game packs contain game-specific orchestration logic.

A game pack may define:

- memory regions of interest
- scene and phase detection
- synchronization boundaries
- safe start conditions
- compatibility requirements
- patch assistance rules
- replay metadata labels

Game packs are not arbitrary script dumps. They are structured data and controlled logic surfaces that plug into the runtime.

---

### 4. Server Infrastructure

Server infrastructure supports self-hosted multiplayer.

Services may include:

- lobby service
- relay service
- matchmaking surfaces
- session directory
- replay storage
- admin tools

The server layer is optional for strictly private/direct sessions but is central to the long-term self-host model.

---

## Architectural principle

Legacy Player should be built as:

**one runtime, many adapters, many game packs**

Not:

**one-off custom code per game**

This principle is critical for long-term maintainability.

---

## Session model

A typical session flow is:

1. Create or discover session
2. Join players
3. Identify game and version
4. Load adapter
5. Load game pack
6. Validate compatibility
7. Reach synchronized ready state
8. Enter simulation
9. Monitor state and desync
10. End session and persist replay/logs

---

## Runtime engines

Legacy Player should center around six internal engines.

### Session Engine

Handles:

- session creation
- player membership
- host/peer roles
- readiness state
- topology metadata

### Sync Engine

Handles:

- input lockstep
- frame pacing
- latency window behavior
- pause/recovery mechanics
- synchronization barriers

### State Engine

Handles:

- memory/state inspection
- scene detection
- critical field observation
- state fingerprints
- compatibility surfaces

### Patch Engine

Handles:

- runtime-only assistance
- controller ownership remaps
- transition barriers
- known game-specific correction rules
- selective orchestration hooks

### Desync Engine

Handles:

- critical state hashing
- mismatch detection
- drift identification
- diagnostics capture
- failure or recovery policies

### Replay Engine

Handles:

- input logs
- checkpoint metadata
- session metadata
- state hash records
- replay package outputs

---

## Support tiers

### Tier A — Native Sync

For games that only need standardized session and replay infrastructure.

### Tier B — Runtime Assisted

For games that need online orchestration help.

### Tier C — Full Multiplayer Conversion

For games that need substantial runtime assistance to become viable online.

---

## First implementation target

The first implementation target should be:

- Dolphin adapter
- party-game game pack
- self-hosted session flow
- replay and desync logging

This gives the project a realistic first proof.

---

## Strategic role relative to CDE

Legacy Player is also a multiplayer research foundation for future CDE systems.

It allows networking, replay, diagnostics, and multiplayer orchestration patterns to be proven in a live environment before being integrated into a future engine.
