from __future__ import annotations

import argparse
import subprocess
import sys


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.run(args, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Legacy Player release verification")
    parser.add_argument("--require-dolphin", action="store_true")
    args = parser.parse_args()
    run(sys.executable, "-m", "compileall", "-q", "adapters", "runtime", "server", "tools", "tests", "launcher", "frontend", "legacy_player_app.py")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    run(sys.executable, "tools/validate_repository.py")
    if args.require_dolphin:
        run(sys.executable, "-m", "tools.live_dolphin_check")
    print("RELEASE_CHECK_PASSED")


if __name__ == "__main__":
    main()
