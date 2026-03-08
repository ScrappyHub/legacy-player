# Legacy Player Memory Probe

## Purpose

Memory Probe is the first executable investigation tool for Legacy Player.

Its job is to observe supported emulator memory in a safe, read-only way so Legacy Player can identify games, discover stable scene markers, study state transitions, and build the structured knowledge required for adapters and game packs.

Memory Probe is not the multiplayer runtime.

It is the reverse-engineering and observation instrument that feeds the runtime.

---

## Why this exists

Legacy Player cannot orchestrate multiplayer safely unless it can first answer questions like:

- what game is running
- which profile or region is loaded
- what phase the game is in
- which state markers are stable
- which transitions are important
- which fields may matter for compatibility or desync detection

Memory Probe exists to produce those answers in a disciplined way.

---

## First design rule

Memory Probe v1 is strictly:

- read-only
- external to the emulator
- bounded in scope
- structured in output
- safe to fail cleanly

It must not:

- write emulator memory
- patch process memory
- inject code
- mutate gameplay state
- pretend certainty where it only has candidate observations

---

## Initial target

The initial target path is:

- Emulator: Dolphin
- Platform: GameCube
- First game class: party games
- First flagship game: Mario Party 4

This gives Memory Probe a narrow and realistic first use case.

---

## Core responsibilities

Memory Probe is responsible for:

- locating a supported emulator process
- attaching in a safe read-only manner
- identifying the active game fingerprint
- reading selected memory regions
- sampling state over time
- detecting meaningful value changes
- exporting structured observation logs

---

## Expected outputs

Memory Probe should produce structured outputs such as:

- process attach success/failure
- game fingerprint events
- memory region sample events
- candidate phase marker events
- candidate boundary marker events
- session summary logs

The first output format should be simple and durable.

Recommended initial format:

- NDJSON / JSONL

---

## Relationship to Legacy Player architecture

Memory Probe feeds the rest of the project.

Conceptually:

```text
memory_probe
→ target investigation
→ adapter understanding
→ game pack discovery
→ runtime orchestration
→ multiplayer support
