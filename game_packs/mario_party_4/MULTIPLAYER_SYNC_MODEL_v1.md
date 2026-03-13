\# Mario Party 4 Multiplayer Sync Model v1



\## Target Profile



\- Game: Mario Party 4

\- Platform: GameCube

\- Emulator: Dolphin

\- Game ID: GMPE01

\- Region: USA



\---



\## Objective



Define the multiplayer-facing synchronization model that Legacy Player is working toward.



This document is intentionally early and discovery-oriented.



\---



\## Multiplayer Stack



1\. detect

2\. observe

3\. model

4\. synchronize

5\. transport

6\. session authority



Current active work is in observe + model.



\---



\## Synchronization Categories



\### Authoritative Session Fields



These fields should become the backbone of multiplayer validation:



\- game\_id

\- region

\- scene\_phase

\- turn\_number

\- active\_player

\- minigame\_state



\### Player-State Fields



These are likely to matter for game progression:



\- board\_position

\- coins

\- stars

\- current\_choice

\- cursor\_state



\### Sync-Boundary Fields



These are likely event boundaries where reconciliation should occur:



\- setup confirmed

\- board turn begins

\- dice roll resolves

\- movement resolves

\- minigame begins

\- minigame ends

\- results commit



\### Desync Detection Fields



These should later be derived into compact validation hashes:



\- scene hash

\- candidate state hash

\- active phase marker

\- per-player compact state summary



\---



\## Transport Intent



Legacy Player is aiming for a self-hosted multiplayer service.



The intended model is:



\- self-hosted room/session authority

\- deterministic event transport where possible

\- snapshot comparison at sync boundaries

\- resync on mismatch

\- game-pack-defined state models per title



\---



\## Discovery Rule



Until named state fields are proven, synchronization must remain discovery-first.



Raw memory regions are not yet authoritative gameplay fields.



They are candidate evidence surfaces only.



\---



\## Next Engineering Goal



Turn memory-region mutation capture into repeatable candidate field discovery for:



\- scene\_phase

\- active\_player

\- turn\_number

\- cursor\_state

\- board\_position

