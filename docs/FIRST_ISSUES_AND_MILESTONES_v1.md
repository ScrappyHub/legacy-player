# Legacy Player First Issues and Milestones v1

## Milestone 1 — Repo Bootstrap and Spec Lock

Purpose:

Establish the public repo, baseline documentation, and implementation direction.

Recommended issues:

1. Publish root repo documents
2. Publish runtime, adapter, game pack, server, and tools readmes
3. Add GitHub issue templates and PR template
4. Add docs-check workflow
5. Finalize first-target direction for Mario Party 4

Success condition:

The repo is publicly coherent and the first implementation path is locked.

---

## Milestone 2 — Runtime Skeleton

Purpose:

Create the shared orchestration structure before emulator integration.

Recommended issues:

1. Create runtime/session skeleton
2. Create runtime/sync skeleton
3. Create runtime/state skeleton
4. Create runtime/desync skeleton
5. Create runtime/replay skeleton
6. Create runtime/patch skeleton
7. Draft runtime event model

Success condition:

The runtime exists as a real project structure with clear module boundaries.

---

## Milestone 3 — Dolphin Adapter Foundation

Purpose:

Create the first platform bridge for Legacy Player.

Recommended issues:

1. Create Dolphin adapter scaffold
2. Add adapter identity and capability model
3. Add active title fingerprint investigation path
4. Add basic state observation investigation path
5. Add controller/input observation investigation path

Success condition:

Legacy Player can identify a supported Dolphin-driven target in a structured way.

---

## Milestone 4 — First Mario Party Game Pack

Purpose:

Create the first game-aware support layer.

Recommended issues:

1. Create Mario Party 4 game pack scaffold
2. Define initial identity profile
3. Define initial scene/phase model
4. Define synchronization boundary model
5. Define compatibility rules
6. Define replay markers
7. Define first mismatch diagnostics expectations

Success condition:

The runtime can load a first game pack and reason about its support model.

---

## Milestone 5 — First Controlled Session Proof

Purpose:

Prove the system can orchestrate one real supported path.

Recommended issues:

1. Create private session flow
2. Add ready-state barrier flow
3. Connect Dolphin adapter to runtime selection flow
4. Connect Mario Party 4 game pack to runtime selection flow
5. Emit first replay metadata package
6. Emit first explicit mismatch diagnostics

Success condition:

A controlled multiplayer session proof exists with explicit replay and diagnostics output.

---

## Milestone 6 — Runtime-Assisted Stabilization

Purpose:

Move from observation-only to assisted orchestration.

Recommended issues:

1. Add menu synchronization barrier model
2. Add scene transition coordination model
3. Add controller ownership assumptions
4. Add critical state hash/checkpoint model
5. Add clean failure policy for boundary violations

Success condition:

Legacy Player begins to stabilize multiplayer behavior instead of only observing it.
