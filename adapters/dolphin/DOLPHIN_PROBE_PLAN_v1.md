# Dolphin Probe Plan v1

## Purpose

This document defines the first investigation plan for using Memory Probe against Dolphin.

It is not the final Dolphin adapter implementation.

It is the planning surface for the first real technical work needed to make the adapter path possible.

---

## Goal

The goal of the first Dolphin probe work is to answer these questions:

1. can Legacy Player identify a running Dolphin target safely
2. can it capture a stable game fingerprint
3. can it observe bounded memory regions in a read-only way
4. can it detect coarse phase transitions for the first target game
5. can those findings be translated into the first game pack model

---

## First investigation target

The first probe target should remain narrow.

Recommended path:

- Emulator: Dolphin
- Platform: GameCube
- Game: Mario Party 4
- Session type: local emulator run under observation only

No multiplayer logic is required at this stage.

---

## Investigation phases

## Phase 1 — Process identification

Questions:

- how is the Dolphin process identified reliably
- what attach path is safest
- what information can be captured before memory reads begin

Expected result:

- stable process discovery
- explicit attach success or attach failure event

---

## Phase 2 — Game fingerprint capture

Questions:

- how will the tool identify the active game
- what fields are stable enough to use for early game-pack selection
- what region, revision, or profile information is practically observable

Expected result:

- a structured fingerprint event
- enough identity information to support first-target selection

---

## Phase 3 — Bounded memory sampling

Questions:

- which known-safe regions should be sampled first
- what sample cadence is practical
- how should read failures be handled
- how should observations be logged

Expected result:

- repeatable read-only samples
- structured memory sample and memory change events

---

## Phase 4 — Coarse phase observation

Questions:

- which memory values or regions change reliably across major scenes
- which markers appear stable within a scene
- which markers are useful for coarse phase labeling

Expected early target phases:

- title
- setup
- board
- minigame entry
- minigame active
- results

Expected result:

- candidate phase markers
- first hints for game-pack phase modeling

---

## Phase 5 — Export and summarize findings

Questions:

- how should probe runs be stored
- how should candidate findings be summarized
- what findings are strong enough to seed the game pack

Expected result:

- exported NDJSON run logs
- a simple session summary
- a short list of candidate markers and boundaries

---

## Investigation rules

The Dolphin probe plan must follow these rules.

### Rule 1 — Read-only only

Do not write emulator memory.

### Rule 2 — Bounded reads only

Do not default to broad uncontrolled scans.

### Rule 3 — Structured output only

Every useful finding should be logged in structured form.

### Rule 4 — Coarse before precise

Find stable broad phase markers before chasing detailed gameplay structures.

### Rule 5 — Target one supported path

Do not broaden the target before first proof is real.

---

## Expected first outputs

The first useful Dolphin probe outputs should include:

- attach_ok or attach_failed
- fingerprint_detected
- region_sample_started
- memory_change_detected
- phase_marker_candidate
- run_summary

These event names can evolve, but the first run should already be structured enough to inspect later.

---

## Definition of success

The Dolphin probe plan succeeds when it produces a repeatable read-only investigation flow that can:

- identify Dolphin
- identify the active first target game
- sample selected memory regions
- emit structured logs
- help distinguish major scene transitions
