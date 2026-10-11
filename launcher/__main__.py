from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .app import LauncherApp
from .catalog import CatalogError
from .shell import make_opener
from .web import CLEANUP_LIMIT_SECONDS, acquire_instance_lock, arm_exit_watchdog, serve, wake_existing

DEFAULT_PORT = 8780
LOCK_WAIT_SECONDS = 20.0        # a closing Legacy Player (for example one restarting into an update) may take this long


def claim_data_folder(data_dir: Path, show: bool, wait: float = LOCK_WAIT_SECONDS):
    """One Legacy Player per data folder. Returns (lock, exit_code): the held lock and None, or None and the exit code
    after waking the one that is already running (0) or failing to reach it (1). A Legacy Player that is just closing is
    waited for, so this launch then starts normally."""
    lock = acquire_instance_lock(data_dir)
    if lock is not None:
        try:
            (Path(data_dir) / "instance.json").unlink()          # nobody else runs here: a leftover from a crash
        except OSError:
            pass
        return lock, None
    end = time.time() + wait
    while True:
        if wake_existing(data_dir, show=show):
            print("Legacy Player is already running" + ("; showing its window." if show else "."), flush=True)
            return None, 0
        lock = acquire_instance_lock(data_dir)
        if lock is not None:
            return lock, None
        if time.time() >= end:
            print("Legacy Player is already running for this data folder but does not answer. Close it (or end "
                  "LegacyPlayer in Task Manager) and try again.", file=sys.stderr, flush=True)
            return None, 1
        time.sleep(0.5)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m launcher", description="Legacy Player library and launcher")
    parser.add_argument("--games", action="append", default=[], metavar="FOLDER",
                        help='a folder that holds your games, e.g. --games "D:\\Games" (repeatable; optional)')
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".legacy-player")
    parser.add_argument("--port", type=int, default=None,
                        help=f"the port of the local page (default {DEFAULT_PORT}, or a free one when that is taken)")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--window", action="store_true", default=getattr(sys, "frozen", False),
                        help="open in an app-style window and quit when it is closed (default in the downloadable app)")
    args = parser.parse_args()
    lock, code = claim_data_folder(args.data_dir, show=not args.no_browser)
    if lock is None:
        if args.games and code == 0:
            print("Add the games folder in the open app (Library folders); it was not added from here.", flush=True)
        return code if code is not None else 1
    app = LauncherApp(args.data_dir)
    if args.games:
        missing = [g for g in args.games if not Path(g).is_dir()]
        if missing:
            print(f"Cannot find this games folder: {missing[0]}\n"
                  "Use the real path to your games folder (the docs show a placeholder). "
                  "You can also start without --games and add the folder in the app.", file=sys.stderr)
            return 2
        merged = list(dict.fromkeys(app.catalog.data["roots"] + [str(Path(g)) for g in args.games]))
        try:
            app.catalog.set_roots(merged)
        except CatalogError as exc:
            print(f"Could not use that folder: {exc}", file=sys.stderr)
            return 2
        app.rescan()
    serve(app, args.port or DEFAULT_PORT, open_browser=not args.no_browser,
          opener=make_opener(args.data_dir) if args.window and not args.no_browser else None,
          exit_when_closed=args.window, port_fallback=args.port is None)
    if args.window or app.quit_requested:
        # the app was closed on purpose: whatever thread is still busy, the process must end (it holds the port, the
        # data folder's lock, and for the exe the file an update has to replace)
        arm_exit_watchdog(CLEANUP_LIMIT_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
