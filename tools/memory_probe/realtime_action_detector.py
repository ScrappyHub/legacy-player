import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
from tools.memory_probe.game_fingerprint.fingerprint import detect_game
from tools.memory_probe.game_fingerprint.compatibility import require_game_profile
from tools.memory_probe.memory_reader.reader import read_region


EXPORT_DIR = Path("tools/memory_probe/exports")
PATTERN_PATH = Path("game_packs/mario_party_4/ACTION_BYTE_PATTERNS_v1.json")

PAGE_SIZE = 4096
LOOP_SECONDS = 0.25
PREVIEW_HEX_BYTES = 32
MAX_CHANGED_BYTE_OFFSETS_PREVIEW = 32


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_export_dir() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_patterns() -> dict:
    if not PATTERN_PATH.exists():
        raise FileNotFoundError(f"PATTERN_FILE_MISSING: {PATTERN_PATH}")
    return json.loads(PATTERN_PATH.read_text(encoding="utf-8"))


def read_page(proc, base_address: int, page_offset: int) -> dict:
    absolute_address = base_address + page_offset
    data = read_region(proc, absolute_address, PAGE_SIZE)
    return {
        "page_offset": page_offset,
        "absolute_address": hex(absolute_address),
        "data_hex": None if data is None else data.hex(),
    }


def diff_page(before_hex: str | None, after_hex: str | None) -> tuple[int, int | None, list[int], str | None, str | None]:
    if not before_hex or not after_hex:
        return 0, None, [], None, None

    before_bytes = bytes.fromhex(before_hex)
    after_bytes = bytes.fromhex(after_hex)

    changed_offsets: list[int] = []
    for i in range(min(len(before_bytes), len(after_bytes))):
        if before_bytes[i] != after_bytes[i]:
            changed_offsets.append(i)

    if not changed_offsets:
        return 0, None, [], None, None

    first_changed_offset = changed_offsets[0]
    preview_offsets = changed_offsets[:MAX_CHANGED_BYTE_OFFSETS_PREVIEW]

    half = PREVIEW_HEX_BYTES // 2
    start = max(0, first_changed_offset - half)
    max_start = max(0, len(before_bytes) - PREVIEW_HEX_BYTES)
    start = min(start, max_start)
    end = min(len(before_bytes), start + PREVIEW_HEX_BYTES)

    before_preview_hex = before_bytes[start:end].hex()
    after_preview_hex = after_bytes[start:end].hex()

    rebased_offsets = []
    for off in preview_offsets:
        rebased = off - start
        if 0 <= rebased < PREVIEW_HEX_BYTES:
            rebased_offsets.append(rebased)

    return len(changed_offsets), first_changed_offset, rebased_offsets, before_preview_hex, after_preview_hex


def collect_pattern_pages(pattern_doc: dict) -> list[int]:
    offsets = set()
    actions = pattern_doc.get("actions", {})
    if not isinstance(actions, dict):
        return []

    for action_meta in actions.values():
        patterns = action_meta.get("patterns", [])
        if not isinstance(patterns, list):
            continue
        for pat in patterns:
            try:
                offsets.add(int(pat["page_offset"]))
            except Exception:
                continue

    return sorted(offsets)


def snapshot(proc, ram_region: dict, page_offsets: list[int]) -> dict[int, dict]:
    base_address = ram_region["base_address"]
    out: dict[int, dict] = {}
    for offset in page_offsets:
        out[offset] = read_page(proc, base_address, offset)
    return out


def score_action(changed_pages: list[dict], action_patterns: list[dict]) -> dict:
    if not action_patterns:
        return {
            "action": None,
            "score": 0.0,
            "matched_pattern_count": 0,
            "matched_pages": [],
        }

    changed_by_page = {int(p["page_offset"]): p for p in changed_pages}
    matched = []

    for pat in action_patterns:
        try:
            page_offset = int(pat["page_offset"])
        except Exception:
            continue

        if page_offset not in changed_by_page:
            continue

        page = changed_by_page[page_offset]
        pat_offsets = set(int(x) for x in pat.get("changed_byte_offsets_preview", []) if isinstance(x, int))
        live_offsets = set(int(x) for x in page.get("changed_byte_offsets_preview", []) if isinstance(x, int))

        overlap = len(pat_offsets & live_offsets) if pat_offsets and live_offsets else 0
        offset_score = 0.0
        if pat_offsets:
            offset_score = overlap / len(pat_offsets)

        first_changed_score = 0.0
        if pat.get("first_changed_offset") is not None and page.get("first_changed_offset") is not None:
            try:
                if int(pat["first_changed_offset"]) == int(page["first_changed_offset"]):
                    first_changed_score = 1.0
            except Exception:
                first_changed_score = 0.0

        changed_byte_score = 0.0
        try:
            pat_count = int(pat.get("changed_byte_count", 0))
            live_count = int(page.get("changed_byte_count", 0))
            if pat_count > 0 and live_count > 0:
                ratio = min(pat_count, live_count) / max(pat_count, live_count)
                changed_byte_score = ratio
        except Exception:
            changed_byte_score = 0.0

        total = (offset_score * 0.6) + (first_changed_score * 0.2) + (changed_byte_score * 0.2)

        if total > 0:
            matched.append({
                "page_offset": page_offset,
                "score": round(total, 6),
                "offset_overlap": overlap,
                "pattern_offset_count": len(pat_offsets),
                "live_offset_count": len(live_offsets),
            })

    if not matched:
        return {
            "action": None,
            "score": 0.0,
            "matched_pattern_count": 0,
            "matched_pages": [],
        }

    score = sum(x["score"] for x in matched) / len(matched)
    return {
        "action": None,
        "score": round(score, 6),
        "matched_pattern_count": len(matched),
        "matched_pages": matched,
    }


