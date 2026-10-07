from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import LauncherApp
from .catalog import CatalogError
from .shell import make_opener
from .web import serve, wake_existing


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m launcher", description="Legacy Player library and launcher")
    parser.add_argument("--games", action="append", default=[], metavar="FOLDER",
                        help='a folder that holds your games, e.g. --games "P:\\Vimm" (repeatable; optional)')
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".legacy-player")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--window", action="store_true", default=getattr(sys, "frozen", False),
                        help="open in an app-style window and quit when it is closed (default in the downloadable app)")
    args = parser.parse_args()
    if args.window and wake_existing(args.data_dir):
        print("Legacy Player is already running; showing its window.")
        return 0
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
    serve(app, args.port, open_browser=not args.no_browser,
          opener=make_opener(args.data_dir) if args.window and not args.no_browser else None,
          exit_when_closed=args.window, port_fallback=args.window)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
