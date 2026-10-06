# Legacy Player Risk Register

**Baseline:** 2026-08-20  
**Review cadence:** At each milestone gate and before any release claim

Likelihood and impact use `Low`, `Medium`, `High`, and `Critical`. Owners are work packages until named maintainers are assigned.

| ID | Risk | Likelihood | Impact | Mitigation / exit condition | Owner | Status |
|---|---|---:|---:|---|---|---|
| LP-RISK-001 | Wrong 32 MiB region is treated as authoritative MEM1 | High | Critical | All-candidate validator and ambiguity failure implemented; live/restart proof pending | WBS 6 | OPEN/NEXT LIVE |
| LP-RISK-002 | Window title or self-asserted metadata produces false game identity | High | High | Revision/media fingerprint and independent identity receipt | WBS 2 | OPEN |
| LP-RISK-003 | Page-pattern collisions are mislabeled as semantic events | High | High | ADR-0001; ground fields and phases; unknown classification | WBS 8–12 | MITIGATING |
| LP-RISK-004 | Dynamic absolute addresses contaminate game-pack knowledge | Medium | High | Persist RAM-relative offsets and verify after restart | WBS 6–8 | OPEN |
| LP-RISK-005 | Session accepts nonexistent or incompatible adapter/game pack | High | High | Registry/manifest compatibility gate before readiness | WBS 17/20 | OPEN |
| LP-RISK-006 | Replay event limit or storage failure leaves irreversible partial state | Medium | High | Transactional finalization and injected-failure tests | WBS 13/23 | OPEN |
| LP-RISK-007 | Replay artifact is accepted without independent integrity verification | High | High | Canonical digest and separate verifier | WBS 13 | OPEN |
| LP-RISK-008 | Crafted Dolphin restore manifest overwrites/deletes arbitrary files | Medium | Critical | Constrain root/target; authenticate provenance; verify current target | WBS 23 | OPEN |
| LP-RISK-009 | Incomplete controller bundle causes partial observable input | Medium | High | Validate complete bundle before updates/broadcast | WBS 15/23 | OPEN |
| LP-RISK-010 | Live Dolphin gate passes using heuristic RAM and unrelated DSU client | Medium | High | Bind evidence to verified process/game and correlated adapter endpoint | WBS 1–2/24 | OPEN |
| LP-RISK-011 | Raw memory captures disclose unrelated user/process data | Medium | High | Local-only retention, review/redaction workflow, digest provenance | WBS 23 | OPEN |
| LP-RISK-012 | Research artifacts are promoted to canonical without controls | High | High | Enforce evidence lifecycle and proof references | WBS 0/24 | OPEN |
| LP-RISK-013 | Deterministic claims are made from conformance simulation only | Medium | High | Require two real Dolphin instances and checkpoint evidence | WBS 14–15 | OPEN |
| LP-RISK-014 | Untracked/dirty working tree makes release evidence irreproducible | High | Medium | Clean reviewed commit and clean-checkout CI receipt | WBS 0/22/24 | OPEN |
| LP-RISK-015 | Game-specific assumptions leak into core runtime | Medium | High | Adapter/pack contract tests and second-game proof | WBS 17–19 | OPEN |
| LP-RISK-016 | Unapproved ecosystem role is treated as canonical | High | High | Approve Proposal 0001 and update registry atomically | WBS 0 | OPEN |
| LP-RISK-017 | Multiplayer design proceeds before authoritative state exists | Medium | Critical | Enforce WBS dependency order; MEM1/state gates precede sync claims | WBS 6–15 | MITIGATING |
| LP-RISK-018 | Recovery mutates emulator state without sufficient authority | Low now | Critical | Read-only default; separate write capability and safety review | WBS 16/23 | DEFERRED |

## Release blockers

The following block the associated claim:

- Tier-0: LP-RISK-001, 002, 007, 012, 014, 016.
- Replay verified: LP-RISK-006 and 007.
- Multiplayer supported: LP-RISK-001, 002, 005, 009, 010, 013, 017.
- Safe configuration tooling: LP-RISK-008.

Closing a risk requires a linked test or receipt; changing `OPEN` to `CLOSED` without evidence is not sufficient.
