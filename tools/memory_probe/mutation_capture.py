import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
from tools.memory_probe.dolphin_attach.ram_sampler import (
    build_sample_offsets,
    read_sampled_snapshot,
)
from tools.memory_probe.game_fingerprint.fingerprint import detect_game


EXPORT_DIR = Path("tools/memory_probe/exports")

WINDOW_SIZE = 256
WINDOW_STRIDE = 64
MAX_SCAN_PER_REGION = 1048576
PREVIEW_HEX_BYTES = 32
MAX_WINDOW_COUNT = 1024

POST_ACTION_SNAPSHOT_PLAN = (
    ("snapshot_b", 0.00),
    ("snapshot_c", 0.15),
    ("snapshot_d", 0.40),
    ("snapshot_e", 0.90),
)


def utc_now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_export_dir():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def write_json(path, obj):
    text = json.dumps(obj, indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def prompt_action_label(cli_action_label=None):
    if cli_action_label:
        raw = str(cli_action_label).strip()
    else:
        raw = input("Enter action label (example: cursor_right_once): ").strip()

    if not raw:
        return "unlabeled_action"

    safe = raw.replace(" ", "_")
    safe = "".join(ch for ch in safe if ch.isalnum() or ch in ("_", "-", "."))
    return safe or "unlabeled_action"


def score_ram_region(region):
    protect = region["protect"]
    region_size = region["region_size"]
    region_type = region["type"]

    score = 0

    if protect in (0x04, 0x40, 0x80):
        score += 50

    if region_type == 0x40000:
        score += 25
    elif region_type != 0x1000000:
        score += 15

    if region_size >= 0x2000000:
        score += 25
    elif region_size >= 0x1000000:
        score += 20
    elif region_size >= 0x400000:
        score += 10

    return score


def _windows_by_offset(snapshot):
    return {
        item["window_offset"]: item
        for item in snapshot.get("sampled_windows", [])
    }


def _diff_window_bytes(a_hex, b_hex):
    if a_hex is None or b_hex is None:
        return []

    a_bytes = bytes.fromhex(a_hex)
    b_bytes = bytes.fromhex(b_hex)

    compare_len = min(len(a_bytes), len(b_bytes))
    changed_offsets = []

    for i in range(compare_len):
        if a_bytes[i] != b_bytes[i]:
            changed_offsets.append(i)

    if len(a_bytes) != len(b_bytes):
        changed_offsets.extend(range(compare_len, max(len(a_bytes), len(b_bytes))))

    return changed_offsets


def build_snapshot_delta(snapshot_a, snapshot_post, snapshot_name):
    a_windows = _windows_by_offset(snapshot_a)
    b_windows = _windows_by_offset(snapshot_post)

    changed_windows = []

    all_offsets = sorted(set(a_windows.keys()) | set(b_windows.keys()))
    for offset in all_offsets:
        a = a_windows.get(offset)
        b = b_windows.get(offset)

        if a is None or b is None:
            changed_windows.append(
                {
                    "window_offset": offset,
                    "window_size": None,
                    "changed_byte_count": 0,
                    "changed_byte_offsets": [],
                    "before_preview_hex": None if a is None else a.get("preview_hex"),
                    "after_preview_hex": None if b is None else b.get("preview_hex"),
                    "before_sha256": None if a is None else a.get("data_sha256"),
                    "after_sha256": None if b is None else b.get("data_sha256"),
                    "reason": "missing_in_one_snapshot",
                }
            )
            continue

        if a.get("data_sha256") == b.get("data_sha256"):
            continue

        changed_byte_offsets = _diff_window_bytes(a.get("data_hex"), b.get("data_hex"))
        changed_windows.append(
            {
                "window_offset": offset,
                "window_size": a.get("window_size"),
                "changed_byte_count": len(changed_byte_offsets),
                "changed_byte_offsets": changed_byte_offsets[:128],
                "before_preview_hex": a.get("preview_hex"),
                "after_preview_hex": b.get("preview_hex"),
                "before_sha256": a.get("data_sha256"),
                "after_sha256": b.get("data_sha256"),
            }
        )

    changed_byte_count = sum(item["changed_byte_count"] for item in changed_windows)

    return {
        "snapshot_name": snapshot_name,
        "changed_window_count": len(changed_windows),
        "changed_byte_count": changed_byte_count,
        "changed_windows": changed_windows,
    }


def choose_best_delta(deltas):
    if not deltas:
        return {
            "snapshot_name": "snapshot_b",
            "changed_window_count": 0,
            "changed_byte_count": 0,
            "changed_windows": [],
        }

    ranked = sorted(
        deltas,
        key=lambda item: (
            item["changed_window_count"],
            item["changed_byte_count"],
            item["snapshot_name"],
        ),
        reverse=True,
    )
    return ranked[0]


def make_snapshot_export(snapshot):
    return {
        "base_address": snapshot["base_address"],
        "region_size": snapshot["region_size"],
        "protect": snapshot["protect"],
        "type": snapshot["type"],
        "sample_window_count": snapshot["sample_window_count"],
        "sample_window_size": snapshot["sample_window_size"],
        "sample_offsets_preview": snapshot["sample_offsets_preview"],
        "sampled_windows": [
            {
                "window_offset": item["window_offset"],
                "absolute_address": item["absolute_address"],
                "window_size": item["window_size"],
                "data_sha256": item["data_sha256"],
                "preview_hex": item["preview_hex"],
            }
            for item in snapshot.get("sampled_windows", [])
        ],
    }


def main():
    import sys

    cli_action_label = sys.argv[1] if len(sys.argv) > 1 else None

    ensure_export_dir()

    run_id = "mutation-" + str(uuid.uuid4())[:8]
    action_label = prompt_action_label(cli_action_label)
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

    sample_offsets = build_sample_offsets(
        region_size=ram_region["region_size"],
        window_size=WINDOW_SIZE,
        max_scan_bytes=MAX_SCAN_PER_REGION,
        max_window_count=MAX_WINDOW_COUNT,
        alignment=WINDOW_STRIDE,
    )

    print("")
    print("=== LEGACY PLAYER MUTATION CAPTURE ===")
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
        f"score={score_ram_region(ram_region)}"
    )
    print("")
    print(f"window_size: {WINDOW_SIZE}")
    print(f"window_stride: {WINDOW_STRIDE}")
    print(f"max_scan_per_region: {MAX_SCAN_PER_REGION}")
    print(f"sample_window_count: {len(sample_offsets)}")
    print("")

    input("Press Enter to capture BASELINE snapshot...")
    snapshot_a = read_sampled_snapshot(
        proc=proc,
        ram_region=ram_region,
        window_size=WINDOW_SIZE,
        max_scan_bytes=MAX_SCAN_PER_REGION,
        preview_hex_bytes=PREVIEW_HEX_BYTES,
        max_window_count=MAX_WINDOW_COUNT,
        alignment=WINDOW_STRIDE,
    )

    print("")
    print("Perform ONE intentional in-game action now.")
    print("Examples: move cursor, confirm, cancel, roll dice.")
    input("Press Enter to capture MUTATED snapshot...")

    post_snapshots = {}
    for snapshot_name, delay_seconds in POST_ACTION_SNAPSHOT_PLAN:
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        post_snapshots[snapshot_name] = read_sampled_snapshot(
            proc=proc,
            ram_region=ram_region,
            window_size=WINDOW_SIZE,
            max_scan_bytes=MAX_SCAN_PER_REGION,
            preview_hex_bytes=PREVIEW_HEX_BYTES,
            max_window_count=MAX_WINDOW_COUNT,
            alignment=WINDOW_STRIDE,
        )

    deltas = []
    for snapshot_name, _delay_seconds in POST_ACTION_SNAPSHOT_PLAN:
        deltas.append(
            build_snapshot_delta(
                snapshot_a=snapshot_a,
                snapshot_post=post_snapshots[snapshot_name],
                snapshot_name=snapshot_name,
            )
        )

    best_delta = choose_best_delta(deltas)

    compare_summary = [
        {
            "snapshot_name": item["snapshot_name"],
            "changed_window_count": item["changed_window_count"],
            "changed_byte_count": item["changed_byte_count"],
        }
        for item in deltas
    ]

    result = {
        "schema": "legacy_player.mutation_capture.v5",
        "captured_at_utc": utc_now(),
        "run_id": run_id,
        "action_label": action_label,
        "delta_mode": "timed_sparse_ram_sampling_v1",
        "window_size": WINDOW_SIZE,
        "window_stride": WINDOW_STRIDE,
        "max_scan_per_region": MAX_SCAN_PER_REGION,
        "sample_window_count": len(sample_offsets),
        "post_action_snapshots_captured": [name for name, _ in POST_ACTION_SNAPSHOT_PLAN],
        "selected_post_snapshot": best_delta["snapshot_name"],
        "changed_window_count": best_delta["changed_window_count"],
        "changed_byte_count": best_delta["changed_byte_count"],
        "compare_summary": compare_summary,
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
            "score": score_ram_region(ram_region),
        },
        "snapshot_a": make_snapshot_export(snapshot_a),
        "snapshot_b": make_snapshot_export(post_snapshots["snapshot_b"]),
        "snapshot_c": make_snapshot_export(post_snapshots["snapshot_c"]),
        "snapshot_d": make_snapshot_export(post_snapshots["snapshot_d"]),
        "snapshot_e": make_snapshot_export(post_snapshots["snapshot_e"]),
        "changed_regions": [
            {
                "base_address": snapshot_a["base_address"],
                "region_size": snapshot_a["region_size"],
                "protect": snapshot_a["protect"],
                "type": snapshot_a["type"],
                "sample_window_count": snapshot_a["sample_window_count"],
                "selected_post_snapshot": best_delta["snapshot_name"],
                "changed_window_count": best_delta["changed_window_count"],
                "changed_byte_count": best_delta["changed_byte_count"],
                "changed_windows": best_delta["changed_windows"],
            }
        ]
        if best_delta["changed_window_count"] > 0
        else [],
    }

    write_json(out_path, result)

    print("")
    print(f"WROTE: {out_path}")
    print(f"CHANGED_WINDOW_COUNT: {best_delta['changed_window_count']}")
    print(f"SELECTED_POST_SNAPSHOT: {best_delta['snapshot_name']}")

    for item in compare_summary:
        print(
            f"COMPARE: {item['snapshot_name']} "
            f"windows_changed={item['changed_window_count']} "
            f"bytes_changed={item['changed_byte_count']}"
        )


if __name__ == "__main__":
    main()