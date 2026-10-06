from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    json_files = sorted(ROOT.rglob("*.json"))
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))

    identity = json.loads(
        (ROOT / "game_packs/mario_party_4/identity.json").read_text(encoding="utf-8")
    )
    profiles = identity.get("supported_profiles", [])
    if not any(p.get("game_id") == "GMPE01" and p.get("region") == "USA" for p in profiles):
        raise SystemExit("Mario Party 4 GMPE01/USA profile is missing")

    for path in ROOT.rglob("*.md"):
        if not path.read_text(encoding="utf-8").strip():
            raise SystemExit(f"empty Markdown file: {path.relative_to(ROOT)}")

    print(f"repository validation passed ({len(json_files)} JSON files)")


if __name__ == "__main__":
    main()
