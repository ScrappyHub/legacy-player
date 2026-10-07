# Legacy Player Documentation Index

**Updated:** 2026-08-20

This page identifies which document answers each project question and prevents older planning artifacts from being mistaken for current proof.

## Governing order

1. Atlas ecosystem service map, registry, agent policy, and shared invariants.
2. `docs/canonical/ECOSYSTEM_INTEGRATION.md` and `project.contract.json`.
3. Approved repository canonical documents, when added through governance.
4. Working project specification and accepted architecture decisions.
5. WBS, Definition of Done, traceability, risks, and dated audits.
6. Component specifications and historical discovery artifacts.

When documents conflict, the higher item governs. Implementation is evidence of current state, not permission to redefine the product.

## Core document set

| Question | Document | Status |
|---|---|---|
| What is the currently approved ecosystem role? | `docs/canonical/ECOSYSTEM_INTEGRATION.md` | Canonical; currently unclassified |
| What role is proposed? | `docs/proposals/0001_CLASSIFY_LEGACY_PLAYER.md` | Proposal; not approved |
| What are we building? | `docs/PROJECT_SPEC.md` | Working specification |
| Why are events state-derived? | `docs/decisions/ADR-0001_STATE_FIRST_EVENT_EXTRACTION.md` | Working architecture decision |
| In what order do we build it? | `docs/WBS.md` | Active plan |
| What does “done” mean? | `docs/DEFINITION_OF_DONE.md` | Active completion policy |
| What evidence is required? | `docs/EVIDENCE_AND_RECEIPTS.md` | Active evidence policy |
| Where is each requirement implemented? | `docs/REQUIREMENTS_TRACEABILITY.md` | Living matrix |
| What can make the project fail? | `docs/RISK_REGISTER.md` | Living register |
| What did the latest audit find? | `docs/audits/AUDIT_2026-08-20.md` | Dated audit |

## App, release and operations documents

- `README.md` — what the app does today and how to install it.
- `docs/RELEASE.md` — build, publish and install a release (GitHub workflow, `install.ps1`, local packaging).
- `docs/HOSTING_PUBLIC_SERVER.md` — run a shared server and the problem-report receiver.
- `docs/MULTIPLAYER_TEST_PLAN.md` — the cross-network test, step by step.
- `docs/WINDOWS_CHECKLIST.md` — what to check by hand on a real Windows computer.
- `docs/LIBRARY_AND_LAUNCHER_v1.md`, `docs/NETPLAY_BY_CONSOLE.md` — launcher design and per-console netplay status.
- `docs/proposals/2026-10-07-audit-and-fixes.md` — October 2026 audit, fixes and follow-ups (problem reports, router opening,
  player counts, shared-server fallback).

## Existing component documents

- `docs/ARCHITECTURE.md` — original architecture overview.
- `docs/RUNTIME_SPEC_v1.md` — runtime target responsibilities.
- `docs/GAME_PACK_SPEC_v1.md` — conceptual game-pack content.
- `docs/ADAPTER_INTERFACE_v1.md` — adapter boundary draft.
- `docs/WIRE_PROTOCOL_v1.md` — current private coordination protocol.
- `docs/DOLPHIN_DSU_BACKEND_v1.md` — DSU controller-delivery design.
- `docs/DOLPHIN_FRAME_CONTROL_PROTOCOL_v1.md` — frame-control contract and conformance layer.
- `adapters/dolphin/DOLPHIN_RAM_VALIDATION_v1.md` — behavioral all-candidate RAM protocol and receipt rules.
- `docs/THREAT_MODEL_v1.md` — current threat model; must be updated as audit risks close.
- `docs/VERIFICATION_MATRIX_v1.md` — existing automated/live gate summary.
- `tools/memory_probe/PROBE_SPEC_v1.md` — memory-probe behavior.
- `adapters/dolphin/DOLPHIN_RAM_TARGETING_PLAN_v1.md` — RAM-targeting plan.
- `game_packs/mario_party_4/*` — title-specific discovery, candidate, and scaffold artifacts.

## Historical-evidence rule

The following remain valuable but are not current canonical truth unless revalidated against an authoritative RAM-resolution receipt:

- v1 hot RAM windows;
- action page clusters;
- byte-pattern classifiers;
- absolute memory addresses;
- page-only action labels;
- the former `start_minigame_once` interpretation;
- static RAM candidate rankings.

Do not delete historical evidence. Add a new version with provenance and explain why it supersedes an earlier interpretation.

## Maintenance rules

- Update traceability and risks in the same change as a requirement or capability status change.
- Add a dated audit rather than rewriting historical audit results.
- Change ecosystem role/ownership only through a proposal and coordinated registry update.
- Update a Definition-of-Done checkbox only when the referenced evidence exists.
- Never use a green unit suite alone as proof of a live emulator, game identity, deterministic replay, or multiplayer claim.
