# Legacy Player Memory Probe

This Windows-only toolkit attaches read-only to Dolphin and gathers controlled memory
observations for the Mario Party 4 `GMPE01` USA game pack.

It currently supports process discovery, title-based game identification, GameCube RAM
candidate enumeration, strict behavioral candidate validation, bounded snapshots,
page/window deltas, and structured local exports. It does not yet prove restart-stable
MEM1 authority, capture controllers, synchronize peers, or provide netplay.

## Safety and validity

- Run from the repository root.
- Use exactly one supported Dolphin process.
- Use only the `GMPE01` USA profile.
- Treat host addresses as run-local; canonical markers use offsets from the RAM base.
- Do not promote a marker from one capture or from an action that is not separable
  from negative controls.
- Exports may contain process paths, command lines, and raw memory bytes. They remain
  ignored by Git and should be reviewed before sharing.

Install the probe dependency with `python -m pip install -r tools/memory_probe/requirements.txt`.
Run the basic probe with `python -m tools.memory_probe.probe_runner.run_probe`.

Evaluate every exact mapped MEM1 candidate with one labeled action:

```powershell
python -m tools.memory_probe.dolphin_attach.ram_candidate_validator --action-label coin_total_change_once
```

The command writes raw evidence and a validation receipt under the ignored exports
directory. Verify them with `ram_candidate_verifier`; treat multiple mutating candidates,
no mutation, and any incomplete read as failed experiments.

See [PROBE_SPEC_v1.md](PROBE_SPEC_v1.md) for the evidence contract.
