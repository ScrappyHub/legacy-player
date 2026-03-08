# Desync Module

## Purpose

The desync module detects and reports multiplayer divergence in Legacy Player.

Its role is to make mismatch and drift visible, structured, and explainable.

Desync handling must be a first-class concern from the beginning.

---

## Responsibilities

This module is responsible for:

- mismatch detection
- divergence reporting
- explicit failure reason creation
- diagnostic event capture
- state comparison support
- future safe-boundary recovery direction

---

## Design rule

The desync module must not be treated as an optional late-stage feature.

If Legacy Player cannot explain why a session failed, it will not scale.

Desync visibility is part of the core architecture.

---

## Expected concerns

The desync module should eventually support:

- critical mismatch detection
- boundary violation reporting
- unsupported state transition reporting
- state hash mismatch events
- structured failure reasons
- replay-visible failure markers

---

## First implementation target

The first implementation should be able to:

- emit explicit mismatch events
- store failure reasons
- hand mismatch information to replay or diagnostics outputs
- terminate a session clearly when required
