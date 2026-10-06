# Dolphin Probe Plan v1

## Objective

Establish a trustworthy, read-only observation path for one Dolphin and GameCube
profile before implementing controller integration.

## Phases

1. Select exactly one supported Dolphin process.
2. Require the Mario Party 4 `GMPE01` USA profile.
3. Validate a non-empty, exact-size GameCube main RAM allocation.
4. Capture bounded snapshots using offsets relative to the current RAM base.
5. Repeat labeled captures with negative controls.
6. Promote only stable, action-specific fields into the game pack.
7. Use promoted fields as readiness, phase, or desync markers in the shared runtime.

## Success criteria

- Unsupported or ambiguous targets fail explicitly.
- Results remain meaningful when Dolphin host addresses change between runs.
- At least one marker survives repeated positives and negative controls.
- No game-specific policy leaks into the shared runtime or server.

Memory observation is supporting evidence. Playable multiplayer additionally requires
frame-numbered controller capture/injection and peer transport through the adapter.
