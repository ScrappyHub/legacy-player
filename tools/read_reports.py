"""Summarise the problem reports collected by server/report_receiver.py, most common first.

    python tools/read_reports.py reports            # the problems, grouped
    python tools/read_reports.py reports <fingerprint>   # the newest report for one problem, in full
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path


def main() -> int:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "reports")
    index = folder / "index.jsonl"
    if not index.exists():
        print("No reports yet.")
        return 0
    rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(sys.argv) > 2:
        wanted = sys.argv[2]
        files = sorted(folder.glob(f"*/{wanted}/*.json"), key=lambda p: p.stat().st_mtime)
        if not files:
            print("No report with that fingerprint.")
            return 1
        print(files[-1].read_text(encoding="utf-8"))
        return 0
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r["fingerprint"]].append(r)
    print(f"{len(rows)} reports, {len(groups)} different problems\n")
    for fp, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        versions = sorted({str(i.get("version")) for i in items})
        print(f"{len(items):>4}x  {fp}  {items[-1].get('kind')}  {items[-1].get('error')}: {items[-1].get('message')}")
        print(f"        versions {', '.join(versions)}; last seen {items[-1]['day']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
