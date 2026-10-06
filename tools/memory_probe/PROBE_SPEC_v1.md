# Memory Probe Spec v1

## Purpose

The memory probe is a read-only research tool for discovering stable state markers
inside a supported Dolphin game instance. It produces evidence for game packs; it is
not the multiplayer transport or synchronization engine.

## Supported target

- Emulator: Dolphin on Windows
- Game: Mario Party 4
- Profile: `GMPE01` / USA
- Access: read-only process memory

The probe must reject ambiguous Dolphin processes, unsupported game profiles, and
RAM candidate sets that cannot produce one complete, unique behavioral result. Exact
size, mapped type, and nonzero content establish eligibility, not authority.

## Functional requirements

1. Attach to exactly one explicitly supported Dolphin process.
2. identify the active game and region before reading game-specific state.
3. Perform bounded, deterministic reads.
4. Store page offsets as canonical identifiers; host addresses are diagnostic only.
5. Record timestamps, profile information, capture parameters, and explicit failures.
6. Require repeated positive captures and negative controls before promoting a marker.
7. Evaluate every eligible MEM1 candidate with identical RAM-relative offsets.
8. Emit digest-bound evidence and a decision receipt for behavioral RAM selection.
9. Reject partial reads, zero-change runs, and multi-candidate mutation as explicit failures.

## Evidence rules

An action signature is not grounded from a single run. Promotion requires at least
three repeatable positive captures, negative-control captures, and a signature that
is separable from competing actions. Page-level activity alone is a discovery hint,
not a safe synchronization marker.

See `adapters/dolphin/DOLPHIN_RAM_VALIDATION_v1.md` for the candidate-selection
protocol and independent receipt-verification procedure.

## Module shape

```text
tools/memory_probe/
├─ probe_runner/
├─ dolphin_attach/
├─ game_fingerprint/
├─ memory_reader/
├─ state_sampler/
├─ log_writer/
└─ exports/
```
