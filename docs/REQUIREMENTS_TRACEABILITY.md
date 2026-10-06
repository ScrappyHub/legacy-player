# Requirements Traceability Matrix

**Baseline:** 2026-08-20

This matrix links the working specification to current implementation evidence. `Present` means code or an artifact exists; it does not mean the requirement is complete.

| Requirement | Current implementation/evidence | Status | Primary gap or next proof |
|---|---|---|---|
| LP-FR-001 process identity | `dolphin_attach/attach.py` | PARTIAL | Executable/version authority and stronger identity |
| LP-FR-002 emulator version | Process metadata in fingerprint output | TODO | Version extraction and compatibility rule |
| LP-FR-003 version-bound game identity | `identity.json`, window-title fingerprint | PARTIAL | Revision/media hash, adapter/pack versions |
| LP-FR-004 fail unsupported profiles | `compatibility.py` | PARTIAL | Replace caller-supplied/title-only authority |
| LP-FR-005 verify adapter/pack at session gate | Session stores identifiers | GAP | Existence and compatibility verification |
| LP-FR-010 enumerate RAM candidates | `ram_map.py` | PRESENT | Complete candidate evidence fixtures |
| LP-FR-011 behavioral validation | `ram_candidate_validator.py` and offline vectors | PARTIAL | Run live action and restart/reload experiments |
| LP-FR-012 ambiguity fails closed | Strict v1 selection policy and adversarial test | PRESENT | Confirm behavior against live mirrored candidates |
| LP-FR-013 restart repeatability | Manual history only | TODO | Repeatable two-run receipt |
| LP-FR-014 RAM-relative offsets | Game-pack candidate files | PARTIAL | Remove/segregate absolute-address assumptions |
| LP-FR-015 read-only discovery | Windows access flags | PRESENT | Controlled-write authorization remains future |
| LP-FR-016 RAM receipt | Evidence/receipt producer plus recomputing verifier | PARTIAL | Preserve live receipts and add cross-run resolver receipt |
| LP-FR-020 field metadata | `STATE_FIELDS_CANDIDATES_v1.json` scaffold | PARTIAL | Type/range/lifetime/phase/evidence completeness |
| LP-FR-021 evidence promotion | Discovery notes | GAP | Enforced confidence lifecycle |
| LP-FR-022 explicit unknown | Some tools expose candidate/unknown behavior | PARTIAL | Uniform schema and tests |
| LP-FR-023 normalized-state schema | `state_model.json` phase scaffold | TODO | Full schema and transforms |
| LP-FR-024 canonical state hash | Checkpoint strings accepted by server | GAP | Define/recompute canonical state bytes |
| LP-FR-025 first board-state set | Candidate/discovery artifacts | TODO | Ground five priority fields |
| LP-FR-030 state-derived events | ADR-0001 | TODO | Implement after grounded state |
| LP-FR-031 confidence/evidence | Prototype classifier artifacts | PARTIAL | Formal event rule schema |
| LP-FR-032 unknown events | Handoff invariant | TODO | Runtime behavior and negative tests |
| LP-FR-033 deterministic event IDs/order | Replay event sequence | PARTIAL | Stable IDs independent of wall clock |
| LP-FR-034 measured classifier errors | Prototype classifier | TODO | Labeled held-out corpus |
| LP-FR-040 replay contents | `ReplayRecorder` | PARTIAL | Initial state, identity, inputs, canonical checkpoints |
| LP-FR-041 transactional replay | Atomic replace in `ReplayStore` | GAP | Limit/storage failure transactionality and durability verification |
| LP-FR-042 package digest | Replay schema string | GAP | Content digest and canonical bytes |
| LP-FR-043 independent verifier | Tests read saved JSON | GAP | Independent package/checkpoint verifier |
| LP-FR-044 safe finalization failure | `LobbyService.complete_session` | GAP | Prevent irreversible half-finalization |
| LP-FR-050 explicit authority | Participant credentials and slot map | PARTIAL | Full authority contract and reconnect identity |
| LP-FR-051 bounded ordered inputs | Lockstep coordinator | PRESENT | Broader adversarial/stale checkpoint policy |
| LP-FR-052 semantic sync boundaries | Candidate JSON and docs | TODO | Empirical boundary proof |
| LP-FR-053 divergence evidence | `DesyncTracker`, replay event | PARTIAL | Bind to recomputed canonical state |
| LP-FR-054 verified recovery | Documentation only | TODO | Choose only after determinism evidence |
| LP-FR-055 two-instance determinism | Conformance engine only | TODO | Real Dolphin long-run proof |
| LP-FR-060 versioned manifests | Several v1 JSON artifacts | PARTIAL | Formal schemas and compatibility matrix |
| LP-FR-061 complete game pack | Mario Party 4 scaffolding | TODO | Fields, phases, events, revisions, evidence |
| LP-FR-062 immutable proof references | Local capture conventions | GAP | Digest-addressed corpus references |
| LP-FR-063 pack verifier | JSON parse validation | GAP | Semantic and integrity verifier |
| LP-NFR-001 deterministic data | Sorted JSON in selected paths | PARTIAL | System-wide canonicalization contract |
| LP-NFR-002 evidence | Discovery artifacts and tests | PARTIAL | Receipt schemas and independent verification |
| LP-NFR-003 path safety | Replay path checks | GAP | Dolphin restore trusts manifest target |
| LP-NFR-004 fail closed | Several bounded validators | PARTIAL | RAM/session/live-gate gaps |
| LP-NFR-005 bounded resources | Server limits | PARTIAL | Transactional behavior when limits hit |
| LP-NFR-006 portable knowledge | RAM-relative intent | PARTIAL | Audit all persisted outputs |
| LP-NFR-007 standalone | No mandatory upstream | PRESENT | Preserve during classification |
| LP-NFR-008 clean reproducibility | `release_check.py`, workflow | PARTIAL | Commit complete tree and validate live evidence separately |
| LP-NFR-009 secrets | Credential tests | PARTIAL | Retention on replay-finalization failure |
| LP-NFR-010 claim discipline | Verification matrix and handoff | PARTIAL | Consolidate status language across older docs |
