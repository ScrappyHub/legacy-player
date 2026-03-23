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


## Discovery update — broad host-region probing

Repeated probe comparison and mutation capture runs produced stable outputs but no changed regions for simple UI/menu actions.

Observed:
- probe-4880fc8c vs probe-98e9c92c => changed_region_count: 0
- mutation-5271d367 => changed_region_count: 0
- mutation-2019d882 => changed_region_count: 0
- mutation-bccc71ed_unlabeled_action => changed_region_count: 0
- scan settings: window_size=256, window_stride=64, max_scan_per_region=16384

Interpretation:
The current scanner is likely observing stable host/runtime memory rather than authoritative emulated Mario Party 4 state.

Next step:
Shift discovery to Dolphin emulated RAM targeting via adapter-specific RAM map and repeat labeled action captures against emulated memory only.



## 2026-03-23 — Page Hash Sweep / Window Tracker Layer

Current conclusion:
- Sparse sampled mutation capture across selected Dolphin RAM candidate has repeatedly returned zero changed windows.
- Deep post-action snapshots also returned zero changed windows for:
  - roll_dice_once
  - coin_total_change_once
  - inboard_event_transition_once
  - board_space_land_once
- This strongly suggests the current fixed sparse-window strategy is still observing the wrong representation of state.

Next locked workflow:
1. Run page_hash_sweep.py on meaningful board/gameplay actions.
2. Identify changed pages first.
3. Only after changed pages are found, run window_tracker.py on those pages.
4. Compare repeated same-action runs for overlap.

Current success criterion:
- First success is not finding exact state addresses.
- First success is finding one or more changed pages for repeated labeled actions.

If page_hash_sweep also returns zero changed pages for meaningful gameplay events, next escalation is:
- full contiguous page sweep over a larger RAM budget
- or emulator-aware mapped-memory extraction rather than generic readable-region reads
