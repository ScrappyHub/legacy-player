# Mario Party 4 Game Pack

## Purpose

This game pack defines Legacy Player support for Mario Party 4.

It contains the structured game-specific knowledge needed for the runtime to reason about compatibility, phase boundaries, replay labeling, and runtime-assisted multiplayer behavior.

---

## Role in Legacy Player

This pack is the first exemplar of the Legacy Player architecture.

It should demonstrate how a game pack can provide game-specific intelligence without forcing game-specific logic into the shared runtime.

This pack should help prove:

- game identity matching
- supported profile declaration
- scene and phase modeling
- synchronization boundary declaration
- replay marker labeling
- explicit mismatch and failure behavior

---

## Expected sections

This game pack is expected to grow into the following areas:

### Identity

- supported title identity
- supported region/revision profile
- adapter expectations
- compatibility notes

### State model

- major scenes and phases
- player slot assumptions
- important runtime-visible markers
- transition indicators

### Synchronization boundaries

- ready-state barriers
- setup confirmation points
- board/minigame transition points
- results and return-flow markers

### Compatibility rules

- supported game profile requirements
- adapter requirements
- optional save/profile conditions if needed
- session assumptions

### Runtime assistance rules

- menu synchronization barriers
- transition wait conditions
- ownership assumptions
- controlled correction/orchestration behavior

### Replay metadata rules

- session start marker
- setup markers
- board/minigame markers
- result markers
- failure markers

---

## First proof target

The first proof for this game pack should be narrow.

It should aim to support one explicit, explainable path rather than claiming broad universal support immediately.

Success means:

- the runtime can recognize and load this pack
- compatibility rules can be evaluated
- major boundaries can be labeled
- replay metadata can be emitted
- mismatch behavior can be reported clearly
