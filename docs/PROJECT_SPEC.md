# Legacy Player Project Specification

**Version:** 0.1-working  
**Status:** Working implementation specification  
**Date:** 2026-08-20

This specification translates the project handoff into testable requirements. It does not override the ecosystem registry. The proposed canonical role is recorded in `docs/proposals/0001_CLASSIFY_LEGACY_PLAYER.md` and remains unapproved until the ecosystem governance process completes.

## 1. Product definition

Legacy Player is intended to give supported legacy games a machine-readable state and lifecycle without requiring their original source code. It surrounds an emulator with governed adapter, game-pack, state, event, replay, and synchronization capabilities.

The emulator executes the game. Legacy Player observes and interprets it.

The canonical processing direction is:

```text
verified emulator and game
    -> authoritative emulated RAM
    -> version-bound fields
    -> normalized state
    -> state deltas
    -> semantic events
    -> replay and synchronization boundaries
```

Page mutation and byte-pattern tooling are discovery aids. They are not the final gameplay API and must not independently establish semantic truth.

## 2. Tier-0 outcome

The first standalone product milestone is:

> Dolphin plus Mario Party 4 `GMPE01` USA as a read-only state and replay-verification instrument.

Tier-0 requires one verified emulator adapter and one complete game pack. Multiplayer is a later capability unless all multiplayer gates in `docs/DEFINITION_OF_DONE.md` are satisfied.

## 3. Scope

### In scope

- safe Dolphin process discovery and read-only attachment;
- emulator and game identity verification;
- behavioral selection of authoritative GameCube MEM1;
- deterministic RAM-relative reads and snapshots;
- evidence-backed Mario Party 4 field discovery;
- normalized state and state-delta calculation;
- conservative semantic event extraction;
- deterministic replay transcript creation and independent verification;
- session and synchronization experiments after state authority is proven;
- versioned emulator-adapter and game-pack interfaces;
- machine-readable receipts and local diagnostics.

### Out of scope for Tier-0

- distribution of game content;
- arbitrary process memory editing;
- public-internet server hardening;
- universal support for games or emulators;
- deterministic multiplayer claims based only on DSU delivery;
- recovery through memory correction or save-state transfer without separate proof;
- treating page-change signatures as canonical semantic events.

## 4. Constitutional separation

Core runtime code must remain emulator- and title-neutral.

- Emulator adapters answer: how is the emulated machine safely located, identified, observed, and—only when separately authorized—controlled?
- Game packs answer: what does verified emulator state mean for one game/version?
- Core runtime answers: how are normalized state, events, replay, sessions, and synchronization handled without title-specific assumptions?

Dolphin process assumptions belong under `adapters/dolphin` or adapter-specific tooling. Mario Party 4 offsets and semantics belong under `game_packs/mario_party_4`.

## 5. Functional requirements

### Identity and compatibility

- **LP-FR-001:** The system shall identify the emulator process without silently selecting among ambiguous candidates.
- **LP-FR-002:** The system shall bind observations to emulator family and version.
- **LP-FR-003:** The system shall bind game knowledge to game ID, region, revision/media fingerprint, adapter version, and game-pack version.
- **LP-FR-004:** Unsupported or incompletely identified configurations shall fail closed.
- **LP-FR-005:** Session validation shall independently verify that the requested adapter and game pack exist and support the observed profile.

### Memory authority and observation

- **LP-FR-010:** The Dolphin adapter shall enumerate plausible emulated-RAM candidates without treating geometry alone as authority.
- **LP-FR-011:** The adapter shall behaviorally validate all plausible exact MEM1 candidates.
- **LP-FR-012:** Candidate ambiguity shall produce an explicit failure, never first-match selection.
- **LP-FR-013:** Selection shall be repeatable across Dolphin restart and game reload even when absolute base addresses change.
- **LP-FR-014:** Persisted game knowledge shall use RAM-relative offsets.
- **LP-FR-015:** Discovery shall remain read-only unless a controlled-write experiment is separately approved and receipted.
- **LP-FR-016:** RAM resolution shall emit a machine-readable receipt.

### Field discovery and normalized state

- **LP-FR-020:** Each proposed field shall record datatype, endianness, valid range, lifetime, phase constraints, and version binding.
- **LP-FR-021:** Promotion beyond `candidate` shall require positive observations, repeated observations, and negative controls.
- **LP-FR-022:** Unknown or ambiguous field values shall remain unknown.
- **LP-FR-023:** Normalized state shall have a versioned schema and deterministic serialization.
- **LP-FR-024:** State hashes shall be SHA-256 over precisely defined canonical bytes.
- **LP-FR-025:** The first board-state set shall cover coins, stars, board position, current player, and turn number.

### Semantic events

