# State Module

## Purpose

The state module provides the shared runtime surface for observing multiplayer-relevant state.

It exists so the runtime can reason about scene progression, compatibility markers, state mismatch indicators, and replay-visible markers without hardcoding game-specific meaning into the shared core.

---

## Responsibilities

This module is responsible for:

- state observation contracts
- runtime-visible marker handling
- shared state representation
- state snapshot and state marker concepts
- compatibility-relevant observable state
- handoff surfaces used by desync and replay systems

---

## Relationship to adapters and game packs

Adapters expose platform-specific observables.

Game packs interpret game-specific meaning.

The state module provides the shared runtime-side shape used to work with those observables in a controlled way.

This separation is important.

---

## Expected concepts

The state module should eventually support concepts such as:

- scene or phase marker
- participant-visible runtime state
- critical state field grouping
- state checkpoint marker
- comparison-ready state surfaces
- replay-visible state labels

---

## First implementation target

The first implementation should be able to:

- represent structured state markers
- receive state observations from the adapter path
- expose state markers to replay and diagnostics layers
- support compatibility-aware checkpoints
