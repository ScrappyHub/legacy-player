import json
import sys
from pathlib import Path


def load_last_region_hashes(path):
    result = {}

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            event = json.loads(line)
            if event.get("kind") != "memory":
                continue
            if event.get("event") != "region_probe_sample":
                continue

            payload = event.get("payload", {})
            base = payload.get("base_address")
            sha = payload.get("data_sha256")

            if base and sha:
                result[base] = {
                    "sha256": sha,
                    "region_size": payload.get("region_size"),
                    "protect": payload.get("protect"),
                    "type": payload.get("type"),
                }

    return result


def main():
    if len(sys.argv) != 3:
        print("usage: python -m tools.memory_probe.compare_runs <run_a.ndjson> <run_b.ndjson>")
        raise SystemExit(1)

    run_a = Path(sys.argv[1])
    run_b = Path(sys.argv[2])

    if not run_a.is_file():
        print(f"ERROR: missing file: {run_a}")
        raise SystemExit(1)

    if not run_b.is_file():
        print(f"ERROR: missing file: {run_b}")
        raise SystemExit(1)

    a = load_last_region_hashes(run_a)
    b = load_last_region_hashes(run_b)

    all_bases = sorted(set(a.keys()) | set(b.keys()))
    changed = []

    for base in all_bases:
        a_entry = a.get(base)
        b_entry = b.get(base)

        if a_entry is None or b_entry is None:
            changed.append({
                "base_address": base,
                "reason": "missing_in_one_run",
            })
            continue

        if a_entry["sha256"] != b_entry["sha256"]:
            changed.append({
                "base_address": base,
                "reason": "sha256_changed",
                "sha_a": a_entry["sha256"],
                "sha_b": b_entry["sha256"],
                "region_size": a_entry.get("region_size"),
                "protect": a_entry.get("protect"),
                "type": a_entry.get("type"),
            })

    print(json.dumps({
        "run_a": str(run_a),
        "run_b": str(run_b),
        "changed_region_count": len(changed),
        "changed_regions": changed,
    }, indent=2))


if __name__ == "__main__":
    main()