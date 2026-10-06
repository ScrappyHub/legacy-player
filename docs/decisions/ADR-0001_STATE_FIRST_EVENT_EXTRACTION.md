# ADR-0001 — Derive Events from Grounded State

**Status:** Accepted as working architecture  
**Date:** 2026-08-20

## Context

Early Mario Party 4 experiments grouped actions by changed 4 KiB pages and coarse byte-count patterns. Several distinct actions mutated the same pages, and exact before/after bytes varied with timing, animation, RNG, position, and transient state. A page labeled for one action therefore produced collisions with unrelated actions.

## Decision

The product pipeline is:

```text
authoritative RAM
  -> grounded fields
  -> normalized state
  -> state deltas plus phase context
  -> semantic events
```

Page hashes, hot windows, changed-byte counts, and offset patterns remain discovery tools used to locate candidate fields. They do not independently establish canonical gameplay semantics.

Unknown and ambiguous transitions return `UNKNOWN`.

## Consequences

- Field discovery and phase grounding precede production event classification.
- Game-pack event rules reference normalized fields, phase constraints, and evidence.
- Existing page/action artifacts remain historical evidence and discovery hints.
- Classifier evaluation measures false positives, false negatives, and unknown coverage.
- Replay and synchronization bind normalized state/checkpoints rather than trusting page-pattern labels.

## Rejected alternatives

### Page identity as action identity

Rejected because shared pages contain economy, board, animation, UI, and transient data.

### Exact before/after byte signatures

Rejected as the primary mechanism because dynamic values make signatures unstable across sessions.

### Best-match guessing

Rejected because it violates the fail-closed and no-silent-guessing requirements.

