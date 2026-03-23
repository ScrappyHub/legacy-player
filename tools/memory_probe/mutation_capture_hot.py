import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.memory_reader.reader import read_region


EXPORT_DIR = Path("tools/memory_probe/exports")
HOT_CONFIG_PATH = Path("game_packs/mario_party_4/HOT_RAM_WINDOWS_v1.json")

PAGE_SIZE = 4096
POST_SNAPSHOT_COUNT = 12
POST_DELAY_SECONDS = 0.05


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_export_dir() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_hot_config() -> dict:
    return json.loads(HOT_CONFIG_PATH.read_text(encoding="utf-8"))


def read_hot_pages(proc, hot_pages: list[dict]) -> dict:
    pages = []

    for item in hot_pages:
        absolute_address_text = item["absolute_address"]
        absolute_address = int(absolute_address_text, 16)

        data = read_region(proc, absolute_address, PAGE_SIZE)
        if data is None:
            page = {
                "absolute_address": absolute_address_text,
                "page_size": PAGE_SIZE,
                "data_hex": None,
            }
        else:
            page = {
                "absolute_address": absolute_address_text,
                "page_size": len(data),
                "data_hex": data.hex(),
            }

        pages.append(page)

    return {
        "captured_at_utc": utc_now(),
        "pages": pages,
    }


def diff_two_snapshots(snapshot_a: dict, snapshot_b: dict) -> tuple[list[dict], int]:
    by_addr_a = {p["absolute_address"]: p for p in snapshot_a["pages"]}
    by_addr_b = {p["absolute_address"]: p for p in snapshot_b["pages"]}

    changed_pages = []
    total_changed_bytes = 0

    for absolute_address in sorted(set(by_addr_a.keys()) | set(by_addr_b.keys())):
        a = by_addr_a.get(absolute_address)
        b = by_addr_b.get(absolute_address)

        if a is None or b is None:
            continue

        a_hex = a.get("data_hex")
        b_hex = b.get("data_hex")

        if a_hex is None or b_hex is None:
            continue

        if a_hex == b_hex:
            continue

        a_bytes = bytes.fromhex(a_hex)
        b_bytes = bytes.fromhex(b_hex)
        compare_len = min(len(a_bytes), len(b_bytes))

        changed_offsets = []
        for i in range(compare_len):
            if a_bytes[i] != b_bytes[i]:
                changed_offsets.append(i)

        changed_byte_count = len(changed_offsets)
        total_changed_bytes += changed_byte_count

        changed_pages.append({
            "absolute_address": absolute_address,
            "page_size": compare_len,
            "changed_byte_count": changed_byte_count,
            "changed_byte_offsets_preview": changed_offsets[:128],
            "before_preview_hex": a_bytes[:32].hex(),
            "after_preview_hex": b_bytes[:32].hex(),
        })

    changed_pages.sort(
        key=lambda x: (x["changed_byte_count"], x["absolute_address"]),
        reverse=True,
    )

    return changed_pages, total_changed_bytes


def write_json(path: Path, obj: dict) -> None:
    text = json.dumps(obj, indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    ensure_export_dir()

    raw_action = input("Action label: ").strip()
    action_label = raw_action if raw_action else "unlabeled"

    hot_config = load_hot_config()
    hot_pages = hot_config["hot_pages"]

    proc = find_dolphin_process()
    if not proc:
        print("ERROR: dolphin_not_found")
        raise SystemExit(1)

    run_id = "hot-" + str(uuid.uuid4())[:8]
    out_path = EXPORT_DIR / f"{run_id}_{action_label}.json"

    print("")
    print("=== HOT WINDOW CAPTURE ===")
    print(f"run_id: {run_id}")
    print(f"tracking_pages: {len(hot_pages)}")
    print(f"post_snapshot_count: {POST_SNAPSHOT_COUNT}")
    print(f"post_delay_seconds: {POST_DELAY_SECONDS}")

    input("Press Enter for BASELINE...")
    baseline = read_hot_pages(proc, hot_pages)

    print("")
    print("Perform action NOW...")
    input("Press Enter immediately after...")

    post_snapshots = []
    for i in range(POST_SNAPSHOT_COUNT):
        snap = read_hot_pages(proc, hot_pages)
        post_snapshots.append({
            "snapshot_name": f"snapshot_{chr(ord('b') + i)}",
            "snapshot": snap,
        })
        time.sleep(POST_DELAY_SECONDS)

    compare_summary = []
    best_snapshot_name = None
    best_changed_pages = []
    best_changed_page_count = -1
    best_changed_byte_count = -1

    for item in post_snapshots:
        snapshot_name = item["snapshot_name"]
        changed_pages, changed_byte_count = diff_two_snapshots(baseline, item["snapshot"])
        changed_page_count = len(changed_pages)

        compare_summary.append({
            "snapshot_name": snapshot_name,
            "changed_page_count": changed_page_count,
            "changed_byte_count": changed_byte_count,
        })

        if (
            changed_page_count > best_changed_page_count
            or (
                changed_page_count == best_changed_page_count
                and changed_byte_count > best_changed_byte_count
            )
        ):
            best_snapshot_name = snapshot_name
            best_changed_pages = changed_pages
            best_changed_page_count = changed_page_count
            best_changed_byte_count = changed_byte_count

    result = {
        "schema": "legacy_player.hot_capture.v2",
        "captured_at_utc": utc_now(),
        "run_id": run_id,
        "action_label": action_label,
        "hot_config_source": str(HOT_CONFIG_PATH),
        "tracking_page_count": len(hot_pages),
        "page_size": PAGE_SIZE,
        "post_snapshot_count": POST_SNAPSHOT_COUNT,
        "post_delay_seconds": POST_DELAY_SECONDS,
        "baseline": baseline,
        "selected_post_snapshot": best_snapshot_name,
        "changed_page_count": best_changed_page_count,
        "changed_byte_count": best_changed_byte_count,
        "changed_pages": best_changed_pages,
        "compare_summary": compare_summary,
    }

    write_json(out_path, result)

    print("")
    print(f"WROTE: {out_path}")
    print(f"BEST_CHANGED_PAGES: {best_changed_page_count}")
    print(f"BEST_CHANGED_BYTES: {best_changed_byte_count}")
    print(f"SELECTED_POST_SNAPSHOT: {best_snapshot_name}")

    top = sorted(compare_summary, key=lambda x: (x["changed_page_count"], x["changed_byte_count"]), reverse=True)[:10]
    print("")
    print("TOP SNAPSHOTS:")
    for item in top:
        print(
            f"{item['snapshot_name']} "
            f"pages_changed={item['changed_page_count']} "
            f"bytes_changed={item['changed_byte_count']}"
        )


if __name__ == "__main__":
    main()