# Dolphin Behavioral RAM Candidate Validation v1

## Purpose

This protocol evaluates every eligible exact mapped 32 MiB Dolphin RAM candidate using the same RAM-relative samples before and after one labeled game action. It replaces first-match geometry as a source of authority.

The protocol is read-only. It does not prove game revision identity, state-field semantics, restart persistence, or deterministic multiplayer.

## Eligibility

A candidate enters a run only when it is:

- exactly 32 MiB;
- mapped memory;
- read/write under the existing Dolphin RAM classification;
- nonzero in the initial screening read.

All eligible candidates must be captured. The tool fails if the count exceeds its configured safety limit; it never truncates the set silently.

## Capture protocol

1. Attach to exactly one Dolphin process or an explicitly selected PID.
2. Require the current `GMPE01`/USA prototype profile gate.
3. Enumerate every eligible candidate.
4. Build one deterministic, sorted, unique set of RAM-relative sample offsets.
5. Capture baseline bytes from every candidate.
6. Perform exactly one labeled operator action.
7. Capture the configured post-action rounds from every candidate.
8. Reject any failed, partial, missing, reordered, or malformed read.
9. Count changed windows and bytes relative to the baseline.
10. Emit raw evidence and a decision receipt.
11. Recompute the receipt with the separate verifier.

Candidates are read sequentially within each round. Timing metadata is therefore diagnostic rather than a claim of simultaneous capture.

## Selection rule

The v1 policy is `exactly_one_candidate_with_changed_bytes.v1`.

| Observation | Result | Reason |
|---|---|---|
| Exactly one candidate changes | `pass` | `unique_behavioral_candidate` |
| More than one candidate changes | `fail` | `ambiguous_mutation` |
| No candidate changes | `fail` | `no_candidate_mutated` |
| Any required read fails | `fail` | `capture_incomplete` |

The strict rule intentionally prefers an inconclusive experiment over a guessed RAM authority. A passing run emits `DOLPHIN_RAM_CANDIDATE_VALIDATED`; restart/reload repetition is still required before `DOLPHIN_RAM_RESOLVER_REPEATABLE` or the milestone-A green token may be claimed.

## Evidence and receipts

The evidence schema is `legacy_player.dolphin_ram_candidate_evidence.v1`. It contains the subject, exact sample offsets, capture parameters, candidate geometry, raw sampled bytes, and post-action rounds. Absolute addresses, PID, executable path, run ID, and timestamps are isolated under `noncanonical`.

The receipt schema is `legacy_player.dolphin_ram_candidate_validation.v1`. It binds the evidence digest, recomputed snapshot digests, mutation counts, selection decision, and claims.

Canonical bytes are UTF-8 JSON with sorted object keys, compact separators, no NaN values, and no trailing newline. The top-level digest field and `noncanonical` object are excluded from their document digest. Stored JSON files are formatted for review, atomically replaced, flushed, reopened, byte-compared, and parsed before success.

Exports contain raw memory and remain under the ignored `tools/memory_probe/exports` directory.

## Usage

From the repository root with one supported Dolphin instance running:

```powershell
python -m tools.memory_probe.dolphin_attach.ram_candidate_validator `
  --action-label coin_total_change_once
```

Then independently verify the generated pair:

```powershell
python -m tools.memory_probe.dolphin_attach.ram_candidate_verifier `
  <evidence.json> <receipt.json>
```

Do not share raw evidence without reviewing it for unrelated process or user data.

## Required follow-up

A single passing action run establishes only a unique behavioral candidate for that experiment. The same behavior must be repeated after game reload and Dolphin restart, with equivalent relative characteristics even if the absolute base changes. Cross-run resolution receipts and stronger game/revision identity remain future work.

