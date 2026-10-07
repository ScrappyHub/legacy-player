# Ecosystem Integration — legacy-player

## Canonical service identity

| Field | Value |
|---|---|
| Service ID | `legacy-player` |
| Canonical name | legacy-player |
| Ecosystem family | `chronicle` |
| Ecosystem layer | `platform.legacy-runtime` |
| Standalone-first | `true` |

## Role

Local-first compatibility, instrumentation, state-understanding, replay-verification, and multiplayer-orchestration runtime for legacy games; integrates emulators through adapters and games through versioned game packs.

## This service owns

- UNCLASSIFIED

## This service does not own

- No ownership boundaries approved yet

## Upstream services

- None

## Downstream consumers or operators

- None

## Contract families

- Not yet classified

## Integration rules

1. This repository must remain independently understandable, testable, buildable, and releasable.
2. Ecosystem integrations extend capability but do not replace standalone correctness.
3. Integrations use explicit, versioned schemas and receipts.
4. No undocumented database sharing, hidden filesystem coupling, or implicit trust is permitted.
5. Producer claims must be independently verified by the receiving boundary where verification is required.
6. Integration failure must not silently corrupt local authoritative state.
7. Missing upstream services must produce an explicit unavailable, unknown, deferred, or failed state according to the local contract.
8. This repository's current implementation must not be treated as the complete product definition.

## Authoritative ecosystem sources

- `C:\dev\Constellation\ecosystem\SERVICE_MAP.md`
- `C:\dev\Constellation\registry\services.json`
- `C:\dev\Constellation\ecosystem\AGENT_POLICY.md`
- `C:\dev\Constellation\ecosystem\SHARED_INVARIANTS.md`

## Change governance

Changes to this service's ecosystem role, ownership boundaries, upstream dependencies, or downstream responsibilities require:

1. A proposal under `docs\proposals`.
2. A documented compatibility impact.
3. Updated registry entries in Constellation (`registry/services.json`) and a re-published service map.
4. Updated positive and negative integration tests.
5. A new Constellation doctor receipt.
