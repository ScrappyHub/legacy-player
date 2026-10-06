from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.dolphin.configurator import (
    ManagedDolphinConfig,
    install_dsu_into_existing_user,
    restore_dsu_backup,
)


def default_user_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is unavailable; pass --user-dir")
    return Path(appdata) / "Dolphin Emulator"


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Dolphin for Legacy Player")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install-existing")
    install.add_argument("--user-dir", type=Path)
    install.add_argument("--port", type=int, default=26760)

    managed = subparsers.add_parser("create-managed")
    managed.add_argument("--user-dir", type=Path, required=True)
    managed.add_argument("--port", type=int, default=26760)
    managed.add_argument("--pads", type=int, default=4)

    restore = subparsers.add_parser("restore")
    restore.add_argument("backup_dir", type=Path)

    args = parser.parse_args()
    if args.command == "install-existing":
        backup = install_dsu_into_existing_user(args.user_dir or default_user_dir(), port=args.port)
        print(f"DSU configuration installed; backup: {backup}")
    elif args.command == "create-managed":
        manifest = ManagedDolphinConfig(args.user_dir, args.port, args.pads).create()
        print(f"Managed Dolphin profile created: {manifest['user_dir']}")
    else:
        restore_dsu_backup(args.backup_dir)
        print("Dolphin DSU configuration restored")


if __name__ == "__main__":
    main()
