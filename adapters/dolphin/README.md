# Dolphin Adapter

The current executable Dolphin backend injects released multiplayer controller states
through Dolphin's built-in DualShock UDP (DSU/Cemuhook) input client. It does not write
controller values into emulated RAM.

## Dolphin setup

1. Start the Legacy Player coordination server.
2. In Dolphin, open Controller Settings and then Alternate Input Sources.
3. Enable DSU input and add `127.0.0.1:26760`.
4. Configure each emulated GameCube controller from the corresponding
   `DSUClient/<slot>/...` device.
5. Map DSU `Cross`, `Circle`, `Square`, `Triangle`, shoulder, D-pad, and stick inputs
   to the desired GameCube controls.

Run the bridge after the session has been created:

```powershell
python -m adapters.dolphin.bridge `
  --session-id SESSION_ID `
  --participant-id PARTICIPANT_ID `
  --map host:0 `
  --map peer:1
```

Set `LEGACY_PLAYER_CREDENTIAL` in the bridge environment, or pass a local
`--credential-file`. Credentials are intentionally not accepted as command-line values
because process arguments are visible to other local tools.

The participant-to-slot mapping must include every participant in each released frame.
Slots are zero-based and range from 0 through 3.

## Button representation

The shared `buttons` field uses `GameCubeButtons` from `dsu_protocol.py`. The DSU bridge
maps GameCube A/B/X/Y to DSU Cross/Circle/Square/Triangle and exposes the remaining
controls through DSU D-pad and shoulder inputs. Dolphin's controller profile performs
the final mapping into GameCube ports.

## Determinism limitation

DSU is an officially supported external input source, but it does not expose Dolphin's
canonical emulation-frame callback or pause/resume control. The bridge therefore
rejects missing network frame bundles but cannot stop Dolphin itself from advancing.
This is suitable for proving controller delivery, not yet deterministic netplay.

The next deterministic path requires either:

- integration with Dolphin's existing netplay/movie input machinery, or
- a small upstream-compatible Dolphin extension that exposes frame callbacks and
  controlled input injection.

Direct writes to guessed controller memory are intentionally out of scope.
