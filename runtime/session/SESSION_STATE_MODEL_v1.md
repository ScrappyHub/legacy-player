# Session State Model v1

## Purpose

This document defines the initial conceptual state model for Legacy Player sessions.

The goal is to make session flow explicit, testable, and explainable from the beginning.

---

## Initial state model

### `created`

The session exists but no compatibility or readiness flow has been completed.

### `joining`

Participants are being added and the session membership is still changing.

### `validating`

The runtime is evaluating compatibility using adapter and game-pack-aware checks.

### `ready-barrier`

The session has enough participants and is waiting for synchronized readiness before active simulation.

### `active`

The session has entered active multiplayer flow.

### `completed`

The session ended successfully.

### `failed`

The session terminated because of incompatibility, mismatch, or another explicit failure condition.

---

## Transition principles

Transitions should be:

- explicit
- observable
- replay-visible where appropriate
- paired with clear failure reasons when rejected

The runtime should not silently skip or blur states.

---

## Example lifecycle

A typical first lifecycle should look like:

1. created
2. joining
3. validating
4. ready-barrier
5. active
6. completed

Or:

1. created
2. joining
3. validating
4. failed

This is enough for first implementation planning.
