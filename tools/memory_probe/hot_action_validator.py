import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
from tools.memory_probe.game_fingerprint.fingerprint import detect_game
from tools.memory_probe.memory_reader.reader import read_region


EXPORT_DIR = Path("tools/memory_probe/exports")
CLUSTER_PATH = Path("game_packs/mario_party_4/ACTION_PAGE_CLUSTERS_v1.json")

PAGE_SIZE = 4096
POST_SNAPSHOT_COUNT = 4
POST_SNAPSHOT_DELAY_SECONDS = 0.125
PREVIEW_HEX_BYTES = 32

TOKEN_MATCH_START_MINIGAME = "MATCH_START_MINIGAME"
TOKEN_MATCH_BOARD_SPACE = "MATCH_BOARD_SPACE"
TOKEN_MATCH_COIN_TOTAL = "MATCH_COIN_TOTAL"
TOKEN_NO_STRONG_MATCH = "NO_STRONG_MATCH"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_export_dir() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_clusters() -> dict:
    if not CLUSTER_PATH.exists():
        raise FileNotFoundError(f"CLUSTER_FILE_MISSING: {CLUSTER_PATH}")
    return json.loads(CLUSTER_PATH.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict) -> None:
    text = json.dumps(obj, indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def read_page(proc, base_address: int, page_offset: int) -> dict:
    absolute_address = base_address + page_offset
    data = read_region(proc, absolute_address, PAGE_SIZE)

    if data is None:
        return {
            "page_offset": page_offset,
            "absolute_address": hex(absolute_address),
            "page_size": PAGE_SIZE,
            "data_sha256": None,
            "preview_hex": None,
            "data_hex": None,
        }

    import hashlib

    return {
        "page_offset": page_offset,
        "absolute_address": hex(absolute_address),
        "page_size": len(data),
        "data_sha256": hashlib.sha256(data).hexdigest(),
        "preview_hex": data[:PREVIEW_HEX_BYTES].hex(),
        "data_hex": data.hex(),
    }


def read_snapshot(proc, ram_region: dict, tracked_offsets: list[int]) -> dict:
    base_address = ram_region["base_address"]
    pages = [read_page(proc, base_address, offset) for offset in tracked_offsets]
    return {
        "captured_at_utc": utc_now(),
        "base_address": hex(base_address),
        "region_size": ram_region["region_size"],
        "protect": hex(ram_region["protect"]),
        "type": hex(ram_region["type"]),
        "tracked_page_count": len(pages),
        "pages": pages,
    }


def _changed_byte_count(a_hex: str | None, b_hex: str | None) -> int:
    if a_hex is None or b_hex is None:
        return 0

    a_bytes = bytes.fromhex(a_hex)
    b_bytes = bytes.fromhex(b_hex)
    compare_len = min(len(a_bytes), len(b_bytes))

    changed = 0
    for i in range(compare_len):
        if a_bytes[i] != b_bytes[i]:
            changed += 1

    changed += abs(len(a_bytes) - len(b_bytes))
    return changed


def diff_snapshots(snapshot_a: dict, snapshot_b: dict) -> list[dict]:
    pages_a = {p["page_offset"]: p for p in snapshot_a["pages"]}
    pages_b = {p["page_offset"]: p for p in snapshot_b["pages"]}

    changed_pages = []
    all_offsets = sorted(set(pages_a.keys()) | set(pages_b.keys()))

    for offset in all_offsets:
        a = pages_a.get(offset)
        b = pages_b.get(offset)

        if a is None or b is None:
            changed_pages.append({
                "page_offset": offset,
                "absolute_address": None if b is None else b["absolute_address"],
                "changed_byte_count": 0,
                "reason": "missing_in_one_snapshot",
            })
            continue

        if a["data_hex"] == b["data_hex"]:
            continue

        changed_pages.append({
            "page_offset": offset,
            "absolute_address": b["absolute_address"],
            "changed_byte_count": _changed_byte_count(a["data_hex"], b["data_hex"]),
        })

    changed_pages.sort(key=lambda x: (x["changed_byte_count"], x["page_offset"]), reverse=True)
    return changed_pages


def cluster_score(changed_page_offsets: set[int], cluster_page_offsets: set[int]) -> dict:
    if not cluster_page_offsets:
        return {
            "overlap_count": 0,
            "cluster_size": 0,
            "changed_count": len(changed_page_offsets),
            "overlap_ratio": 0.0,
            "precision_ratio": 0.0,
            "score": 0.0,
        }

    overlap = changed_page_offsets & cluster_page_offsets
    overlap_count = len(overlap)
    cluster_size = len(cluster_page_offsets)
    changed_count = len(changed_page_offsets)

    overlap_ratio = overlap_count / cluster_size if cluster_size else 0.0
    precision_ratio = overlap_count / changed_count if changed_count else 0.0

    score = (overlap_ratio * 0.7) + (precision_ratio * 0.3)

    return {
        "overlap_count": overlap_count,
        "cluster_size": cluster_size,
        "changed_count": changed_count,
        "overlap_ratio": round(overlap_ratio, 6),
        "precision_ratio": round(precision_ratio, 6),
        "score": round(score, 6),
    }


def choose_token(best_cluster_name: str | None, best_score: dict) -> str:
    if best_cluster_name is None:
        return TOKEN_NO_STRONG_MATCH

    if best_score["overlap_count"] <= 0:
        return TOKEN_NO_STRONG_MATCH

    if best_cluster_name == "start_minigame_once":
        return TOKEN_MATCH_START_MINIGAME
    if best_cluster_name == "board_space_land_once":
        return TOKEN_MATCH_BOARD_SPACE
    if best_cluster_name == "coin_total_change_once":
        return TOKEN_MATCH_COIN_TOTAL

    return TOKEN_NO_STRONG_MATCH


def main() -> None:
    ensure_export_dir()

    action_label = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    if not action_label:
        action_label = input("Action label: ").strip()
    if not action_label:
        action_label = "unlabeled_action"

    clusters_doc = load_clusters()
    clusters = clusters_doc["clusters"]

    tracked_offsets = set()
    for cluster in clusters.values():
        for offset in cluster.get("page_offsets", []):
            tracked_offsets.add(int(offset))
    tracked_offsets = sorted(tracked_offsets)

    if not tracked_offsets:
        print("ERROR: NO_TRACKED_PAGES")
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

    run_id = "validator-" + str(uuid.uuid4())[:8]
    out_path = EXPORT_DIR / f"{run_id}_{action_label}.json"

    print("")
    print("=== HOT ACTION VALIDATOR ===")
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
        f"score={ram_region.get('score')}"
    )
    print("")
    print(f"tracked_page_count: {len(tracked_offsets)}")
    print(f"post_snapshot_count: {POST_SNAPSHOT_COUNT}")
    print(f"post_snapshot_delay_seconds: {POST_SNAPSHOT_DELAY_SECONDS}")
    print("")

    input("Press Enter for BASELINE snapshot...")
    snapshot_a = read_snapshot(proc, ram_region, tracked_offsets)

    print("")
    print("Perform ONE intentional in-game action now.")
    print("Press Enter immediately after the action occurs...")
    input()

    post_snapshots = {}
    for i in range(POST_SNAPSHOT_COUNT):
        if i > 0:
            time.sleep(POST_SNAPSHOT_DELAY_SECONDS)
        name = f"snapshot_{chr(ord('b') + i)}"
        post_snapshots[name] = read_snapshot(proc, ram_region, tracked_offsets)

    compare_summary = []
    best_snapshot_name = None
    best_changed_pages = []
    best_changed_count = -1

    for name, snap in post_snapshots.items():
        changed_pages = diff_snapshots(snapshot_a, snap)
        changed_count = len(changed_pages)
        changed_bytes = sum(x.get("changed_byte_count", 0) for x in changed_pages)

        compare_summary.append({
            "snapshot_name": name,
            "changed_page_count": changed_count,
            "changed_byte_count": changed_bytes,
        })

        if changed_count > best_changed_count:
            best_changed_count = changed_count
            best_snapshot_name = name
            best_changed_pages = changed_pages

    changed_page_offsets = {x["page_offset"] for x in best_changed_pages}

    cluster_results = {}
    best_cluster_name = None
    best_cluster_score = None

    for cluster_name, cluster in clusters.items():
        page_offsets = {int(x) for x in cluster.get("page_offsets", [])}
        score = cluster_score(changed_page_offsets, page_offsets)
        cluster_results[cluster_name] = score

        if best_cluster_score is None or score["score"] > best_cluster_score["score"]:
            best_cluster_name = cluster_name
            best_cluster_score = score

    token = choose_token(best_cluster_name, best_cluster_score or {
        "overlap_count": 0,
        "cluster_size": 0,
        "changed_count": 0,
        "overlap_ratio": 0.0,
        "precision_ratio": 0.0,
        "score": 0.0,
    })

    result = {
        "schema": "legacy_player.hot_action_validator.v1",
        "captured_at_utc": utc_now(),
        "run_id": run_id,
        "action_label": action_label,
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
        "tracked_page_offsets": tracked_offsets,
        "tracked_page_count": len(tracked_offsets),
        "snapshot_a": snapshot_a,
        "post_snapshots": post_snapshots,
        "selected_post_snapshot": best_snapshot_name,
        "changed_page_count": len(best_changed_pages),
        "changed_pages": best_changed_pages,
        "compare_summary": compare_summary,
        "cluster_results": cluster_results,
        "best_cluster_name": best_cluster_name,
        "best_cluster_score": best_cluster_score,
        "token": token,
    }

    write_json(out_path, result)

    print("")
    print(f"WROTE: {out_path}")
    print(f"CHANGED_PAGE_COUNT: {len(best_changed_pages)}")
    print(f"SELECTED_POST_SNAPSHOT: {best_snapshot_name}")

    for row in compare_summary:
        print(
            f"COMPARE: {row['snapshot_name']} "
            f"pages_changed={row['changed_page_count']} "
            f"bytes_changed={row['changed_byte_count']}"
        )

    print("")
    print(f"BEST_CLUSTER: {best_cluster_name}")
    if best_cluster_score is not None:
        print(
            f"BEST_SCORE: overlap={best_cluster_score['overlap_count']}/"
            f"{best_cluster_score['cluster_size']} "
            f"score={best_cluster_score['score']}"
        )

    print(token)


if __name__ == "__main__":
    main()