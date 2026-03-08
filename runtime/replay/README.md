# Replay Module

## Purpose

The replay module records structured multiplayer session artifacts for Legacy Player.

Replay is a first-class output of the system.

It exists not only for playback and archival value, but also for debugging, diagnostics, and future multiplayer research.

---

## Responsibilities

This module is responsible for:

- session metadata recording
- replay event capture
- state marker capture
- mismatch and failure marker capture
- replay package shaping
- handoff to replay inspection tooling

---

## Why replay matters early

Replay should not be deferred until later.

Replay is part of how Legacy Player proves:

- what happened
- when it happened
- where boundaries were crossed
- where mismatch occurred
- what session shape existed

Replay and diagnostics should grow together.

---

## Expected replay concerns

The replay module should eventually support:

- session start markers
- participant metadata
- compatibility checkpoint markers
- readiness markers
- boundary markers
- mismatch markers
- session completion markers

---

## First implementation target

The first implementation should be able to:

- create a replay-visible session record
- record major lifecycle markers
- record mismatch or failure markers
- finalize a minimal replay package shape
