from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List


EXPORT_DIR = Path("tools/memory_probe/exports")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_mutation_files(limit: int = 8) -> List[Path]:
    files = sorted(
        EXPORT_DIR.glob("mutation-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[:limit]


def main() -> None:
    paths: List[Path]

    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        paths = latest_mutation_files()

    if not paths:
        print("NO_MUTATION_FILES_FOUND")
        raise SystemExit(1)

    print("")
    print("=== LEGACY PLAYER MUTATION RUN ANALYSIS ===")
    print("")

    for path in paths:
        obj = load_json(path)
        print(path.name)
        print(f"  schema: {obj.get('schema')}")
        print(f"  run_id: {obj.get('run_id')}")
        print(f"  action_label: {obj.get('action_label')}")
        print(f"  changed_window_count: {obj.get('changed_window_count', 0)}")
        print(f"  changed_byte_count: {obj.get('changed_byte_count', 0)}")
        print(f"  selected_post_snapshot: {obj.get('selected_post_snapshot')}")
        ram_candidate = obj.get("ram_candidate", {})
        print(f"  ram_base: {ram_candidate.get('base_address')}")
        print(f"  sample_window_count: {obj.get('sample_window_count')}")
        print("")

        changed_windows = obj.get("changed_windows", [])
        for item in changed_windows[:10]:
            print(
                f"    offset=0x{int(item.get('window_offset', 0)):x} "
                f"addr={item.get('address')} "
                f"bytes_changed={item.get('changed_byte_count', 0)}"
            )

        if changed_windows:
            print("")

    print("ANALYSIS_DONE")


if __name__ == "__main__":
    main()