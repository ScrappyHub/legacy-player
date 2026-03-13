import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.game_fingerprint.fingerprint import detect_game
from tools.memory_probe.memory_reader.reader import iter_readable_regions, read_region


EXPORT_DIR = Path("tools/memory_probe/exports")
DEFAULT_REGION_LIMIT = 8
DEFAULT_READ_SIZE = 256


def utc_now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_export_dir():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def score_region(region):
    protect = region["protect"]
    region_size = region["region_size"]
    region_type = region["type"]
    base = region["base_address"]

    score = 0

    if protect in (0x04, 0x40, 0x80):
        score += 50

    if region_type != 0x1000000:
        score += 20

    if region_size >= 0x10000:
        score += 20
    elif region_size >= 0x4000:
        score += 10

    if base < 0x100000000:
        score -= 15

    return score


def select_candidate_regions(regions, limit=DEFAULT_REGION_LIMIT):
    ranked = sorted(regions, key=score_region, reverse=True)
    return ranked[:limit]


def read_region_snapshot(proc, regions, read_size=DEFAULT_READ_SIZE):
    snapshot = {}

    for region in regions:
        base = region["base_address"]
        data = read_region(proc, base, read_size)
        snapshot[hex(base)] = {
            "base_address": hex(base),
            "region_size": region["region_size"],
            "protect": hex(region["protect"]),
            "type": hex(region["type"]),
            "data_hex": None if data is None else data.hex(),
        }

    return snapshot


def diff_snapshots(snapshot_a, snapshot_b):
    changed_regions = []

    all_keys = sorted(set(snapshot_a.keys()) | set(snapshot_b.keys()))
    for key in all_keys:
        a = snapshot_a.get(key)
        b = snapshot_b.get(key)

        if a is None or b is None:
            changed_regions.append({
                "base_address": key,
                "reason": "missing_in_one_snapshot",
            })
            continue

        a_hex = a.get("data_hex")
        b_hex = b.get("data_hex")

        if a_hex == b_hex:
            continue

        changed_byte_offsets = []
        if a_hex is not None and b_hex is not None:
            a_bytes = bytes.fromhex(a_hex)
            b_bytes = bytes.fromhex(b_hex)
            compare_len = min(len(a_bytes), len(b_bytes))

            for i in range(compare_len):
                if a_bytes[i] != b_bytes[i]:
                    changed_byte_offsets.append(i)

        changed_regions.append({
            "base_address": key,
            "region_size": a.get("region_size"),
            "protect": a.get("protect"),
            "type": a.get("type"),
            "changed_byte_count": len(changed_byte_offsets),
            "changed_byte_offsets": changed_byte_offsets[:128],
            "before_hex": a_hex,
            "after_hex": b_hex,
        })

    return changed_regions


def write_json(path, obj):
    text = json.dumps(obj, indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def main():
    ensure_export_dir()

    run_id = "mutation-" + str(uuid.uuid4())[:8]
    out_path = EXPORT_DIR / f"{run_id}.json"

    proc = find_dolphin_process()
    if not proc:
        print("ERROR: dolphin_not_found")
        raise SystemExit(1)

    game = detect_game(proc)
    if not game or game.get("game_id") == "unknown":
        print("ERROR: game_fingerprint_unknown")
        raise SystemExit(1)

    regions = iter_readable_regions(proc, limit=256)
    candidate_regions = select_candidate_regions(regions, limit=DEFAULT_REGION_LIMIT)

    print("")
    print("=== LEGACY PLAYER MUTATION CAPTURE ===")
    print(f"run_id: {run_id}")
    print(f"pid: {proc.pid}")
    print(f"game_id: {game.get('game_id')}")
    print(f"region: {game.get('region')}")
    print(f"phase_hint: {game.get('phase_hint')}")
    print("")
    print("Selected candidate regions:")
    for region in candidate_regions:
        print(
            f"  {hex(region['base_address'])} "
            f"size={region['region_size']} "
            f"protect={hex(region['protect'])} "
            f"type={hex(region['type'])} "
            f"score={score_region(region)}"
        )

    print("")
    input("Press Enter to capture BASELINE snapshot...")
    snapshot_a = read_region_snapshot(proc, candidate_regions)

    print("")
    print("Perform ONE intentional in-game action now.")
    print("Examples: move cursor, advance menu, roll dice, enter minigame, confirm prompt.")
    input("Press Enter to capture MUTATED snapshot...")

    snapshot_b = read_region_snapshot(proc, candidate_regions)
    changed_regions = diff_snapshots(snapshot_a, snapshot_b)

    result = {
        "schema": "legacy_player.mutation_capture.v1",
        "captured_at_utc": utc_now(),
        "run_id": run_id,
        "process": {
            "pid": proc.pid,
            "name": game.get("process_name"),
            "exe": game.get("exe"),
        },
        "game": game,
        "candidate_regions": [
            {
                "base_address": hex(r["base_address"]),
                "region_size": r["region_size"],
                "protect": hex(r["protect"]),
                "type": hex(r["type"]),
                "score": score_region(r),
            }
            for r in candidate_regions
        ],
        "snapshot_a": snapshot_a,
        "snapshot_b": snapshot_b,
        "changed_region_count": len(changed_regions),
        "changed_regions": changed_regions,
    }

    write_json(out_path, result)

    print("")
    print(f"WROTE: {out_path}")
    print(f"CHANGED_REGION_COUNT: {len(changed_regions)}")

    for item in changed_regions[:10]:
        print(
            f"CHANGE: {item['base_address']} "
            f"bytes_changed={item.get('changed_byte_count', 0)}"
        )


if __name__ == "__main__":
    main()