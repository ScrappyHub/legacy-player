import time
import uuid
import json
from datetime import UTC, datetime
from pathlib import Path

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
from tools.memory_probe.dolphin_attach.ram_sampler import build_sample_offsets
from tools.memory_probe.memory_reader.reader import read_region


EXPORT_DIR = Path("tools/memory_probe/exports")

WINDOW_SIZE = 256
MAX_SCAN_PER_REGION = 1024 * 1024
SAMPLE_WINDOW_COUNT = 2048

STREAM_DURATION_SECONDS = 3.0
STREAM_INTERVAL_SECONDS = 0.02  # 50Hz capture


def utc_now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_export_dir():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def read_snapshot(proc, base, offsets):
    windows = []
    for off in offsets:
        data = read_region(proc, base + off, WINDOW_SIZE)
        windows.append({
            "offset": off,
            "data_hex": None if data is None else data.hex()
        })
    return windows


def diff_windows(a, b):
    changed = 0
    for i in range(len(a)):
        if a[i]["data_hex"] != b[i]["data_hex"]:
            changed += 1
    return changed


def main():
    ensure_export_dir()

    action_label = "stream"
    run_id = "stream-" + str(uuid.uuid4())[:8]

    proc = find_dolphin_process()
    if not proc:
        print("ERROR: dolphin_not_found")
        return

    ram = find_dolphin_ram_region(proc)
    if not ram:
        print("ERROR: ram_not_found")
        return

    offsets = build_sample_offsets(
        region_size=ram["region_size"],
        window_size=WINDOW_SIZE,
        max_scan_bytes=MAX_SCAN_PER_REGION,
        max_window_count=SAMPLE_WINDOW_COUNT,
    )

    print("")
    print("=== STREAM CAPTURE ===")
    print(f"run_id: {run_id}")
    print(f"windows: {len(offsets)}")
    print(f"duration: {STREAM_DURATION_SECONDS}s")
    print(f"interval: {STREAM_INTERVAL_SECONDS}s")

    input("\nPress Enter → then perform the action DURING capture...")

    frames = []
    start = time.time()

    prev = None

    while time.time() - start < STREAM_DURATION_SECONDS:
        snap = read_snapshot(proc, ram["base_address"], offsets)

        if prev:
            changed = diff_windows(prev, snap)
        else:
            changed = 0

        frames.append({
            "t": time.time() - start,
            "changed_windows": changed
        })

        prev = snap
        time.sleep(STREAM_INTERVAL_SECONDS)

    out = {
        "schema": "mutation_capture_stream.v1",
        "run_id": run_id,
        "captured_at_utc": utc_now(),
        "frames": frames,
        "window_count": len(offsets),
    }

    out_path = EXPORT_DIR / f"{run_id}_{action_label}.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print("")
    print(f"WROTE: {out_path}")

    peaks = sorted(frames, key=lambda x: x["changed_windows"], reverse=True)[:10]

    print("\nTOP CHANGE FRAMES:")
    for p in peaks:
        print(f"t={p['t']:.3f}s changed_windows={p['changed_windows']}")


if __name__ == "__main__":
    main()