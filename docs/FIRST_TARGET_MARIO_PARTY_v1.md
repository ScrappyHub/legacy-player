# Legacy Player First Target — Mario Party v1

## Purpose

This document defines the reasoning and intent behind Legacy Player's first target path.

The purpose of this document is not to lock final reverse-engineering details yet. It is to lock the first-class implementation direction for a realistic and high-value proof.

---

## First target direction

Legacy Player should begin with:

- Platform: GameCube
- Emulator: Dolphin
- Game class: party games
- First flagship target: Mario Party 4 or Mario Party 6

This first target is selected because it gives Legacy Player the best balance of technical realism, player interest, and architectural value.

---

## Why Mario Party is the right first class

Party games are one of the strongest first classes for Legacy Player because they naturally expose discrete phases and synchronization boundaries.

Typical phase structure includes:

- title/menu flow
- player setup flow
- map/board flow
- event/transition flow
- minigame flow
- results flow

These boundaries are easier to reason about than the continuous frame-exact combat loops required by competitive fighters.

---

## Why this is a better first proof than a fighter

A fighting game is attractive, but it is a worse first implementation target because it usually requires:

- tighter frame timing
- harsher latency demands
- more punishing desync consequences
- stronger rollback requirements
- more difficult early perception of quality

Mario Party provides a better first proof because:

- it has more visible synchronization checkpoints
- it is more tolerant as a multiplayer research target
- the session structure is easier to model
- it still has a strong audience

---

## Initial support intent

The first Mario Party support path should aim for:

- game identification
- compatibility validation
- session-ready barrier control
- scene and phase detection
- replay event labeling
- mismatch diagnostics
- later runtime-assisted transition coordination

The first proof does not need perfect universal online support for every mode or version.

It needs one clean, explainable supported path.

---

## Initial target questions

The first technical investigation should answer:

1. how the game can be identified reliably
2. which version/revision should be supported first
3. which major scenes or phases can be detected
4. which boundaries are safe for synchronization enforcement
5. which fields or states are most important for mismatch detection
6. what minimal replay markers are useful
7. what runtime assistance is likely needed first

---

## Example phase model

The exact model will evolve, but the project should expect something conceptually like this:

### Phase 1 — Boot / Title

Focus:
- identify active game
- establish compatibility fingerprint
- confirm supported profile

### Phase 2 — Setup / Player configuration

Focus:
- player slot agreement
- controller ownership assumptions
- save/profile considerations if relevant
- synchronized readiness

### Phase 3 — Board / Main progression

Focus:
- confirm players entered shared phase
- track major turn transitions
- detect unexpected divergence markers

### Phase 4 — Minigame entry

Focus:
- synchronization barrier before transition
- confirm all peers entered correct scene
- mark replay boundary

### Phase 5 — Minigame active play

Focus:
- active input synchronization
- limited critical-state monitoring
- mismatch diagnostics if needed

### Phase 6 — Results / Return flow

Focus:
- detect transition completion
- mark replay event boundaries
- confirm session continuity

---

## Suggested first implementation intent

The first Mario Party proof should aim to support a narrow, high-confidence path rather than broad uncertain claims.

Recommended first proof shape:

- one chosen Mario Party title
- one chosen version/revision
- one chosen supported session flow
- private session only
- explicit compatibility requirements
- replay and diagnostics always enabled

---

## What success looks like

A successful first Mario Party proof means:

- Legacy Player can identify the game and supported profile
- the runtime can load the matching game pack
- a session can reach synchronized ready state
- major boundaries can be recognized and logged
- replay metadata is produced
- mismatch/failure behavior is clear and explicit

That is enough to prove the framework is real.

---

## What should not happen

The first Mario Party target should not become:

- a grab bag of untracked hacks
- a hardcoded special case inside the runtime
- a Dolphin-only design that cannot generalize
- a broad support promise for all Mario Party titles at once

The first title should be treated as the first clean exemplar of the architecture.

---

## Strategic role

Mario Party is not just the first supported game.

It is the first demonstration that Legacy Player can act as:

- a multiplayer orchestration runtime
- a game-aware compatibility layer
- a replay and diagnostics platform
- a reusable foundation for future game classes

If done cleanly, the first Mario Party path becomes the template for how the rest of Legacy Player grows.
