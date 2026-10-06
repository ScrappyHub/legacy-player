# Evidence and Receipt Policy

**Version:** 1.0-working  
**Date:** 2026-08-20

## Purpose

Legacy Player learns semantics from experiments against opaque software. Evidence discipline is therefore part of correctness, not optional project administration.

## Confidence lifecycle

| Level | Meaning | Promotion requirement |
|---|---|---|
| `candidate` | A value or behavior may be relevant | Reproducible observation plan exists |
| `observed` | Seen once in an identified run | Raw artifact preserved and digested |
| `repeated` | Seen in independent equivalent runs | Results agree within declared constraints |
| `grounded` | Semantics withstand positives, negatives, and confounders | Restart/reload and version-binding evidence |
| `canonical` | Approved for a versioned game pack or contract | Independent verifier and review approval |

No tool may automatically promote an observation directly to `canonical`.

## Required experiment record

Every discovery experiment records:

- experiment schema and unique ID;
- tool and schema versions;
- game ID, region, revision/media identity, and game-pack version;
- emulator family/version and adapter version;
- process identity as noncanonical metadata;
- RAM-resolution receipt digest;
- initial phase/state assumptions;
- exact operator action or automated input;
- capture parameters and canonical sample offsets;
- positive, negative, or confounding classification;
- raw artifact digests;
- result, confidence, and unresolved ambiguity;
- start/end timestamps as noncanonical metadata.

## Receipt families

The project requires versioned receipts for:

- emulator/game identity;
- RAM candidate enumeration and selected authority;
- field discovery and promotion;
- phase transitions;
- normalized state and state hashes;
- event classification;
- replay creation and replay verification;
- divergence and recovery;
- game-pack verification and freeze;
- release verification.

## Minimum receipt envelope

```json
{
  "schema": "legacy_player.receipt.v1",
  "receipt_type": "example",
  "subject": {},
  "inputs": [],
  "result": "pass",
  "claims": [],
  "artifacts": [
    {
      "media_type": "application/json",
      "sha256": "64 lowercase hexadecimal characters"
    }
  ],
  "verifier": {
    "name": "independent verifier",
    "version": "..."
  },
  "noncanonical": {
    "created_at_utc": "..."
  }
}
```

Each specialized receipt schema must define canonical fields, canonical byte construction, ordering, allowed values, and verification procedure. Machine paths must not be the sole artifact identifier.

## Canonicalization

- Canonical JSON uses UTF-8 without BOM and LF line endings.
- Object-key ordering and array ordering are defined by each schema.
- Floating-point values are forbidden in canonical content unless represented by an explicitly specified deterministic encoding.
- SHA-256 is the default digest.
- Timestamps, PIDs, random IDs, usernames, and absolute paths are noncanonical unless a contract explicitly requires them.
- A receipt never trusts a stored count, hash, signature, or status without recomputation.

## Artifact handling

- Raw captures are immutable evidence; derived summaries never replace them.
- New evidence versions are added rather than overwriting v1 artifacts.
- Sensitive memory captures remain ignored by Git and require explicit review before sharing.
- Redaction creates a new derived artifact with provenance; it does not alter the source.
- Retention and deletion must be explicit because raw memory may contain unrelated process or user data.

## Failure policy

Missing input, unreadable memory, ambiguous candidates, invalid schemas, digest mismatch, partial captures, incompatible versions, and verifier disagreement fail closed. A failed run emits a failure receipt when it can do so without misrepresenting incomplete output as verified evidence.

