# Legacy Player Roadmap

## Phase 0 — Repo and spec lock

Goals:

- establish public repo structure
- publish README
- publish Venture Lab pitch
- publish architecture
- publish runtime spec
- publish game pack spec
- publish legal position

Outcome:

Project is publicly understandable and properly framed.

---

## Phase 1 — Core prototype

Goals:

- establish basic runtime structure
- define first adapter interface
- define first game pack interface
- select first supported title
- select first session model

Recommended first target:

- Dolphin
- Mario Party

Outcome:

Foundation exists for first proof of online session orchestration.

---

## Phase 2 — First playable proof

Goals:

- adapter can identify target game
- session can be created and joined
- compatibility checks can run
- synchronization barrier logic exists
- replay metadata capture begins

Outcome:

First controlled multiplayer proof.

---

## Phase 3 — Runtime-assisted support

Goals:

- add scene transition coordination
- add menu synchronization barriers
- add critical state mismatch detection
- add desync diagnostics

Outcome:

System becomes robust enough to support runtime-assisted multiplayer.

---

## Phase 4 — Replay and diagnostics

Goals:

- deterministic replay package shape
- state hash checkpoints
- replay inspection tools
- stronger failure analysis surfaces

Outcome:

Legacy Player becomes useful not only for play, but also for debugging, events, and preservation.

---

## Phase 5 — Game class expansion

Goals:

- add second party-game title
- abstract shared class logic
- begin sports-game strategy exploration

Outcome:

Framework proves it can grow through reusable patterns.

---

## Phase 6 — Platform expansion

Goals:

- evaluate mGBA adapter path
- evaluate RetroArch adapter path
- formalize adapter compatibility matrix

Outcome:

Project expands from one-platform proof toward broader infrastructure.

---

## Long-term direction

Legacy Player may ultimately become:

- a retro multiplayer infrastructure platform
- a replay archive platform
- a preservation-adjacent multiplayer history tool
- a multiplayer research foundation for CDE
