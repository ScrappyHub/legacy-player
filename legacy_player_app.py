"""Entry point of the downloadable Legacy Player app (built with PyInstaller).

    LegacyPlayer.exe                    opens the app window
    LegacyPlayer.exe --games "D:\\Games"  also adds a games folder
    LegacyPlayer.exe --server-run ...   (internal) runs the multiplayer server
"""
from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path


def _log_file() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    folder = base / "LegacyPlayer"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "app.log"


def _fix_stdio() -> None:
    """A windowed app has no console: send prints to a log file instead of crashing."""
    if sys.stdout is None or sys.stderr is None:
        log = open(_log_file(), "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def main() -> int:
    multiprocessing.freeze_support()
    _fix_stdio()
    if "--server-run" in sys.argv:
        sys.argv.remove("--server-run")
        from server.api import json_server
        json_server.main()
        return 0
    from launcher.__main__ import main as launcher_main
    return launcher_main()


if __name__ == "__main__":
    raise SystemExit(main())
