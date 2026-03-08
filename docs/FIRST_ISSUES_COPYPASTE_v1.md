# Legacy Player First Issues — Copy/Paste Titles and Bodies

## Issue 1

### Title

```text
Bootstrap: publish GitHub templates and workflow
Body
## Goal

Add the initial GitHub project management and validation surfaces.

## Scope

Create:

- `.github/workflows/docs-check.yml`
- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/feature_request.md`
- `.github/ISSUE_TEMPLATE/game_pack_request.md`
- `.github/ISSUE_TEMPLATE/adapter_request.md`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/CODEOWNERS`

## Success condition

The repo has a clean issue intake flow and a basic docs validation workflow.
Issue 2
Title
Runtime: create initial runtime module scaffold
Body
## Goal

Establish the shared runtime structure for Legacy Player.

## Scope

Create:

- `runtime/session/`
- `runtime/sync/`
- `runtime/state/`
- `runtime/desync/`
- `runtime/replay/`
- `runtime/patch/`

Add minimal README or placeholder files as needed to preserve structure.

## Success condition

The repo has a real runtime scaffold with clear module boundaries.
Issue 3
Title
Adapter: create Dolphin adapter scaffold
Body
## Goal

Create the first Legacy Player platform adapter scaffold.

## Scope

Create the initial Dolphin adapter structure and align it with `docs/ADAPTER_INTERFACE_v1.md`.

Focus on:

- identity
- capability reporting
- future game fingerprint support
- future state observation support

## Success condition

The repo has a real adapter scaffold for Dolphin with a stable architectural role.
Issue 4
Title
Game Pack: create Mario Party 4 pack scaffold
Body
## Goal

Create the first real game pack scaffold for Legacy Player.

## Scope

Create the initial `game_packs/mario_party_4/` structure and align it with:

- `docs/GAME_PACK_SPEC_v1.md`
- `docs/FIRST_TARGET_MARIO_PARTY_v1.md`

Include initial placeholders for:

- identity
- state model
- synchronization boundaries
- compatibility rules
- replay markers

## Success condition

The repo has a first-class game pack scaffold that demonstrates the intended project growth model.
Issue 5
Title
Research: define first Mario Party 4 support profile
Body
## Goal

Lock the initial supported profile for the first Mario Party target.

## Scope

Determine and document:

- target title
- region/revision
- expected emulator path
- initial session assumptions
- initial support boundaries

## Success condition

Legacy Player has one explicit first supported target path instead of vague broad claims.
Issue 6
Title
Runtime: draft initial replay and diagnostics event model
Body
## Goal

Define the first event model for replay metadata and mismatch diagnostics.

## Scope

Draft the structure for:

- session start events
- ready-state events
- boundary events
- mismatch events
- session end events

## Success condition

Replay and diagnostics are designed as first-class runtime outputs from the beginning.
Issue 7
Title
Adapter Research: investigate Dolphin game fingerprint surface
Body
## Goal

Define how the Dolphin adapter will identify active titles in a structured way.

## Scope

Investigate a practical fingerprint model for:

- title identity
- region/revision
- compatibility-relevant profile selection

## Success condition

The adapter path has a clear direction for selecting a matching game pack.
Issue 8
Title
Game Pack: define Mario Party 4 phase and boundary model
Body
## Goal

Define the first scene and synchronization boundary model for Mario Party 4.

## Scope

Document expected major phases such as:

- boot/title
- setup
- board flow
- minigame entry
- minigame active
- results/return flow

Define where synchronized barriers are most likely needed.

## Success condition

The first game pack has a usable orchestration model for the runtime.
Issue 9
Title
Runtime: implement first private session lifecycle scaffold
Body
## Goal

Create the first session lifecycle model for Legacy Player.

## Scope

Model:

- session creation
- participant join
- readiness tracking
- compatibility check point
- active-session entry
- session completion/failure state

## Success condition

The runtime can represent the shape of a real multiplayer session before full live integration.
Issue 10
Title
First Proof: connect runtime, Dolphin adapter, and Mario Party 4 game pack
Body
## Goal

Create the first end-to-end controlled proof path for Legacy Player.

## Scope

Connect:

- runtime selection flow
- Dolphin adapter identity flow
- Mario Party 4 game pack load flow
- ready-state barrier flow
- replay metadata output
- explicit failure reporting

## Success condition

Legacy Player has a single explainable first proof path that demonstrates the real architecture.

# Repo target tree

```text
legacy-player/
├─ README.md
├─ LICENSE
├─ .gitignore
├─ docs/
│  ├─ VENTURE_LAB_PITCH.md
│  ├─ ARCHITECTURE.md
│  ├─ RUNTIME_SPEC_v1.md
│  ├─ GAME_PACK_SPEC_v1.md
│  ├─ LEGAL_POSITION.md
│  ├─ ROADMAP.md
│  ├─ IMPLEMENTATION_PLAN_v1.md
│  ├─ ADAPTER_INTERFACE_v1.md
│  ├─ FIRST_TARGET_MARIO_PARTY_v1.md
│  ├─ FIRST_ISSUES_AND_MILESTONES_v1.md
│  └─ FIRST_ISSUES_COPYPASTE_v1.md
├─ runtime/
│  ├─ README.md
│  ├─ session/
│  ├─ sync/
│  ├─ state/
│  ├─ desync/
│  ├─ replay/
│  └─ patch/
├─ adapters/
│  └─ dolphin/
│     └─ README.md
├─ game_packs/
│  └─ mario_party_4/
│     └─ README.md
├─ server/
│  ├─ README.md
│  ├─ lobby/
│  ├─ relay/
│  └─ api/
├─ tools/
│  ├─ README.md
│  ├─ memory_probe/
│  ├─ replay_inspector/
│  └─ pack_builder/
└─ .github/
   ├─ CODEOWNERS
   ├─ PULL_REQUEST_TEMPLATE.md
   ├─ labels.md
   ├─ workflows/
   │  └─ docs-check.yml
   └─ ISSUE_TEMPLATE/
      ├─ bug_report.md
      ├─ feature_request.md
      ├─ game_pack_request.md
      ├─ adapter_request.md
      └─ config.yml
