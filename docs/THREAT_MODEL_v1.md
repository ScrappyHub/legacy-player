# Legacy Player Threat Model v1

## Scope

This model covers the coordination TCP service, session runtime, replay storage,
Dolphin DSU bridge, and Windows Dolphin memory probes. It does not claim the emulator,
game image, operating system, or future public discovery service is trusted.

## Assets

- Private session membership and participant credentials
- Ordered controller inputs and replay history
- Session compatibility and desync decisions
- Local filesystem integrity
- Dolphin process integrity and availability
- Raw memory-capture exports, which may contain user or process data

## Trust boundaries

1. JSON/TCP requests cross from clients into the coordination service.
2. Released input bundles cross from the service into each Dolphin bridge.
3. DSU/UDP packets cross from the bridge into Dolphin's input subsystem.
4. Read-only Windows process APIs cross into Dolphin memory.
5. Replay and diagnostic artifacts cross onto the local filesystem.
6. Authenticated frame-control IPC crosses into a future native Dolphin provider.
7. Automatic configuration crosses into Dolphin's user configuration directory.

## Threats and controls

### Unauthorized session access

Sessions use cryptographically random join codes and participant-scoped credentials.
Credentials are compared in constant time, omitted from status and replay data, removed
when sessions finish/fail/expire, and should be supplied to the bridge through an
environment variable or credential file rather than process arguments.

Residual risk: the v1 TCP protocol is plaintext. The server binds to loopback by
default and refuses non-loopback binding without an explicit insecure override. Remote
deployment requires an authenticated TLS proxy or a future native secure transport.

### Resource exhaustion

The server bounds request size, requests per connection, concurrent connections,
active sessions, participants, frame lead, released-frame history, pending desync
checkpoints, replay events, finalized-session retention, DSU subscribers, and idle
session lifetime. Oversized or malformed messages return structured errors.

Residual risk: limits are process-local and there is no distributed rate limiter.

### Input forgery, reordering, and replay

Only authenticated participants can submit their own input. Duplicate, stale, overly
future, non-contiguous, incomplete, and unmapped frames are rejected. SHA-256 state
checkpoints terminate a session when peers disagree.

Residual risk: TCP credentials can be stolen by a privileged local process. DSU itself
has no authentication, so another local process could spoof UDP controller packets.

The deterministic frame-control contract is separately authenticated, session-bound,
length-bounded, sequence-checked, and loopback-only. It exposes fixed controller and
state-hash operations rather than arbitrary memory access. A native implementation
must avoid blocking while holding Dolphin global locks and must close on malformed IPC.

### Artifact and path attacks

Replay names derive only from generated UUID session IDs. Storage resolves and checks
the final path, writes through a temporary file, flushes it, and atomically replaces
the target. Replay records exclude credentials.

Memory-probe exports remain ignored by Git and require manual review before sharing.
They may contain raw emulator memory, executable paths, and command lines.

Managed Dolphin configuration is isolated through Dolphin's `--user` directory and is
the default. Existing-profile setup changes only `DSUClient.ini`, writes a timestamped
backup first, records its SHA-256 hash, and provides verified restoration. Launch paths
are passed without a shell. Legacy Player never silently terminates a user-owned
Dolphin process to force configuration reload.

### Emulator/process corruption

Memory probes request read-only process rights and reject ambiguous Dolphin processes,
unsupported game profiles, and unverified RAM allocations. Controller injection uses
Dolphin's supported DSU input interface rather than guessed memory writes.

Residual risk: DSU cannot pause Dolphin at a missing emulation frame. The current
bridge verifies network-frame continuity but is not deterministic netplay until a
tested Dolphin frame-control integration exists.

## Security release gates

- All unit, TCP, UDP, adversarial, replay, and desync tests pass.
- The server remains loopback-only unless protected by authenticated encryption.
- No credentials appear in logs, replay packages, command arguments, or status output.
- A supported Dolphin build completes live pad discovery and input mapping validation.
- Deterministic claims remain disabled until live frame-control and two-instance desync
  testing pass.