- **LP-FR-030:** Events shall derive primarily from validated normalized-state transitions and phase context.
- **LP-FR-031:** Event rules shall expose confidence and supporting evidence.
- **LP-FR-032:** Unknown transitions shall produce `UNKNOWN`, not a best-effort semantic guess.
- **LP-FR-033:** Event ordering and IDs shall be deterministic.
- **LP-FR-034:** False-positive and false-negative rates shall be measured against a labeled proof corpus.

### Replay and verification

- **LP-FR-040:** A replay shall bind initial identity/state, ordered authorized inputs or events, sync markers, and state checkpoints.
- **LP-FR-041:** Replay writes shall be atomic, durable, bounded, and recoverable from limit or storage failures.
- **LP-FR-042:** A replay package shall include or bind a content digest and schema version.
- **LP-FR-043:** An independent verifier shall recompute event counts, canonical hashes, checkpoint results, and package integrity.
- **LP-FR-044:** Recorder failure shall not leave a session in an irreversible partially finalized state.

### Session and synchronization

- **LP-FR-050:** Participant identity, credentials, input ownership, and controller-slot authority shall be explicit.
- **LP-FR-051:** Inputs and checkpoints shall be ordered, bounded, authenticated, and rejected when stale, duplicate, or unsupported.
- **LP-FR-052:** Synchronization shall occur at empirically validated boundaries rather than assuming every emulator frame is authoritative.
- **LP-FR-053:** Divergence shall fail visibly and emit diagnostic evidence.
- **LP-FR-054:** Recovery/resynchronization shall not be claimed until a deterministic, independently verified mechanism exists.
- **LP-FR-055:** Deterministic multiplayer shall require two independent emulator instances and long-run state agreement.

### Game packs and adapters

- **LP-FR-060:** Adapter and game-pack manifests shall be schema-versioned and machine-verifiable.
- **LP-FR-061:** A game pack shall declare supported game identities, revisions, adapters, fields, phases, events, replay markers, and sync boundaries.
- **LP-FR-062:** Game-pack evidence shall refer to immutable proof artifacts rather than local absolute paths alone.
- **LP-FR-063:** A verifier shall reject malformed, unsupported, incompatible, or integrity-invalid packs.

## 6. Non-functional requirements

- **LP-NFR-001 Determinism:** Canonical ordering, serialization, hashing, and IDs shall be explicit and stable.
- **LP-NFR-002 Evidence:** Major claims shall have independently checkable receipts or proof artifacts.
- **LP-NFR-003 Safety:** Observation is read-only by default; paths and local configuration restore operations are constrained to approved roots.
- **LP-NFR-004 Failure semantics:** Missing dependencies, ambiguity, malformed input, stale state, invalid integrity, and verification failure shall fail closed.
- **LP-NFR-005 Bounded resources:** Network, memory, event, session, file, and evidence growth shall be bounded with transactional failure behavior.
- **LP-NFR-006 Portability:** Runtime knowledge shall not depend on process-specific absolute addresses or usernames/machine paths.
- **LP-NFR-007 Standalone correctness:** Optional ecosystem services shall not be required for local Tier-0 correctness.
- **LP-NFR-008 Reproducibility:** Automated gates and evidence formats shall be runnable from a clean checkout with declared dependencies.
- **LP-NFR-009 Security:** Secrets shall not enter logs, replays, receipts, command arguments, or status output.
- **LP-NFR-010 Claim discipline:** Documentation shall distinguish target, prototype, observed, repeated, grounded, canonical, and release-proven behavior.

## 7. Required outputs

Tier-0 produces:

- a verified adapter manifest;
- a RAM-resolution receipt;
- a version-bound Mario Party 4 game-pack manifest;
- a state-field registry and proof references;
- normalized-state snapshots and deterministic hashes;
- an ordered event/state transcript;
- a replay package and independent verification receipt;
- self-test results and a release-gate receipt.

## 8. Failure states

The following are explicit outcomes, not silent fallbacks:

- `EMULATOR_NOT_FOUND`
- `EMULATOR_AMBIGUOUS`
- `GAME_IDENTITY_UNVERIFIED`
- `UNSUPPORTED_GAME_PROFILE`
- `RAM_CANDIDATE_NOT_FOUND`
- `RAM_CANDIDATE_AMBIGUOUS`
- `RAM_CANDIDATE_NOT_REPEATABLE`
- `FIELD_VALUE_UNKNOWN`
- `EVENT_UNKNOWN`
- `PACK_INVALID`
- `REPLAY_VERIFICATION_FAILED`
- `STATE_DIVERGED`
- `CAPABILITY_UNAVAILABLE`

## 9. Milestone order

1. Authoritative MEM1 selection.
2. First grounded field.
3. Core board state.
4. Normalized state and semantic events.
5. Independently verified replay.
6. Local two-instance synchronization proof.
7. Network synchronization and recovery proof.
8. Mario Party 4 game-pack v1 freeze.
9. Second-game proof.
10. Second-emulator proof.

The detailed decomposition and entry/exit criteria are in `docs/WBS.md` and `docs/DEFINITION_OF_DONE.md`.

