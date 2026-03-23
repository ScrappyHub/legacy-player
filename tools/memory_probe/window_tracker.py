import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
from tools.memory_probe.game_fingerprint.fingerprint import detect_game
from tools.memory_probe.memory_reader.reader import read_region


EXPORT_DIR = Path("tools/memory_probe/exports")

WINDOW_SIZE = 256
WINDOW_STRIDE = 64
PREVIEW_HEX_BYTES = 32
MAX_CHANGED_BYTE_OFFSETS = 128


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


def build_window_offsets(page_size: int, window_size: int, window_stride: int) -> list[int]:
    if page_size <= 0:
        return []
    if page_size <= window_size:
        return [0]

    last_start = page_size - window_size
    offsets = list(range(0, last_start + 1, window_stride))
    if offsets[-1] != last_start:
        offsets.append(last_start)
    return sorted(set(offsets))


def read_page_windows(proc, base_address: int, page_offset: int, page_size: int) -> list[dict]:
    out = []
    window_offsets = build_window_offsets(page_size, WINDOW_SIZE, WINDOW_STRIDE)

    for window_offset in window_offsets:
        absolute_offset = page_offset + window_offset
        absolute_address = base_address + absolute_offset
        current_size = min(WINDOW_SIZE, page_size - window_offset)
        if current_size <= 0:
            continue

        data = read_region(proc, absolute_address, current_size)
        out.append(
            {
                "page_offset": page_offset,
                "window_offset_within_page": window_offset,
                "absolute_window_offset": absolute_offset,
                "absolute_address": hex(absolute_address),
                "window_size": current_size,
                "data_hex": None if data is None else data.hex(),
                "data_sha256": None if data is None else hashlib.sha256(data).hexdigest(),
                "preview_hex": None if data is None else data[:PREVIEW_HEX_BYTES].hex(),
            }
        )

    return out


def diff_window_bytes(before_hex: str | None, after_hex: str | None) -> list[int]:
    if before_hex is None or after_hex is None:
        return []

    before_bytes = bytes.fromhex(before_hex)
    after_bytes = bytes.fromhex(after_hex)
    compare_len = min(len(before_bytes), len(after_bytes))

    changed = []
    for i in range(compare_len):
        if before_bytes[i] != after_bytes[i]:
            changed.append(i)

    return changed


def main() -> None:
    ensure_export_dir()

    if len(sys.argv) < 2:
        print("ERROR: missing_page_sweep_json_path")
        raise SystemExit(1)

    page_sweep_path = Path(sys.argv[1])
    action_label = safe_action_label(sys.argv[2] if len(sys.argv) > 2 else "")

    if not page_sweep_path.exists():
        print(f"ERROR: page_sweep_not_found: {page_sweep_path}")
        raise SystemExit(1)

    page_sweep = json.loads(page_sweep_path.read_text(encoding="utf-8"))
    changed_pages = page_sweep.get("changed_pages", [])

    if not changed_pages:
        print("ERROR: no_changed_pages_in_sweep")
        raise SystemExit(1)

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

    run_id = "window-track-" + str(uuid.uuid4())[:8]
    out_path = EXPORT_DIR / f"{run_id}_{action_label}.json"

    changed_page_offsets = [int(item["page_offset"]) for item in changed_pages]

    print("")
    print("=== WINDOW TRACKER ===")
    print(f"run_id: {run_id}")
    print(f"action_label: {action_label}")
    print(f"page_sweep_path: {page_sweep_path}")
    print(f"changed_page_count: {len(changed_page_offsets)}")
    print("")

    input("Press Enter to capture BEFORE windows for changed pages...")

    before_windows = {}
    for page_offset in changed_page_offsets:
        before_windows[str(page_offset)] = read_page_windows(
            proc=proc,
            base_address=ram_region["base_address"],
            page_offset=page_offset,
            page_size=0x1000,
        )

    print("")
    print("Perform the SAME intentional action again now.")
    input("Press Enter immediately after the action occurs...")

    after_windows = {}
    for page_offset in changed_page_offsets:
        after_windows[str(page_offset)] = read_page_windows(
            proc=proc,
            base_address=ram_region["base_address"],
            page_offset=page_offset,
            page_size=0x1000,
        )

    changed_windows = []
    total_changed_bytes = 0

    for page_offset in changed_page_offsets:
        key = str(page_offset)
        before_list = before_windows.get(key, [])
        after_list = after_windows.get(key, [])

        count = min(len(before_list), len(after_list))
        for i in range(count):
            before_item = before_list[i]
            after_item = after_list[i]

            if before_item["data_sha256"] == after_item["data_sha256"]:
                continue

            changed_offsets = diff_window_bytes(before_item["data_hex"], after_item["data_hex"])
            total_changed_bytes += len(changed_offsets)

            changed_windows.append(
                {
                    "page_offset": page_offset,
                    "window_offset_within_page": before_item["window_offset_within_page"],
                    "absolute_window_offset": before_item["absolute_window_offset"],
                    "absolute_address": before_item["absolute_address"],
                    "window_size": before_item["window_size"],
                    "changed_byte_count": len(changed_offsets),
                    "changed_byte_offsets": changed_offsets[:MAX_CHANGED_BYTE_OFFSETS],
                    "before_sha256": before_item["data_sha256"],
                    "after_sha256": after_item["data_sha256"],
                    "before_preview_hex": before_item["preview_hex"],
                    "after_preview_hex": after_item["preview_hex"],
                }
            )

    result = {
        "schema": "legacy_player.window_tracker.v1",
        "captured_at_utc": utc_now(),
        "run_id": run_id,
        "action_label": action_label,
        "page_sweep_path": str(page_sweep_path),
        "window_size": WINDOW_SIZE,
        "window_stride": WINDOW_STRIDE,
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
        "changed_page_offsets": changed_page_offsets,
        "changed_window_count": len(changed_windows),
        "changed_byte_count": total_changed_bytes,
        "changed_windows": changed_windows,
    }

    write_json(out_path, result)

    print("")
    print(f"WROTE: {out_path}")
    print(f"CHANGED_WINDOW_COUNT: {len(changed_windows)}")
    print(f"CHANGED_BYTE_COUNT: {total_changed_bytes}")

    if changed_windows:
        print("")
        print("TOP CHANGED WINDOWS:")
        for item in changed_windows[:10]:
            print(
                f"page_offset=0x{item['page_offset']:x} "
                f"absolute_window_offset=0x{item['absolute_window_offset']:x} "
                f"changed_byte_count={item['changed_byte_count']}"
            )


if __name__ == "__main__":
    main()