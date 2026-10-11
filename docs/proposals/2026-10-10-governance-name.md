# Proposal: one name for the governing ecosystem (Constellation, not Atlas)

**Date:** 2026-10-10
**Status:** Proposal; not approved. Changes no canonical file.
**Decision owners:** the Constellation ecosystem maintainers and the repository owner.

## The mismatch

The files that govern this repository name the ecosystem **Constellation**:

- `CLAUDE.md` and `AGENTS.md`: "the `legacy-player` service inside the Constellation deterministic software ecosystem",
  "Ecosystem authority: Constellation (`constellation`)".
- `project.contract.json`: `service_map_path` and `registry_path` point at `../Constellation/...`.
- `docs/canonical/ECOSYSTEM_INTEGRATION.md` (canonical): its authoritative sources are `../Constellation/...`, and its
  change-governance section requires "Updated registry entries in Constellation" and "a new Constellation doctor receipt".

Some non-canonical documents still use an older name, **Atlas** / **Atlas Systems**:

| Document | Text | Kind |
|---|---|---|
| `docs/PROJECT_DOCUMENTATION_INDEX.md` | "Atlas ecosystem service map, registry, agent policy, and shared invariants" | Index (non-canonical). **Fixed in this change** to say Constellation. |
| `docs/proposals/0001_CLASSIFY_LEGACY_PLAYER.md` | "Decision owners: Atlas Systems ecosystem maintainers" | Open proposal; left as written. |
| `docs/proposals/2026-10-07-audit-and-fixes.md` | "the rest of the Atlas Systems ecosystem" | Dated note; left as written. |
| `docs/audits/AUDIT_2026-08-20.md` | "Atlas service map, registry, agent policy, and shared invariants" | Dated audit; never rewritten (index maintenance rule). |

No canonical file uses "Atlas", so there is no conflict inside the canonical set; the mismatch is between the canonical
set and older working documents. The current repository could not confirm whether "Atlas" was a former name of
Constellation or a separate body (the `../Constellation` checkout is not present next to this repository).

## Proposed resolution

1. Treat **Constellation** as the governing ecosystem's name everywhere (it is what every canonical and contract file says).
2. Ask the Constellation maintainers to confirm that "Atlas" / "Atlas Systems" was an earlier name for the same body. If
   so, amend proposal 0001's "Decision owners" line to "Constellation ecosystem maintainers" through that proposal's own
   review, and leave dated audits and notes unchanged (they record what was true when written).
3. If "Atlas" is a different body, record its relationship to Constellation in `docs/canonical/ECOSYSTEM_INTEGRATION.md`
   through the change-governance steps listed there (proposal, compatibility impact, registry update, receipt).

## Compatibility impact

None on code, schemas, receipts or behaviour. Documentation only.
