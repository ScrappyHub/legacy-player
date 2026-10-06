# Legacy Player Verification Matrix v1

## Verified automatically

| Capability | Evidence |
|---|---|
| Session lifecycle and compatibility | Unit and service tests |
| Ready barrier and bounded lockstep | Unit and adversarial tests |
| TCP create/join/input/poll flow | Real loopback TCP integration |
| DSU packet encoding and CRC | Wire-format tests |
| DSU discovery and pad reports | Real loopback UDP integration |
| Coordination-to-virtual-pad path | End-to-end TCP plus UDP test |
| Desync mismatch termination | Two-peer checkpoint test |
| Atomic replay generation | Filesystem tests |
| Malformed and oversized requests | Adversarial TCP tests |
| Credential and path handling | Authentication and traversal tests |
| Frame-control authentication and ordering | IPC conformance tests |
| Deterministic bridge continuity | 30-frame network and 5,000-frame engine tests |
| Managed Dolphin configuration | Isolated profile generation and manifest test |
| Existing Dolphin configuration | Backup, install, hash verification, and restore test |
| RAM candidate decision and receipt integrity | Unique, ambiguous, unchanged, partial, corrupted, and forged offline vectors |

Run all automatic gates with:

```powershell
python tools/release_check.py
```

## Required live gate

The release is not eligible for deterministic multiplayer claims until a supported
Dolphin instance is running Mario Party 4 `GMPE01` USA, DSU input is configured, and:

```powershell
python tools/release_check.py --require-dolphin
```

passes. The current live check exercises the title-derived `GMPE01`/USA profile gate,
finds a plausible nonempty exact 32 MiB mapping, and observes a DSU subscriber. These
are prototype checks: they do not prove game revision/media identity, behavioral MEM1
authority, or that the subscriber belongs to the selected Dolphin process.

The live check does not replace the interactive behavioral RAM candidate protocol in
`adapters/dolphin/DOLPHIN_RAM_VALIDATION_v1.md`. Milestone-A RAM authority additionally
requires a unique behavioral result and restart/reload repetition.

## Remaining deterministic gate

DSU does not expose emulator pause or canonical frame callbacks. Even after the live
DSU check passes, deterministic multiplayer requires a Dolphin frame-control extension
or integration with Dolphin's native netplay input machinery, followed by a two-instance
long-run test with periodic state checkpoints and zero unexplained divergence.
