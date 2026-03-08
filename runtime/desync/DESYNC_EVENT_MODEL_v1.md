# Desync Event Model v1

## Purpose

This document defines the first conceptual event shape for desync and mismatch reporting in Legacy Player.

The goal is to make session failure explainable from the beginning.

---

## Core principle

A multiplayer session should not just fail.

It should fail with structure.

That means the system should be able to say:

- what kind of mismatch occurred
- where it occurred
- what phase or boundary was active
- whether the mismatch was recoverable or terminal

---

## Suggested first event categories

Initial categories may include:

- compatibility mismatch
- boundary violation
- unsupported transition
- critical state mismatch
- session termination reason

---

## Example event meanings

Examples:

- peers do not match supported game profile
- peers did not reach the same ready state
- peers entered different scene boundaries
- critical observed state diverged
- session stopped because continued play was unsafe

These describe the intended shape of the event model.

---

## Design rule

Desync events should be:

- explicit
- readable
- useful for debugging
- usable by replay and diagnostic tooling

The runtime should never rely on mystery failure.
