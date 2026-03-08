# Sync Module

## Purpose

The sync module manages multiplayer synchronization policy in Legacy Player.

Its job is to coordinate the active multiplayer flow in a way that preserves simulation correctness and makes failure observable.

The first expected strategy is deterministic input lockstep.

---

## Responsibilities

This module is responsible for:

- synchronization strategy coordination
- boundary enforcement
- active input timing policy
- readiness-to-active transition handling
- explicit sync-related failure behavior
- future extension to stronger sync models

---

## Initial strategy

The first runtime strategy should be:

- deterministic input lockstep

This is the most practical starting point for a first proof because it is understandable, observable, and consistent with the architecture direction.

---

## Boundary role

The sync module should work closely with session and game-pack-defined boundaries.

Typical responsibilities include:

- waiting until peers are ready
- coordinating entry into active simulation
- respecting game-pack-defined safe boundaries
- surfacing boundary violations clearly

---

## Non-goals

The sync module should not:

- hardcode Mario Party logic
- hardcode Dolphin-specific behaviors
- become a dumping ground for game hacks

Shared sync behavior belongs here.

Game-specific meaning does not.

---

## First implementation target

The first implementation should be able to:

- represent the selected sync strategy
- respect a ready barrier
- enter active synchronization state
- emit clear failure signals if the session cannot safely proceed
