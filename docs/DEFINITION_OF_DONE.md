# Legacy Player Definition of Done

**Version:** 1.0-working  
**Date:** 2026-08-20

“Done” means independently verifiable evidence, not code presence, a successful demonstration, or a model explanation.

## Global completion rules

Every completed work item must satisfy all applicable rules:

- Requirement and acceptance criteria are identified.
- Positive, negative, malformed, corrupted, partial, stale/replayed, ambiguous, and clean-state cases are tested as applicable.
- Canonical data uses stable ordering, UTF-8 without BOM, LF endings, and explicitly defined canonical bytes.
- Stored counts, hashes, signatures, identities, and state claims are independently recomputed.
- Failure is explicit and closed; no silent fallback or best-effort semantic guess is introduced.
- Resource limits fail transactionally without partially committed authoritative state.
- Secrets, machine paths, usernames, timestamps, and random IDs are excluded from reproducible content or isolated as noncanonical metadata.
- Outputs are atomically written, durably committed where supported, reopened, and verified before success is emitted.
- Documentation distinguishes target, prototype, observed, repeated, grounded, canonical, and release-proven status.
- A clean checkout can run the automated verification with declared dependencies.
- No high-severity audit finding remains open for the claimed capability.

## Memory substrate done

- [ ] Dolphin attachment is repeatable and ambiguous processes fail closed.
- [ ] Emulator version and game identity are independently verified.
- [ ] Every plausible exact MEM1 candidate is evaluated behaviorally.
- [ ] Exactly one candidate satisfies the authority rule or resolution fails.
- [ ] Selection survives game reload and Dolphin restart.
- [ ] Persisted knowledge uses RAM-relative offsets.
- [ ] Partial and failed reads are explicit.
- [ ] A versioned RAM-selection receipt is emitted and independently verified.
- [ ] Offline self-tests and regression vectors exist.
- [ ] Live evidence identifies the experiment, operator action, versions, and proof artifacts.

## Mario Party 4 discovery done

- [ ] Board and major phase can be identified.
- [ ] Current player and turn number are grounded.
- [ ] Coins, stars, and board position are grounded for every player.
- [ ] Dice result, movement remaining, items, active star location, and minigame ID are grounded.
- [ ] Every field specifies offset, type, width, endianness, range, lifetime, and phase constraints.
- [ ] Every field has positive, repeated-positive, negative, and confounding proofs.
- [ ] Every field survives reload/restart and is version-bound.
- [ ] No field depends on a runtime absolute address.
- [ ] Unsupported revisions and invalid values fail closed.

## Normalized state done

- [ ] A versioned schema defines all canonical and noncanonical fields.
- [ ] Raw-to-normalized transforms are deterministic and tested.
- [ ] Unknown values have an explicit representation.
- [ ] Canonical serialization bytes are specified with test vectors.
- [ ] State hashes are recomputed by an independent verifier.
- [ ] Snapshot and diff APIs have valid, invalid, partial, and version-mismatch tests.

## Semantic event engine done

- [ ] Events derive from grounded normalized state and phase context.
- [ ] Coin changes, landings, star purchases, star thefts, board events, and minigame transitions are distinguishable.
- [ ] Event IDs, ordering, payloads, and confidence are deterministic.
- [ ] Unknown or ambiguous transitions produce `UNKNOWN`.
- [ ] False-positive and false-negative rates are measured against a held-out corpus.
- [ ] Results repeat across independent sessions and supported emulator versions.

## Replay done

- [ ] Initial identity and normalized state are bound to the replay.
- [ ] Authorized input/event streams and sync markers are ordered and captured.
- [ ] Checkpoints bind canonical state hashes.
- [ ] Package schema, content digest, and limits are explicit.
- [ ] Storage failure and event-limit exhaustion do not partially finalize sessions.
- [ ] Replay reproduction reaches expected checkpoints where determinism is claimed.
- [ ] Corruption, truncation, reordering, duplication, stale replay, path abuse, and credential leakage are tested.
- [ ] A verifier independent from the recorder recomputes package integrity and checkpoint results.
- [ ] Success is emitted only after durable write and read-back verification.

## Multiplayer done

- [ ] Two independent emulator instances join one authenticated session.
- [ ] Emulator, game, revision, adapter, pack, and starting-state identities match.
- [ ] Input and controller ownership are explicit.
- [ ] Both instances reach the same empirically validated sync boundaries.
- [ ] State digests match over a complete Mario Party match.
- [ ] Deliberate divergence is detected and receipted.
- [ ] Recovery succeeds deterministically or fails closed with no continuation claim.
- [ ] Reconnect and participant loss are tested.
- [ ] All sync decisions and state transitions are logged without secrets.
- [ ] LAN and WAN latency/loss experiments meet declared thresholds.

## Game pack done

- [ ] Immutable game identity and supported region/revision are declared.
- [ ] Adapter and emulator compatibility constraints are declared.
- [ ] Field, phase, event, replay-marker, and sync-boundary registries are present.
- [ ] Every semantic entry references evidence.
- [ ] Machine-readable schemas and a pack verifier exist.
- [ ] Integrity and malicious/malformed pack tests pass.
- [ ] Self-tests and a portable proof corpus pass from a clean checkout.
- [ ] Pack version and compatibility policy are frozen.
- [ ] A freeze receipt is generated and independently verified.

## Tier-0 done

Tier-0 requires all of the following as one standalone instrument:

- [ ] One verified emulator adapter: Dolphin.
- [ ] One complete game pack: Mario Party 4 `GMPE01` USA.
- [ ] Authoritative game identity and MEM1 resolution.
- [ ] Grounded state extraction.
- [ ] Normalized state and semantic events.
- [ ] State transcript and independently verified replay/checkpoints.
- [ ] Receipts, self-test, clean installation, and operator documentation.
- [ ] All required security and release gates pass.

Reading Dolphin RAM alone does not satisfy Tier-0.

## Platform generality done

- [ ] A second game works through the same Dolphin adapter.
- [ ] Mario Party 4 knowledge remains isolated to its game pack.
- [ ] A second emulator passes the adapter contract.
- [ ] Core runtime requires no title-specific changes.
- [ ] Pack schemas are sufficiently declarative for both games.
- [ ] The game-pack verifier accepts both valid packs and rejects incompatible variants.

## Claim gates

| Claim | Minimum evidence |
|---|---|
| “Observed” | One identified run and preserved artifact |
| “Repeated” | Independent repeated runs with equivalent result |
| “Grounded field” | Repeated positives, negatives, confounders, restart proof, version binding |
| “Canonical” | Approved schema/contract plus independent verification |
| “Replay verified” | Independent verifier and corruption vectors |
| “Deterministic” | Reproduction from equivalent initial conditions with matching checkpoints |
| “Multiplayer supported” | Complete two-instance game plus divergence and recovery tests |
| “Platform” | Second game and second emulator proofs |

