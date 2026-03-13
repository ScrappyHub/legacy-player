\# Mario Party 4 Phase Discovery Notes v1



\## Target Profile



\- Game: Mario Party 4

\- Platform: GameCube

\- Emulator: Dolphin

\- Game ID: GMPE01

\- Region: USA



\---



\## Objective



Move from fingerprint proof into repeatable coarse phase capture.



Initial target phases:



\- loaded

\- setup

\- board

\- minigame\_entry

\- minigame\_active

\- results



\---



\## Current Proven Signals



The probe currently proves:



\- Dolphin attach

\- active window title selection

\- GMPE01 extraction

\- USA region derivation

\- phase hint emission

\- stable timed sampling while the process remains alive



\---



\## Current Limitation



The current phase hint is title-driven and remains `loaded` for the current observed title.



That means the next pass is not adding more guessed title rules first.



The next pass is collecting repeated runs across manually chosen scenes and comparing emitted events.



\---



\## Capture Plan



Run the probe separately while the game is placed in each of these contexts:



1\. title or initial loaded state

2\. setup or mode select

3\. board gameplay

4\. minigame entry

5\. minigame active

6\. results



For each run, record:



\- run id

\- intended visible scene

\- active window title

\- emitted phase hint

\- whether `phase\_transition\_candidate` appeared

\- whether `active\_window\_title\_changed` appeared



\---



\## What To Look For



The first question is simple:



\- does the active window title change across these scenes



If yes, title-driven hints can be refined.



If no, the next authoritative step is memory-backed phase discovery.



\---



\## Current Status



Known good profile:



\- GMPE01

\- USA

\- Dolphin



Known current coarse phase output:



\- loaded



\---



\## Near-Term Goal



Complete one capture run for each target scene and compare outputs before moving to memory-backed state capture.

