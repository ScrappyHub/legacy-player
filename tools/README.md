# Legacy Player Tools

## Purpose

The tools layer contains helper utilities that support development, debugging, replay inspection, and pack authoring for Legacy Player.

These tools are not the runtime itself, but they are important for making the system observable, maintainable, and scalable.

---

## Intended areas

### `memory_probe/`

Tools for observing and validating emulator-visible state and memory regions during supported target investigation.

### `replay_inspector/`

Tools for viewing replay metadata, session markers, state hashes, and diagnostic events produced by Legacy Player sessions.

### `pack_builder/`

Tools for creating, validating, and refining game pack structures as support expands.

---

## Why this matters

Legacy Player will only scale if it can inspect and explain its own behavior.

These tools exist to support:

- reverse-engineering discipline
- structured investigation
- replay usefulness
- desync debugging
- maintainable game pack growth

---

## First implementation role

At the beginning, these tools can remain simple.

The first goal is to support:

- target investigation
- structured observation
- replay visibility
- pack authoring discipline

That is enough to help the first adapter and first game pack become real.
