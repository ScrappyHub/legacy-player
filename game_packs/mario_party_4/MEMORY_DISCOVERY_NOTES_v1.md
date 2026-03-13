# Mario Party 4 Memory Discovery Notes v1

## Target Profile

- Game: Mario Party 4
- Platform: GameCube
- Emulator: Dolphin
- Game ID: GMPE01
- Region: USA

---

## Current State

The probe can now:

- identify the game profile
- inventory readable host regions
- rank candidate dynamic regions
- sample non-null bytes from candidate regions
- emit stable region hashes

---

## Interpretation

The current candidate regions are readable and stable within a single run.

That is useful.

It means the next task is not intra-run change hunting first.

The next task is cross-run comparison across different visible scenes and intentional in-scene mutations.

---

## Next Capture Plan

Perform separate runs in clearly different game contexts, for example:

- title
- setup
- board
- minigame entry
- minigame active
- results

Also perform mutation captures where one controlled action occurs between snapshots, for example:

- move cursor once
- confirm menu option
- roll dice
- advance prompt
- enter minigame

---

## Comparison Goal

Identify candidate regions whose sampled hashes differ across:

- scene runs
- mutation captures

Those regions become the first serious leads for memory-backed phase detection and state extraction.