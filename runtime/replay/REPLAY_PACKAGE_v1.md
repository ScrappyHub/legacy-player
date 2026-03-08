# Replay Package v1

## Purpose

This document defines the first conceptual replay package for Legacy Player.

The first replay package does not need advanced playback yet.

It needs to preserve a structured history of the session.

---

## First replay package goals

The first replay package should make it possible to understand:

- what session was created
- who participated
- which adapter and game pack were used
- when key boundaries were crossed
- whether compatibility passed
- whether mismatch occurred
- how the session ended

---

## Suggested sections

The first replay package may eventually contain sections such as:

- session metadata
- participant metadata
- compatibility markers
- boundary markers
- mismatch events
- completion or failure event

---

## Design rule

Replay packages should be:

- structured
- stable
- readable
- useful for debugging and later tooling

Replay should be treated as a durable runtime artifact, not a disposable afterthought.

---

## First implementation target

The first implementation should produce a minimal replay package shape that can capture the first controlled session proof.
