import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
from tools.memory_probe.game_fingerprint.fingerprint import detect_game
from tools.memory_probe.memory_reader.reader import read_region
from tools.memory_probe.page_delta import build_changed_pages, summarize_compare_results


EXPORT_DIR = Path("tools/memory_probe/exports")

PAGE_SIZE = 4096
SCAN_SIZE = 0x00200000          # 2 MiB targeted scan
POST_SNAPSHOT_COUNT = 5
POST_SNAPSHOT_DELAY_SECONDS = 0.125
PREVIEW_HEX_BYTES = 32


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_export_dir() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def normalize_action_label(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return "unlabeled_action"
    return value.replace(" ", "_")


def write_json(path: Path, obj: Dict) -> None:
    text = json.dumps(obj, indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def choose_scan_base(ram_region: Dict) -> int:
    base = int(ram_region["base_address"])
    region_size = int(ram_region["region_size"])

    if region_size <= SCAN_SIZE:
        return base

    midpoint = base + (region_size // 2)
    scan_base = midpoint - (SCAN_SIZE // 2)

    if scan_base < base:
        scan_base = base

    max_base = base + region_size - SCAN_SIZE
    if scan_base > max_base:
        scan_base = max_base

    return scan_base


def read_page(proc, absolute_address: int, page_size: int) -> Optional[bytes]:
    return read_region(proc, absolute_address, page_size)


def read_targeted_snapshot(
    proc,
    ram_region: Dict,
    scan_base: int,
    scan_size: int,
    page_size: int = PAGE_SIZE,
) -> Dict:
    sampled_pages: List[Dict] = []

    offset = 0
    while offset < scan_size:
        current_size = min(page_size, scan_size - offset)
        absolute_address = scan_base + offset
        data = read_page(proc, absolute_address, current_size)

        sampled_pages.append({
            "page_offset": offset,
            "absolute_address": hex(absolute_address),
            "page_size": current_size,
            "data_sha256": None if data is None else __import__("hashlib").sha256(data).hexdigest(),
            "preview_hex": None if data is None else data[:PREVIEW_HEX_BYTES].hex(),
            "data_hex": None if data is None else data.hex(),
        })

        offset += page_size

    return {
        "base_address": hex(ram_region["base_address"]),
        "region_size": ram_region["region_size"],
        "protect": hex(ram_region["protect"]),
        "type": hex(ram_region["type"]),
        "score": ram_region.get("score"),
        "scan_base": hex(scan_base),
        "scan_size": scan_size,
        "page_size": page_size,
        "sampled_page_count": len(sampled_pages),
        "sampled_pages": sampled_pages,
    }


def compare_snapshots(snapshot_a: Dict, snapshot_b: Dict, snapshot_name: str) -> Dict:
    changed_pages = build_changed_pages(snapshot_a, snapshot_b)
    changed_page_count = len(changed_pages)
    changed_byte_count = sum(
        int(x.get("changed_byte_count", 0))
        for x in changed_pages
        if isinstance(x, dict)
    )

    return {
        "snapshot_name": snapshot_name,
        "changed_page_count": changed_page_count,
        "changed_byte_count": changed_byte_count,
        "changed_pages": changed_pages,
    }


def choose_best_post_snapshot(compare_results: List[Dict]) -> Dict:
    ranked = sorted(
        compare_results,
        key=lambda x: (
            int(x["changed_page_count"]),
            int(x["changed_byte_count"]),
            x["snapshot_name"],
        ),
        reverse=True,
    )
    return ranked[0]


def main() -> None:
    ensure_export_dir()

    action_label = normalize_action_label(sys.argv[1] if len(sys.argv) > 1 else "unlabeled_action")
    run_id = "mutation-" + str(uuid.uuid4())[:8]
    out_path = EXPORT_DIR / f"{run_id}_{action_label}.json"

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

    scan_base = choose_scan_base(ram_region)
    scan_size = min(SCAN_SIZE, int(ram_region["region_size"]))

    print("")
    print("=== LEGACY PLAYER MUTATION CAPTURE TARGETED ===")
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
        f"score={ram_region.get('score')}"
    )
    print("")
    print(f"scan_base: {hex(scan_base)}")
    print(f"scan_size: {scan_size}")
    print(f"page_size: {PAGE_SIZE}")
    print(f"post_snapshot_count: {POST_SNAPSHOT_COUNT}")
    print(f"post_snapshot_delay_seconds: {POST_SNAPSHOT_DELAY_SECONDS}")
    print("")
    input("Press Enter to capture BASELINE snapshot...")
    snapshot_a = read_targeted_snapshot(
        proc=proc,
        ram_region=ram_region,
        scan_base=scan_base,
        scan_size=scan_size,
        page_size=PAGE_SIZE,
    )

    print("")
    print("Perform ONE intentional in-game action now.")
    print("Examples: roll dice, land on a space, start a minigame, coin total change.")
    input("Press Enter immediately after the action occurs...")

    post_snapshots: List[Dict] = []
    snapshot_names = ["snapshot_b", "snapshot_c", "snapshot_d", "snapshot_e", "snapshot_f"]

    for i in range(POST_SNAPSHOT_COUNT):
        time.sleep(POST_SNAPSHOT_DELAY_SECONDS)
        snap = read_targeted_snapshot(
            proc=proc,
            ram_region=ram_region,
            scan_base=scan_base,
            scan_size=scan_size,
            page_size=PAGE_SIZE,
        )
        post_snapshots.append({
            "snapshot_name": snapshot_names[i],
            "snapshot": snap,
        })

    compare_results: List[Dict] = []
    for item in post_snapshots:
        compare_results.append(
            compare_snapshots(
                snapshot_a=snapshot_a,
                snapshot_b=item["snapshot"],
                snapshot_name=item["snapshot_name"],
            )
        )

    best = choose_best_post_snapshot(compare_results)
    selected_post_snapshot = best["snapshot_name"]

    selected_snapshot_obj = None
    for item in post_snapshots:
        if item["snapshot_name"] == selected_post_snapshot:
            selected_snapshot_obj = item["snapshot"]
            break

    result = {
        "schema": "legacy_player.mutation_capture_targeted.v1",
        "captured_at_utc": utc_now(),
        "run_id": run_id,
        "action_label": action_label,
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
            "score": ram_region.get("score"),
            "zero_filled_head": ram_region.get("zero_filled_head"),
        },
        "scan_base": hex(scan_base),
        "scan_size": scan_size,
        "page_size": PAGE_SIZE,
        "post_snapshot_count": POST_SNAPSHOT_COUNT,
        "post_snapshot_delay_seconds": POST_SNAPSHOT_DELAY_SECONDS,
        "snapshot_a": snapshot_a,
        "selected_post_snapshot": selected_post_snapshot,
        "selected_post_snapshot_data": selected_snapshot_obj,
        "changed_page_count": best["changed_page_count"],
        "changed_byte_count": best["changed_byte_count"],
        "changed_pages": best["changed_pages"],
        "compare_summary": summarize_compare_results(compare_results),
    }

    write_json(out_path, result)

    print("")
    print(f"WROTE: {out_path}")
    print(f"CHANGED_PAGE_COUNT: {best['changed_page_count']}")
    print(f"CHANGED_BYTE_COUNT: {best['changed_byte_count']}")
    print(f"SELECTED_POST_SNAPSHOT: {selected_post_snapshot}")

    for item in compare_results:
        print(
            f"COMPARE: {item['snapshot_name']} "
            f"pages_changed={item['changed_page_count']} "
            f"bytes_changed={item['changed_byte_count']}"
        )


if __name__ == "__main__":
    main()