# Dolphin Frame-Control Protocol v1

## Purpose

This protocol is the executable contract for deterministic Dolphin integration. It is
separate from DSU: DSU remains useful for ordinary virtual-pad delivery, while frame
control guarantees that Dolphin cannot advance a simulation frame without the complete
released controller bundle.

## Transport and authentication

- TCP bound to `127.0.0.1` only
- Four-byte network-order message length followed by canonical compact JSON
- Maximum message size: 64 KiB
- Strict monotonically increasing request sequence
- `hello` must be first and must include protocol version, session ID, and a random
  token of at least 32 characters
- Tokens are compared in constant time and supplied by environment or protected file

## Required lifecycle

For every frame, the bridge performs exactly:

1. `pause(frame)`
2. one `inject(frame, slot, state)` for every configured controller slot
3. `advance(frame)`
4. `state_hash(frame)`

The emulator must reject skipped frames, duplicate slots, missing slots, invalid
controller ranges, replayed sequences, and advance requests for a frame that is not
currently paused.

## Dolphin integration points

Current upstream Dolphin routes GameCube controller reads through
`CSIDevice_GCController::GetPadStatus()` and then `HandleMoviePadStatus()`. That path
already gives native netplay first opportunity to provide controller input through
`NetPlay_GetInput`; movie playback/recording follows afterward. A native Legacy Player
provider should integrate at this established input-selection boundary rather than
write controller values into emulated RAM.

Frame blocking should reuse Dolphin's existing netplay synchronization model and core
thread coordination. It must not block arbitrary UI or network threads while holding
Dolphin global locks. State hashes must cover locally configured, game-pack-approved
state fields and must not expose an arbitrary remote memory-read API.

Official upstream references:

- https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/HW/SI/SI_DeviceGCController.cpp
- https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/NetPlayClient.cpp
- https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/Movie.cpp
- https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/CoreTiming.cpp

## Conformance implementation

`runtime/frame_control` contains the bounded protocol, authenticated client, and a
deterministic conformance server. `DeterministicDolphinBridge` consumes released
lockstep bundles and enforces pause/inject/advance/hash ordering. The conformance engine
is a test oracle, not a claim that unmodified Dolphin exposes these capabilities.

## Native release gate

The Dolphin integration is complete only when a current upstream checkout can:

1. build with the optional provider disabled and enabled;
2. pass Dolphin's existing unit tests;
3. pass the Legacy Player conformance suite;
4. run two `GMPE01` instances for a long session with identical periodic state hashes;
5. disconnect or fail cleanly under missing input, malformed IPC, and peer loss.
