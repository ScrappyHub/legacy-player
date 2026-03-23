\# DOLPHIN RAM TARGETING PLAN v1



Purpose:

Move Legacy Player memory discovery from broad host-process readable-region probing to Dolphin emulated RAM targeting, so mutation capture can observe authoritative Mario Party 4 gameplay state.



\## Why this is needed



Broad readable-region probing succeeded technically but produced no gameplay deltas for intentional actions.



Observed:

\- repeated probe runs stable

\- repeated mutation captures returned changed\_region\_count = 0

\- sliding-window scan still returned zero changes



Interpretation:

The current scanner is likely observing stable host/runtime memory rather than authoritative emulated console state.



\## Goal



Add a Dolphin-specific RAM map helper that identifies emulated RAM and lets mutation capture scan deterministic windows inside that RAM only.



\## Scope



Phase 1:

\- add Dolphin RAM map helper

\- expose emulated RAM base/size candidates

\- support deterministic reads from emulated RAM

\- patch mutation capture to prefer RAM-targeted scanning when Dolphin is detected



Phase 2:

\- run labeled mutation captures for simple UI actions

\- identify changed windows and narrow stable state offsets

\- record findings into Mario Party 4 discovery notes



Phase 3:

\- derive candidate state fields for multiplayer sync model

\- classify fields by local-only, shared-turn, shared-board, hidden/private, and transient



\## Working assumptions



For Dolphin + GameCube:

\- authoritative game state is far more likely to live in emulated RAM than generic host heap regions

\- useful state changes may be small and localized

\- repeated labeled actions will make deltas easier to classify than unlabeled exploratory runs



\## Deliverables



1\. tools/memory\_probe/dolphin\_attach/ram\_map.py

&#x20;  - deterministic RAM candidate discovery

&#x20;  - read helpers over emulated RAM ranges

&#x20;  - compact metadata output for base/size/source



2\. tools/memory\_probe/mutation\_capture.py update

&#x20;  - adapter-aware mode for Dolphin

&#x20;  - RAM-targeted window scanning

&#x20;  - compact changed-window summaries

&#x20;  - support action\_label parameter



3\. New labeled test runs

&#x20;  - cursor\_left\_once

&#x20;  - cursor\_right\_once

&#x20;  - confirm\_once

&#x20;  - cancel\_once



4\. Discovery note updates

&#x20;  - add run IDs

&#x20;  - add changed window summaries

&#x20;  - add suspected state offsets/ranges if found



\## Detection strategy



Priority order:

1\. explicit Dolphin emulated RAM signatures if known in-process

2\. memory regions matching expected size/layout characteristics

3\. readable private/mapped regions that consistently behave like emulated RAM

4\. fail closed with explicit token if no strong RAM candidate is found



\## Output contract



Mutation outputs should include:

\- run\_id

\- action\_label

\- ram\_base\_address

\- ram\_region\_size

\- window\_size

\- window\_stride

\- max\_scan\_per\_region

\- changed\_region\_count

\- changed\_window\_count

\- changed\_windows\[]

&#x20; - window\_offset

&#x20; - window\_length

&#x20; - changed\_byte\_count

&#x20; - first\_changed\_offset

&#x20; - last\_changed\_offset



\## Determinism rules



\- UTF-8

\- LF line endings

\- no interactive ambiguity beyond explicit Enter prompts already used

\- compact summaries preferred over large raw hex dumps

\- explicit failure tokens on no-process / no-game / no-ram-map cases



\## Success condition



At least one labeled action produces non-zero changed windows inside Dolphin-targeted emulated RAM, giving a reproducible starting point for Mario Party 4 state field discovery and future multiplayer synchronization work.

