import json
import os
from collections import defaultdict
from datetime import datetime, UTC

EXPORT_DIR = os.path.join("tools", "memory_probe", "exports")
OUTPUT_PATH = os.path.join("game_packs", "mario_party_4", "ACTION_BYTE_PATTERNS_v1.json")

MIN_REPEAT = 3


def utc_now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_files():
    if not os.path.isdir(EXPORT_DIR):
        return []
    return [
        os.path.join(EXPORT_DIR, f)
        for f in os.listdir(EXPORT_DIR)
        if f.startswith("validator-") and f.endswith(".json")
    ]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_entries():
    actions = defaultdict(list)

    for path in load_files():
        data = load_json(path)
        action = data.get("action_label")
        if not action:
            continue

        for page in data.get("changed_pages", []):
            entry = {
                "page_offset": page.get("page_offset"),
                "absolute_address": page.get("absolute_address"),
                "changed_byte_count": page.get("changed_byte_count", 0),
                "offsets": page.get("changed_byte_offsets_preview") or []
            }
            actions[action].append(entry)

    return actions


def bucket(n):
    if n < 64: return "0-63"
    if n < 128: return "64-127"
    if n < 192: return "128-191"
    if n < 256: return "192-255"
    return "256+"


def build_patterns(entries):
    groups = defaultdict(list)

    for e in entries:
        key = (e["page_offset"], bucket(e["changed_byte_count"]))
        groups[key].append(e)

    patterns = []

    for (page, b), group in groups.items():
        if len(group) < MIN_REPEAT:
            continue

        rep = group[0]

        patterns.append({
            "page_offset": page,
            "absolute_address": rep["absolute_address"],
            "repeat_count": len(group),
            "signature_type": "coarse",
            "signature_length": 0,
            "changed_byte_offsets_preview": [],
            "first_changed_offset": None,
            "changed_byte_count": rep["changed_byte_count"],
            "changed_byte_bucket": b,
            "byte_signature": "coarse_signature_v1"
        })

    return patterns


def main():
    actions = extract_entries()

    out = {
        "schema": "legacy_player.action_byte_patterns.v9",
        "generated_at_utc": utc_now(),
        "minimum_repeat": MIN_REPEAT,
        "notes": "coarse clustering only (fine offsets currently missing)",
        "actions": {}
    }

    for name, entries in actions.items():
        patterns = build_patterns(entries)

        out["actions"][name] = {
            "input_entry_count": len(entries),
            "pattern_count": len(patterns),
            "patterns": patterns
        }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print("CLASSIFIER_V9_OK")


if __name__ == "__main__":
    main()