def main() -> None:
    ensure_export_dir()

    pattern_doc = load_patterns()
    tracked_pages = collect_pattern_pages(pattern_doc)
    if not tracked_pages:
        print("ERROR: NO_PATTERN_PAGES")
        raise SystemExit(1)

    proc = find_dolphin_process()
    if not proc:
        print("ERROR: dolphin_not_found")
        raise SystemExit(1)

    game = detect_game(proc)
    try:
        require_game_profile(game)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)

    ram_region = find_dolphin_ram_region(proc)
    if not ram_region:
        print("ERROR: dolphin_ram_region_not_found")
        raise SystemExit(1)

    run_id = "realtime-" + str(uuid.uuid4())[:8]
    out_path = EXPORT_DIR / f"{run_id}_realtime_action_detector.json"

    print("")
    print("=== REALTIME ACTION DETECTOR ===")
    print(f"run_id: {run_id}")
    print(f"pid: {proc.pid}")
    print(f"game_id: {game.get('game_id')}")
    print(f"region: {game.get('region')}")
    print(f"phase_hint: {game.get('phase_hint')}")
    print(f"tracked_pages: {len(tracked_pages)}")
    print("")
    input("Press Enter for baseline snapshot...")

    baseline = snapshot(proc, ram_region, tracked_pages)

    print("")
    print("Detector running. Perform one action now.")
    print("Press Ctrl+C to stop after a few loops.")
    print("")

    actions = pattern_doc.get("actions", {})
    frames = []

    try:
        while True:
            time.sleep(LOOP_SECONDS)
            current = snapshot(proc, ram_region, tracked_pages)

            changed_pages = []
            for page_offset in tracked_pages:
                before = baseline.get(page_offset)
                after = current.get(page_offset)
                if not before or not after:
                    continue

                changed_byte_count, first_changed_offset, changed_offsets_preview, before_preview_hex, after_preview_hex = diff_page(
                    before.get("data_hex"),
                    after.get("data_hex"),
                )

                if changed_byte_count <= 0:
                    continue

                changed_pages.append({
                    "page_offset": page_offset,
                    "absolute_address": after["absolute_address"],
                    "changed_byte_count": changed_byte_count,
                    "first_changed_offset": first_changed_offset,
                    "changed_byte_offsets_preview": changed_offsets_preview,
                    "before_preview_hex": before_preview_hex,
                    "after_preview_hex": after_preview_hex,
                })

            if not changed_pages:
                continue

            scored_actions = []
            for action_name, action_meta in actions.items():
                patterns = action_meta.get("patterns", [])
                result = score_action(changed_pages, patterns)
                result["action"] = action_name
                scored_actions.append(result)

            scored_actions.sort(key=lambda x: (x["score"], x["matched_pattern_count"]), reverse=True)
            best = scored_actions[0] if scored_actions else {
                "action": None,
                "score": 0.0,
                "matched_pattern_count": 0,
                "matched_pages": [],
            }

            frame = {
                "captured_at_utc": utc_now(),
                "changed_page_count": len(changed_pages),
                "changed_pages": changed_pages,
                "best_action": best,
                "all_scores": scored_actions,
            }
            frames.append(frame)

            print(
                f"{frame['captured_at_utc']} "
                f"pages={frame['changed_page_count']} "
                f"best={best['action']} "
                f"score={best['score']}"
            )

    except KeyboardInterrupt:
        pass

    result = {
        "schema": "legacy_player.realtime_action_detector.v1",
        "captured_at_utc": utc_now(),
        "run_id": run_id,
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
        "tracked_pages": tracked_pages,
        "frame_count": len(frames),
        "frames": frames,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("")
    print(f"WROTE: {out_path}")


if __name__ == "__main__":
    main()
