# Session Module

## Purpose

The session module manages the lifecycle of a Legacy Player multiplayer session.

It defines how sessions are created, how participants join, how readiness is tracked, how compatibility gates are enforced, and how a session moves into active play or fails cleanly.

---

## Responsibilities

This module is responsible for:

- session creation
- session identity
- participant membership
- host or peer role metadata
- readiness tracking
- session state transitions
- compatibility gate checkpoints
- explicit session completion and failure states

---

## Core session states

The session module should model a session through explicit states.

Suggested initial states:

- created
- joining
- validating
- ready-barrier
- active
- completed
- failed

The system should prefer explicit state transitions over implicit behavior.

---

## Required concerns

The session module should eventually define:

- session id
- participant list
- participant role metadata
- readiness status
- selected adapter id
- selected game pack id
- compatibility status
- session start marker
- session end marker
- failure reason if applicable

---

## First implementation target

The first implementation should be able to:

- create a session
- add participants
- track readiness
- store selected adapter and game pack metadata
- enter a ready-barrier state
- transition into active or failed state

That is enough for the first controlled proof.
