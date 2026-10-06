# Proposal 0001 — Classify Legacy Player

**Status:** Proposed  
**Date:** 2026-08-20  
**Decision owners:** Atlas Systems ecosystem maintainers  
**Affected service:** `legacy-player`

## Decision requested

Classify Legacy Player as a standalone-first legacy-game compatibility and runtime service rather than leaving it in the ecosystem's `unclassified` group.

Proposed role:

> Legacy Player is a local-first compatibility, instrumentation, state-understanding, replay-verification, and multiplayer-orchestration runtime for legacy games. It integrates with emulators through adapters and interprets supported games through versioned game packs.

Proposed layer: `platform.legacy-runtime`.

No mandatory upstream service is proposed for Tier-0. Optional future ecosystem integrations must remain versioned and must not replace standalone correctness.

## Why classification is required

The current ecosystem registry says that the role and ownership boundaries require classification. The repository, however, already contains an emulator adapter, memory-observation tooling, game-pack scaffolding, session coordination, replay recording, and synchronization experiments. This is a canonical conflict: implementation and project documentation assert responsibilities that the ecosystem has not approved.

This proposal resolves the conflict without editing the service map or registry prematurely.

## Proposed ownership

Legacy Player owns:

- emulator-adapter contracts for safe observation and bounded control;
- supported-game identity and compatibility checks at the adapter/game-pack boundary;
- game-pack schemas and version-bound game semantics;
- RAM-relative field extraction and normalized game state;
- semantic event derivation from verified state changes;
- session, input-authority, synchronization-boundary, and divergence orchestration;
- replay transcripts, state checkpoints, and independent replay verification;
- local operator diagnostics and evidence receipts for these capabilities.

## Proposed non-ownership

Legacy Player does not own:

- emulator execution or emulator implementation;
- game binaries, ROMs, disc images, proprietary assets, or game licensing;
- general-purpose process inspection or arbitrary memory mutation;
- ecosystem identity, signing, consent, policy, or preservation authority;
- public matchmaking identity or internet-scale abuse prevention in Tier-0;
- claims of deterministic multiplayer for an unverified adapter/game combination;
- title-specific semantics outside the corresponding game pack.

## Trust and dependency boundaries

1. Emulator process data is untrusted until the adapter verifies process identity, emulator version, game identity, and the authoritative emulated-memory region.
2. Game packs are untrusted inputs until their schema, version, compatibility declaration, and integrity are verified.
3. Recorder-produced replays and hashes are claims until an independent verifier recomputes them.
4. Network participants authenticate to a session and may submit only data authorized for their participant identity.
5. Memory observation remains read-only by default. Controlled writes require a separately approved capability and failure policy.
6. Optional ecosystem integrations use explicit versioned contracts and explicit unavailable/failure states.

## Compatibility impact

Approval would require updates to:

- `C:\dev\_ecosystem\SERVICE_MAP.md`;
- `C:\dev\_ecosystem\service.registry.json`;
- `project.contract.json`;
- `docs/canonical/ECOSYSTEM_INTEGRATION.md`;
- integration tests and a new service-map receipt.

No runtime behavior should change merely because this proposal is approved.

## Alternatives considered

### Remain unclassified

Rejected as a durable state because it prevents an authoritative ownership audit and leaves the README and implementation in conflict with ecosystem governance.

### Classify as a generic emulator

Rejected because Legacy Player does not execute games. Emulator execution remains outside its boundary.

### Classify as a preservation authority

Rejected because replay and compatibility artifacts may support preservation, but long-term preservation authority belongs elsewhere in the ecosystem.

## Approval gates

- [ ] Ownership and non-ownership boundaries reviewed.
- [ ] Dependency direction reviewed.
- [ ] Compatibility impact accepted.
- [ ] Service map and registry updated together.
- [ ] Positive and negative integration tests added.
- [ ] Service-map receipt generated and verified.

