from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DSU_CONFIG = """[Server]
Enabled = True
Entries = LegacyPlayer:127.0.0.1:{port};
"""

# Must agree with dsu_protocol.pad_data_packet: GameCube Z rides on the R1 analog field, L and R on the L2/R2 trigger
# fields (Dolphin's DualShockUDPClient reads "L1"/"R1" from the shoulder analog bytes and "L2"/"R2" from the triggers).
PAD_TEMPLATE = """[GCPad{number}]
Device = DSUClient/{index}/LegacyPlayer
Buttons/A = Cross
Buttons/B = Circle
Buttons/X = Square
Buttons/Y = Triangle
Buttons/Z = R1
Buttons/Start = Options
Main Stick/Up = `Left Y+`
Main Stick/Down = `Left Y-`
Main Stick/Left = `Left X-`
Main Stick/Right = `Left X+`
C-Stick/Up = `Right Y+`
C-Stick/Down = `Right Y-`
C-Stick/Left = `Right X-`
C-Stick/Right = `Right X+`
Triggers/L = L2
Triggers/R = R2
Triggers/L-Analog = L2
Triggers/R-Analog = R2
D-Pad/Up = `Pad N`
D-Pad/Down = `Pad S`
D-Pad/Left = `Pad W`
D-Pad/Right = `Pad E`
Options/Always Connected = True
"""


class DolphinConfigError(RuntimeError):
    pass


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class ManagedDolphinConfig:
    user_dir: Path
    dsu_port: int = 26760
    pad_count: int = 4

    def create(self) -> dict:
        if self.pad_count not in range(1, 5):
            raise DolphinConfigError("pad_count must be between 1 and 4")
        if self.dsu_port not in range(1, 65536):
            raise DolphinConfigError("DSU port must be between 1 and 65535")
        root = self.user_dir.resolve()
        config = root / "Config"
        config.mkdir(parents=True, exist_ok=True)
        files = {
            "DSUClient.ini": DSU_CONFIG.format(port=self.dsu_port),
            "Dolphin.ini": "[Core]\n"
            + "\n".join(f"SIDevice{index} = 6" for index in range(self.pad_count))
            + "\nSkipIPL = True\n",
            "GCPadNew.ini": "\n".join(
                PAD_TEMPLATE.format(number=index + 1, index=index)
                for index in range(self.pad_count)
            ),
        }
        for name, text in files.items():
            (config / name).write_text(text, encoding="utf-8", newline="\n")
        manifest = {
            "schema": "legacy_player.dolphin_managed_config.v1",
            "created_at_utc": utc_stamp(),
            "user_dir": str(root),
            "dsu_port": self.dsu_port,
            "pad_count": self.pad_count,
            "files": {
                name: file_sha256(config / name) for name in sorted(files)
            },
        }
        (root / "legacy-player.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return manifest


def install_dsu_into_existing_user(user_dir: Path, *, port: int = 26760) -> Path:
    root = user_dir.resolve()
    config = root / "Config"
    if not config.is_dir():
        raise DolphinConfigError(f"Dolphin Config directory not found: {config}")
    target = config / "DSUClient.ini"
    backup_dir = config / "LegacyPlayerBackups" / utc_stamp()
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": "legacy_player.dolphin_config_backup.v1",
        "target": str(target),
        "original_existed": target.exists(),
        "original_sha256": file_sha256(target),
    }
    if target.exists():
        shutil.copy2(target, backup_dir / target.name)
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    temporary = target.with_suffix(".ini.legacy-player.tmp")
    temporary.write_text(DSU_CONFIG.format(port=port), encoding="utf-8", newline="\n")
    os.replace(temporary, target)
    return backup_dir


def restore_dsu_backup(backup_dir: Path) -> None:
    manifest_path = backup_dir.resolve() / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = Path(manifest["target"]).resolve()
    backup = manifest_path.parent / target.name
    if manifest["original_existed"]:
        if file_sha256(backup) != manifest["original_sha256"]:
            raise DolphinConfigError("backup hash does not match manifest")
        shutil.copy2(backup, target)
    else:
        target.unlink(missing_ok=True)


def launch_managed_dolphin(
    dolphin_exe: Path, game_path: Path, user_dir: Path
) -> subprocess.Popen:
    executable = dolphin_exe.resolve()
    game = game_path.resolve()
    if not executable.is_file():
        raise DolphinConfigError(f"Dolphin executable not found: {executable}")
    if not game.is_file():
        raise DolphinConfigError(f"game file not found: {game}")
    ManagedDolphinConfig(user_dir).create()
    return subprocess.Popen(
        [str(executable), "--user", str(user_dir.resolve()), "--exec", str(game)],
        cwd=executable.parent,
        shell=False,
    )
