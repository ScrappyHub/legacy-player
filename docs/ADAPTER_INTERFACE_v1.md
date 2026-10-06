# Legacy Player Adapter Interface v1

## Purpose

Adapters isolate emulator-specific behavior from the shared multiplayer runtime. The
runtime owns session and synchronization policy; adapters report identity and connect
frame-numbered controller state to an emulator.

## Required identity capabilities

An adapter must report its adapter ID, platform, emulator version, game ID, region,
and revision or content fingerprint when available. It must reject unsupported or
ambiguous targets rather than guessing.

## Controller contract

The executable controller boundary is defined in `adapters/controller.py`.
Implementations provide:

- `current_frame()` for the emulator's canonical simulation frame
- `capture_local_input(slot)` for the locally owned controller
- `inject_remote_input(frame, slot, state)` for released lockstep inputs
- `pause_at_frame(frame)` when the next bundle is not yet available
- `resume()` after the required bundle has been injected

Controller state uses a non-negative button bit field and signed-byte stick axes.
Game-specific meaning does not belong in this interface.

## Observation capabilities

Adapters may expose bounded read-only state observation, validated memory regions,
phase markers, and state hashes. Host memory addresses are diagnostic only; game packs
use canonical offsets or stable identifiers.

## Failure behavior

Failures must identify the unavailable capability, unsupported game profile,
ambiguous emulator instance, invalid memory mapping, missed frame, or injection error.
The adapter must never report readiness when a required synchronization capability is
missing.

## Dolphin implementation sequence

1. Attach to one validated Dolphin instance.
2. Confirm the exact game profile.
3. Select a stable emulator frame counter or callback.
4. Capture the locally owned controller state.
5. Pause before advancing without a complete frame bundle.
6. Inject remote states into their assigned controller slots.
7. Resume and emit diagnostics for every missed or late frame.

The current repository implements the shared contract and observation foundation. A
real Dolphin controller backend remains adapter-specific work.
