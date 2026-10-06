from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.dolphin.dsu_protocol import create_dsu_server
from tools.memory_probe.dolphin_attach.attach import DolphinProcessError, find_dolphin_process
from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
from tools.memory_probe.game_fingerprint.compatibility import require_game_profile
from tools.memory_probe.game_fingerprint.fingerprint import detect_game


async def check(timeout: float) -> dict:
    try:
        process = find_dolphin_process()
    except DolphinProcessError as exc:
        raise RuntimeError(str(exc)) from exc
    if process is None:
        raise RuntimeError("Dolphin is not running")
    game = require_game_profile(detect_game(process))
    ram = find_dolphin_ram_region(process)
    if ram is None:
        raise RuntimeError("validated GameCube RAM allocation was not found")
    transport, protocol = await create_dsu_server("127.0.0.1", 26760)
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while not protocol.subscribers and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)
        if not protocol.subscribers:
            raise RuntimeError(
                "Dolphin did not register with the DSU bridge; configure Alternate Input "
                "Sources for 127.0.0.1:26760"
            )
        return {
            "ok": True,
            "pid": process.pid,
            "game_id": game["game_id"],
            "region": game["region"],
            "ram_base": hex(ram["base_address"]),
            "ram_size": ram["region_size"],
            "dsu_subscriber_count": len(protocol.subscribers),
        }
    finally:
        transport.close()
        await protocol.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a live Mario Party 4 Dolphin target")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    try:
        result = asyncio.run(check(args.timeout))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
