import hashlib
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
from tools.memory_probe.game_fingerprint.fingerprint import detect_game
from tools.memory_probe.memory_reader.reader import read_region


EXPORT_DIR = Path("tools/memory_probe/exports")

PAGE_SIZE = 0x1000
MAX_SCAN_BYTES = 0x200000
POST_SNAPSHOT_COUNT = 4
POST_SNAPSHOT_DELAY_SECONDS = 0.125


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_export_dir() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj) -> None:
    text = json.dumps(obj, indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def safe_action_label(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "unlabeled_action"
    return raw.replace(" ", "_")


def build_page_offsets(region_size: int, max_scan_bytes: int, page_size: int) -> list[int]:
    if region_size <= 0:
        return []

    effective_scan = min(region_size, max_scan_bytes)
    last_start = max(0, effective_scan - page_size)

    offsets = list(range(0, last_start + 1, page_size))
    if not offsets:
        offsets = [0]
    elif offsets[-1] != last_start:
        offsets.append(last_start)

    return sorted(set(offsets))


def hash_bytes(data: bytes | None) -> str | None:
    if data is None:
        return None
    return hashlib.sha256(data).hexdigest()


def read_page_snapshot(proc, ram_region: dict, page_offsets: list[int], page_size: int) -> dict:
    base_address = ram_region["base_address"]
    region_size = ram_region["region_size"]

    pages = []
    for offset in page_offsets:
        remaining = max(0, region_size - offset)
        current_size = min(page_size, remaining)
        if current_size <= 0:
            continue

        data = read_region(proc, base_address + offset, current_size)
        pages.append(
            {
                "page_offset": offset,
                "absolute_address": hex(base_address + offset),
                "page_size": current_size,
                "data_sha256": hash_bytes(data),
                "preview_hex": None if data is None else data[:32].hex(),
            }
        )

    return {
        "captured_at_utc": utc_now(),
        "page_count": len(pages),
        "page_size": page_size,
        "pages": pages,
    }


def index_pages(snapshot: dict) -> dict[int, dict]:
    out = {}
    for page in snapshot.get("pages", []):
        out[page["page_offset"]] = page
    return out


def diff_page_snapshots(snapshot_a: dict, snapshot_b: dict) -> list[dict]:
    a_idx = index_pages(snapshot_a)
    b_idx = index_pages(snapshot_b)

    changed = []
    for offset in sorted(set(a_idx.keys()) | set(b_idx.keys())):
        a_page = a_idx.get(offset)
        b_page = b_idx.get(offset)

        if a_page is None or b_page is None:
            changed.append(
                {
                    "page_offset": offset,
                    "reason": "missing_in_one_snapshot",
                    "absolute_address_before": None if a_page is None else a_page["absolute_address"],
                    "absolute_address_after": None if b_page is None else b_page["absolute_address"],
                }
            )
            continue

        if a_page["data_sha256"] == b_page["data_sha256"]:
            continue

        changed.append(
            {
                "page_offset": offset,
                "absolute_address": a_page["absolute_address"],
                "page_size": a_page["page_size"],
                "before_sha256": a_page["data_sha256"],
                "after_sha256": b_page["data_sha256"],
                "before_preview_hex": a_page["preview_hex"],
                "after_preview_hex": b_page["preview_hex"],
            }
        )

    return changed


def choose_best_post_snapshot(snapshot_a: dict, post_snapshots: list[dict]) -> tuple[str, dict, list[dict]]:
    best_name = "snapshot_b"
    best_snapshot = post_snapshots[0]
    best_changed = diff_page_snapshots(snapshot_a, post_snapshots[0])

    for i, snap in enumerate(post_snapshots[1:], start=2):
        current_changed = diff_page_snapshots(snapshot_a, snap)
        if len(current_changed) > len(best_changed):
            best_name = f"snapshot_{chr(ord('a') + i)}"
            best_snapshot = snap
            best_changed = current_changed

    return best_name, best_snapshot, best_changed


def main() -> None:
    ensure_export_dir()

    action_label = safe_action_label(sys.argv[1] if len(sys.argv) > 1 else "")
    run_id = "page-sweep-" + str(uuid.uuid4())[:8]
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

    page_offsets = build_page_offsets(
        region_size=ram_region["region_size"],
        max_scan_bytes=MAX_SCAN_BYTES,
        page_size=PAGE_SIZE,
    )

    print("")
    print("=== PAGE HASH SWEEP ===")
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
    print(f"page_size: {PAGE_SIZE}")
    print(f"max_scan_bytes: {MAX_SCAN_BYTES}")
    print(f"page_count: {len(page_offsets)}")
    print(f"post_snapshot_count: {POST_SNAPSHOT_COUNT}")
    print(f"post_snapshot_delay_seconds: {POST_SNAPSHOT_DELAY_SECONDS}")
    print("")

    input("Press Enter to capture BASELINE page hashes...")

    snapshot_a = read_page_snapshot(proc, ram_region, page_offsets, PAGE_SIZE)

    print("")
    print("Perform ONE intentional in-game action now.")
    print("Examples: roll dice, coin total change, board space land, start minigame.")
    input("Press Enter immediately after the action occurs...")

    post_snapshots = []
    for _ in range(POST_SNAPSHOT_COUNT):
        time.sleep(POST_SNAPSHOT_DELAY_SECONDS)
        post_snapshots.append(read_page_snapshot(proc, ram_region, page_offsets, PAGE_SIZE))

    selected_post_snapshot, selected_snapshot_obj, changed_pages = choose_best_post_snapshot(snapshot_a, post_snapshots)

    compare_summary = []
    for i, snap in enumerate(post_snapshots, start=2):
        changed = diff_page_snapshots(snapshot_a, snap)
        compare_summary.append(
            {
                "snapshot_name": f"snapshot_{chr(ord('a') + i)}",
                "changed_page_count": len(changed),
            }
        )

    result = {
        "schema": "legacy_player.page_hash_sweep.v1",
        "captured_at_utc": utc_now(),
        "run_id": run_id,
        "action_label": action_label,
        "page_size": PAGE_SIZE,
        "max_scan_bytes": MAX_SCAN_BYTES,
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
            "score": ram_region.get("score"),
        },
        "baseline_snapshot": snapshot_a,
        "post_snapshots": {
            "snapshot_b": post_snapshots[0],
            "snapshot_c": post_snapshots[1],
            "snapshot_d": post_snapshots[2],
            "snapshot_e": post_snapshots[3],
        },
        "selected_post_snapshot": selected_post_snapshot,
        "changed_page_count": len(changed_pages),
        "changed_pages": changed_pages,
        "compare_summary": compare_summary,
    }

    write_json(out_path, result)

    print("")
    print(f"WROTE: {out_path}")
    print(f"CHANGED_PAGE_COUNT: {len(changed_pages)}")
    print(f"SELECTED_POST_SNAPSHOT: {selected_post_snapshot}")
    for item in compare_summary:
        print(f"COMPARE: {item['snapshot_name']} changed_pages={item['changed_page_count']}")

    if changed_pages:
        print("")
        print("TOP CHANGED PAGES:")
        for item in changed_pages[:10]:
            print(
                f"page_offset=0x{item['page_offset']:x} "
                f"absolute_address={item.get('absolute_address')} "
                f"page_size={item.get('page_size')}"
            )


if __name__ == "__main__":
    main()