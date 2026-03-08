# Sync Strategy v1

## Purpose

This document defines the first synchronization direction for Legacy Player.

The first goal is not to support every multiplayer model.

The first goal is to support one explainable model well enough to prove the architecture.

---

## Initial synchronization model

Legacy Player v1 should begin with:

- deterministic input lockstep

This means the runtime coordinates players around synchronized input progression rather than trying to design a broad rollback system immediately.

---

## Why this is the right first model

Deterministic input lockstep is the right first model because it is:

- simpler to reason about
- easier to pair with replay capture
- easier to pair with state mismatch diagnostics
- consistent with early emulator-assisted support goals

---

## Boundary-aware behavior

The sync strategy must work with game-pack-defined boundaries.

Examples of important boundaries include:

- ready-state confirmation
- setup completion
- scene transition entry
- minigame or active-play start
- result or return transitions

The sync system should not advance blindly across these boundaries.

---

## Failure posture

When synchronization safety is not achieved, the runtime should:

- stop clearly
- emit diagnostics
- preserve replay-visible failure markers

The first implementation should prefer explainable failure over vague drift.

---

## Future models

Future versions may explore:

- rollback
- hybrid lockstep and rollback
- checkpoint-assisted recovery

These are not required for the first proof.
