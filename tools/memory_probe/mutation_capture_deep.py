from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
from tools.memory_probe.dolphin_attach.ram_sampler import build_sample_offsets
from tools.memory_probe.game_fingerprint.fingerprint import detect_game
from tools.memory_probe.memory_reader.reader import read_region


EXPORT_DIR = Path("tools/memory_probe/exports")

WINDOW_SIZE = 256
MAX_SCAN_PER_REGION = 1024 * 1024
SAMPLE_WINDOW_COUNT = 8192
ALIGNMENT = 0x20

POST_SNAPSHOT_COUNT = 4
POST_SNAPSHOT_DELAY_SECONDS = 0.125

PREVIEW_HEX_BYTES = 32
MAX_CHANGED_WINDOWS_TO_PRINT = 20
MAX_CHANGED_WINDOWS_TO_STORE = 2000
MAX_CHANGED_BYTE_OFFSETS_PER_WINDOW = 128


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_export_dir() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: dict) -> None:
    text = json.dumps(obj, indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def diff_window_bytes(a_bytes: bytes, b_bytes: bytes) -> List[int]:
    compare_len = min(len(a_bytes), len(b_bytes))
    changed_offsets: List[int] = []
    for i in range(compare_len):
        if a_bytes[i] != b_bytes[i]:
            changed_offsets.append(i)
    return changed_offsets


def read_sampled_snapshot(proc, ram_region: dict, offsets: List[int]) -> dict:
    base = ram_region["base_address"]
    snapshot_windows: List[dict] = []

    for offset in offsets:
        addr = base + offset
        data = read_region(proc, addr, WINDOW_SIZE)

        snapshot_windows.append(
            {
                "window_offset": offset,
                "address": hex(addr),
                "window_size": WINDOW_SIZE,
                "data_hex": None if data is None else data.hex(),
            }
        )

    return {
        "captured_at_utc": utc_now(),
        "window_count": len(snapshot_windows),
        "windows": snapshot_windows,
    }


def index_snapshot_windows(snapshot: dict) -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    for item in snapshot.get("windows", []):
        out[int(item["window_offset"])] = item
    return out


def diff_snapshots(snapshot_a: dict, snapshot_b: dict) -> dict:
    a_map = index_snapshot_windows(snapshot_a)
    b_map = index_snapshot_windows(snapshot_b)

    all_offsets = sorted(set(a_map.keys()) | set(b_map.keys()))
    changed_windows: List[dict] = []
    changed_byte_total = 0

    for offset in all_offsets:
        a_item = a_map.get(offset)
        b_item = b_map.get(offset)

        if a_item is None or b_item is None:
            changed_windows.append(
                {
                    "window_offset": offset,
                    "reason": "missing_in_one_snapshot",
                }
            )
            continue

        a_hex = a_item.get("data_hex")
        b_hex = b_item.get("data_hex")

        if a_hex == b_hex:
            continue

        if a_hex is None or b_hex is None:
            changed_windows.append(
                {
                    "window_offset": offset,
                    "reason": "read_failed",
                }
            )
            continue

        a_bytes = bytes.fromhex(a_hex)
        b_bytes = bytes.fromhex(b_hex)
        changed_byte_offsets = diff_window_bytes(a_bytes, b_bytes)
        changed_byte_count = len(changed_byte_offsets)
        changed_byte_total += changed_byte_count

        changed_windows.append(
            {
                "window_offset": offset,
                "address": a_item.get("address"),
                "window_size": WINDOW_SIZE,
                "changed_byte_count": changed_byte_count,
                "changed_byte_offsets": changed_byte_offsets[:MAX_CHANGED_BYTE_OFFSETS_PER_WINDOW],
                "before_preview_hex": a_bytes[:PREVIEW_HEX_BYTES].hex(),
                "after_preview_hex": b_bytes[:PREVIEW_HEX_BYTES].hex(),
            }
        )

    changed_windows = changed_windows[:MAX_CHANGED_WINDOWS_TO_STORE]

    return {
        "changed_window_count": len(changed_windows),
        "changed_byte_count": changed_byte_total,
        "changed_windows": changed_windows,
    }


def choose_best_post_snapshot(
    snapshot_a: dict,
    post_snapshots: Dict[str, dict],
) -> Tuple[str, dict, dict]:
    best_name = ""
    best_snapshot: Optional[dict] = None
    best_diff: Optional[dict] = None

    for name, snap in post_snapshots.items():
        diff = diff_snapshots(snapshot_a, snap)

        if best_diff is None:
            best_name = name
            best_snapshot = snap
            best_diff = diff
            continue

        if diff["changed_window_count"] > best_diff["changed_window_count"]:
            best_name = name
            best_snapshot = snap
            best_diff = diff
            continue

        if (
            diff["changed_window_count"] == best_diff["changed_window_count"]
            and diff["changed_byte_count"] > best_diff["changed_byte_count"]
        ):
            best_name = name
            best_snapshot = snap
            best_diff = diff

    if best_snapshot is None or best_diff is None:
        raise RuntimeError("best_post_snapshot_not_found")

    return best_name, best_snapshot, best_diff


def main() -> None:
    ensure_export_dir()

    action_label = sys.argv[1].strip() if len(sys.argv) > 1 else "unlabeled_action"
    run_id = "mutation-" + str(uuid.uuid4())[:8]

    proc = find_dolphin_process()
    if not proc:
        print("ERROR: dolphin_not_found")
        raise SystemExit(1)

    game = detect_game(proc)
    if not game or game.get("game_id") == "unknown":
        print("ERROR: game_fingerprint_unknown")
        raise SystemExit(1)

    ram_region = find_dolphin_ram_region(proc)
    if not ram_region:
        print("ERROR: dolphin_ram_region_not_found")
        raise SystemExit(1)

    sample_offsets = build_sample_offsets(
        region_size=ram_region["region_size"],
        window_size=WINDOW_SIZE,
        max_scan_bytes=MAX_SCAN_PER_REGION,
        max_window_count=SAMPLE_WINDOW_COUNT,
        alignment=ALIGNMENT,
    )

    out_path = EXPORT_DIR / f"{run_id}_{action_label}.json"

    print("")
    print("=== LEGACY PLAYER MUTATION CAPTURE DEEP ===")
    print(f"run_id: {run_id}")
    print(f"action_label: {action_label}")
    print(f"pid: {proc.pid}")
    print(f"game_id: {game.get('game_id')}")
    print(f"region: {game.get('region')}")
    print(f"phase_hint: {game.get('phase_hint')}")
    print("")
    print("Selected Dolphin RAM candidate:")
    print(
        f"  base={hex(ram_region['base_address'])} "
        f"size={ram_region['region_size']} "
        f"protect={hex(ram_region['protect'])} "
        f"type={hex(ram_region['type'])} "
        f"score={ram_region.get('score', 0)}"
    )
    print("")
    print(f"window_size: {WINDOW_SIZE}")
    print(f"max_scan_per_region: {MAX_SCAN_PER_REGION}")
    print(f"sample_window_count: {len(sample_offsets)}")
    print(f"post_snapshot_count: {POST_SNAPSHOT_COUNT}")
    print(f"post_snapshot_delay_seconds: {POST_SNAPSHOT_DELAY_SECONDS}")

    input("\nPress Enter to capture BASELINE snapshot...")
    snapshot_a = read_sampled_snapshot(proc, ram_region, sample_offsets)

    print("")
    print("Perform ONE intentional in-game action now.")
    print("Examples: roll dice, land on a space, start a minigame, coin total change.")
    input("Press Enter immediately after the action occurs...")

    post_snapshots: Dict[str, dict] = {}
    for i in range(POST_SNAPSHOT_COUNT):
        snap_name = f"snapshot_{chr(ord('b') + i)}"
        post_snapshots[snap_name] = read_sampled_snapshot(proc, ram_region, sample_offsets)
        if i != POST_SNAPSHOT_COUNT - 1:
            time.sleep(POST_SNAPSHOT_DELAY_SECONDS)

    selected_post_snapshot_name, selected_post_snapshot, selected_diff = choose_best_post_snapshot(
        snapshot_a,
        post_snapshots,
    )

    compare_summary: Dict[str, dict] = {}
    for name, snap in post_snapshots.items():
        compare_summary[name] = diff_snapshots(snapshot_a, snap)

    result = {
        "schema": "legacy_player.mutation_capture_deep.v1",
        "captured_at_utc": utc_now(),
        "run_id": run_id,
        "action_label": action_label,
        "window_size": WINDOW_SIZE,
        "max_scan_per_region": MAX_SCAN_PER_REGION,
        "sample_window_count": len(sample_offsets),
        "alignment": ALIGNMENT,
        "post_snapshot_count": POST_SNAPSHOT_COUNT,
        "post_snapshot_delay_seconds": POST_SNAPSHOT_DELAY_SECONDS,
        "process": {
            "pid": proc.pid,
            "name": game.get("process_name"),
            "exe": game.get("exe"),
        },
        "game": game,
        "ram_candidate": {
            "base_address": hex(ram_region["base_address"]),
            "region_size": ram_region["region_size"],
            "protect": hex(ram_region["protect"]),
            "type": hex(ram_region["type"]),
            "score": ram_region.get("score", 0),
        },
        "sample_offsets_preview": sample_offsets[:128],
        "snapshot_a": snapshot_a,
        "selected_post_snapshot": selected_post_snapshot_name,
        "selected_snapshot": selected_post_snapshot,
        "changed_window_count": selected_diff["changed_window_count"],
        "changed_byte_count": selected_diff["changed_byte_count"],
        "changed_windows": selected_diff["changed_windows"],
        "compare_summary": {
            name: {
                "changed_window_count": diff["changed_window_count"],
                "changed_byte_count": diff["changed_byte_count"],
            }
            for name, diff in compare_summary.items()
        },
    }

    write_json(out_path, result)

    print("")
    print(f"WROTE: {out_path}")
    print(f"CHANGED_WINDOW_COUNT: {selected_diff['changed_window_count']}")
    print(f"CHANGED_BYTE_COUNT: {selected_diff['changed_byte_count']}")
    print(f"SELECTED_POST_SNAPSHOT: {selected_post_snapshot_name}")

    for name, diff in compare_summary.items():
        print(
            f"COMPARE: {name} "
            f"windows_changed={diff['changed_window_count']} "
            f"bytes_changed={diff['changed_byte_count']}"
        )

    for item in selected_diff["changed_windows"][:MAX_CHANGED_WINDOWS_TO_PRINT]:
        if "address" in item:
            print(
                f"CHANGE: offset=0x{item['window_offset']:x} "
                f"addr={item['address']} "
                f"bytes_changed={item.get('changed_byte_count', 0)}"
            )
        else:
            print(
                f"CHANGE: offset=0x{item['window_offset']:x} "
                f"reason={item.get('reason', 'unknown')}"
            )


if __name__ == "__main__":
    main()