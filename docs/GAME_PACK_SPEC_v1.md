# Legacy Player Game Pack Spec v1

## Purpose

A game pack defines how Legacy Player supports a specific game.

A game pack provides the structured, game-specific knowledge required for online session orchestration.

This includes:

- game identity
- memory/state regions of interest
- scene and phase detection
- synchronization boundaries
- compatibility rules
- runtime assistance rules
- replay labeling

---

## Design principle

A game pack is not an unstructured bag of hacks.

A game pack is a controlled support package that plugs into the runtime through defined boundaries.

Game packs must remain readable, testable, and replaceable.

---

## Core sections

A game pack should define the following sections.

### 1. Identity

Defines:

- game title
- platform
- region/version fingerprints
- supported adapter targets
- compatibility notes

### 2. State model

Defines:

- major game scenes or phases
- player slot representations
- core state variables
- scene transition markers
- critical simulation fields

### 3. Synchronization boundaries

Defines where the runtime may safely enforce synchronization.

Examples:

- lobby ready state
- character select confirmation
- map start
- minigame start
- inning transition
- race countdown
- results screen

### 4. Compatibility rules

Defines what must match across peers.

Examples:

- game version
- region
- adapter version
- save/profile conditions
- controller slot assumptions
- optional feature flags

### 5. Runtime assistance rules

Defines controlled runtime help.

Examples:

- menu freeze barriers
- transition wait states
- controller ownership remaps
- scene-entry validation
- known correction hooks

### 6. Replay metadata rules

Defines labels and markers that improve replay usefulness.

Examples:

- session phase names
- round/minigame markers
- results boundaries
- notable event labels

---

## Support tiers in game packs

Each game pack should declare its support tier.

### Tier A

Native sync only.

### Tier B

Runtime-assisted support.

### Tier C

Full multiplayer conversion support.

---

## Game class reuse

Game packs should eventually inherit from game-class knowledge when possible.

Examples of classes:

- party games
- sports games
- racing games
- fighting games

This allows structured reuse across similar titles.

---

## Initial expected game pack targets

Recommended first targets:

- Mario Party 4
- Mario Party 6

These are strong first candidates because they have discrete phases and clearer synchronization boundaries.

---

## Testing expectations

Each game pack should eventually be tested for:

- identity recognition
- scene detection
- synchronization boundaries
- critical mismatch detection
- replay labeling
- clean failure behavior

---

## Long-term role

Game packs are the scaling mechanism of Legacy Player.

The project becomes maintainable by growing through disciplined game packs instead of uncontrolled per-title code sprawl.
