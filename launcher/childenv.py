"""What a program started by Legacy Player inherits: a clean environment and a safe working folder.

The downloadable app is a PyInstaller "onefile" program: it unpacks itself into a temporary _MEI… folder and tells
its own child processes about that folder through environment variables (_PYI_*, _MEIPASS2). A child that is the
same program (LegacyPlayer.exe --server-run / --social-run, or the new LegacyPlayer.exe after an update) must not
reuse that state: it would run from the parent's temporary folder, which disappears when the parent exits. And no child
may keep the temporary folder as its working folder, or Windows cannot delete it when the app closes.

    from launcher.childenv import clean_env, child_cwd
    subprocess.Popen(cmd, env=clean_env(), cwd=child_cwd(data_dir))
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent      # the checkout (source); in the exe, the temporary _MEI folder


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def clean_env(base: dict | None = None) -> dict:
    """A copy of the environment without PyInstaller's onefile hand-over variables, asking a PyInstaller child to start
    afresh (PYINSTALLER_RESET_ENVIRONMENT=1). Harmless for children that are not PyInstaller programs."""
    env = dict(os.environ if base is None else base)
    for key in list(env):
        upper = key.upper()
        if upper.startswith("_PYI_") or upper == "_MEIPASS2" or upper == "_PYI_ARCHIVE_FILE":
            env.pop(key, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def exe_folder() -> Path:
    """The folder of the running program (LegacyPlayer.exe in the app; the Python interpreter otherwise)."""
    return Path(sys.executable).resolve().parent


def child_cwd(data_dir: Path | str | None = None) -> str:
    """A working folder for a child process that never is the onefile temporary folder.

    In the app: the data folder when given and present, otherwise the exe's folder. From source: the checkout, because
    `python -m launcher` / `python -m server.social` need it to find their packages."""
    if frozen():
        if data_dir is not None:
            folder = Path(data_dir)
            try:
                folder.mkdir(parents=True, exist_ok=True)
                return str(folder)
            except OSError:
                pass
        return str(exe_folder())
    return str(SOURCE_ROOT)
