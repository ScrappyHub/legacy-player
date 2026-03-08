
# Path: `tools/memory_probe/PROBE_SPEC_v1.md`

```md
# Memory Probe Spec v1

## Purpose

This document defines the first functional specification for the Legacy Player Memory Probe tool.

The goal of v1 is to create a safe, structured, read-only investigation tool that can help identify emulator targets, inspect selected memory regions, and produce logs that support adapter and game-pack development.

---

## Scope

Memory Probe v1 is intentionally narrow.

It is meant to support:

- Dolphin attach
- game fingerprint capture
- bounded read-only memory observation
- structured log emission
- coarse scene and transition investigation

It is not meant to support:

- memory writes
- runtime patching
- emulator injection
- multiplayer session control
- production-grade UI
- broad automatic game support

---

## Functional goals

Memory Probe v1 must aim to support the following functional goals.

### Goal 1 — Process attach

The tool must be able to:

- locate a supported Dolphin process
- attempt a read-only attach
- report success or explicit failure
- exit cleanly if attach is unavailable

### Goal 2 — Game fingerprint capture

The tool must be able to capture a structured target identity sufficient for early game-pack selection planning.

Expected fields may include:

- emulator identity
- game title identity if available
- game id
- region
- revision/profile notes if available

### Goal 3 — Region sampling

The tool must be able to read selected memory regions in bounded sizes.

The first design should prefer:

- explicit regions
- small reads
- sampled intervals
- controlled failures

### Goal 4 — Observation logging

The tool must emit structured events describing what happened during a probe run.

Expected event classes include:

- attach event
- fingerprint event
- memory sample event
- memory change event
- marker candidate event
- summary event

### Goal 5 — Candidate phase observation

The tool should support identifying coarse candidate phase changes for the first target game.

Examples:

- title
- setup
- board
- minigame entry
- minigame active
- results

At first, these can remain explicitly labeled as candidate findings rather than guaranteed truth.

---

## Non-functional rules

Memory Probe v1 must follow these non-functional rules.

### Rule 1 — Read-only only

No emulator memory writes.

### Rule 2 — Small bounded reads

No uncontrolled sweeping of large process memory ranges as a default behavior.

### Rule 3 — Structured failure

Failures must be emitted clearly and cleanly.

### Rule 4 — No architecture contamination

Memory Probe logic must remain separate from runtime multiplayer logic.

### Rule 5 — Durable logs

Probe outputs should be structured and easy to inspect later.

---

## Suggested module shape

A practical first internal shape is:

```text
tools/memory_probe/
├─ probe_runner/
├─ dolphin_attach/
├─ game_fingerprint/
├─ memory_reader/
├─ region_catalog/
├─ state_sampler/
├─ log_writer/
└─ exports/
