# Dolphin Automatic Configuration v1

Legacy Player supports two automatic setup modes.

## Managed mode (default)

Managed mode creates an isolated Dolphin user directory and launches Dolphin with its
documented `--user` option. It writes only inside that managed directory and leaves the
user's normal Dolphin settings untouched.

Generated configuration includes:

- local DSU source at `127.0.0.1:26760`
- four standard GameCube controller ports
- four DSU-backed controller mappings
- a manifest containing hashes of every generated file

The launcher passes arguments as a list with `shell=False`, validates that Dolphin and
the game file exist, and does not interpolate either path into a shell command.

## Existing-profile mode

For an already-running normal Dolphin profile, Legacy Player can install the DSU source
setting automatically. Before writing, it creates a timestamped backup under:

```text
Config/LegacyPlayerBackups/<UTC timestamp>/
```

The backup manifest records whether the file originally existed and its SHA-256 hash.
Restore verifies the hash before copying the original file back. Existing GameCube pad
mappings are not modified in this mode.

Commands:

```powershell
python tools/configure_dolphin.py install-existing
python tools/configure_dolphin.py create-managed --user-dir <managed-directory>
python tools/configure_dolphin.py restore <backup-directory>
```

## Runtime behavior

Dolphin may not reload an externally changed DSU configuration while emulation is
active. Product orchestration should therefore use managed mode and launch Dolphin
after generating configuration. Existing-profile mode may require a controlled Dolphin
restart; Legacy Player must not terminate a user-owned Dolphin process without explicit
confirmation.
