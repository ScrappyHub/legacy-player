import hashlib
import time

from tools.memory_probe.game_fingerprint.fingerprint import detect_game
from tools.memory_probe.memory_reader.reader import iter_readable_regions, read_region
from tools.memory_probe.memory_reader.hexutil import short_hex


def _score_region(region):
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


def _select_candidate_regions(regions, limit=8):
    ranked = sorted(regions, key=_score_region, reverse=True)
    return ranked[:limit]


def _sha256_hex(data):
    if data is None:
        return None
    return hashlib.sha256(data).hexdigest()


def run_sampler(proc, writer):
    last_phase_hint = None
    last_active_title = None
    last_region_hashes = {}

    regions = iter_readable_regions(proc, limit=256)
    candidate_regions = _select_candidate_regions(regions, limit=8)

    writer.emit({
        "kind": "memory",
        "event": "readable_region_inventory",
        "payload": {
            "count": len(regions),
            "regions": [
                {
                    "base_address": hex(r["base_address"]),
                    "region_size": r["region_size"],
                    "protect": hex(r["protect"]),
                    "type": hex(r["type"]),
                }
                for r in regions[:16]
            ],
        },
    })

    writer.emit({
        "kind": "memory",
        "event": "candidate_region_selection",
        "payload": {
            "count": len(candidate_regions),
            "regions": [
                {
                    "base_address": hex(r["base_address"]),
                    "region_size": r["region_size"],
                    "protect": hex(r["protect"]),
                    "type": hex(r["type"]),
                    "score": _score_region(r),
                }
                for r in candidate_regions
            ],
        },
    })

    for i in range(10):
        alive = True

        try:
            _ = proc.status()
        except Exception:
            alive = False

        game = detect_game(proc)
        phase_hint = game.get("phase_hint", "unknown")
        active_title = game.get("active_window_title", "")
        game_id = game.get("game_id", "unknown")
        region = game.get("region", "unknown")

        writer.emit({
            "kind": "sample",
            "event": "tick",
            "iteration": i,
            "pid": proc.pid,
            "alive": alive,
            "phase_hint": phase_hint,
            "game_id": game_id,
            "region": region,
            "active_window_title": active_title,
        })

        if phase_hint != last_phase_hint:
            writer.emit({
                "kind": "phase",
                "event": "phase_transition_candidate",
                "payload": {
                    "from": last_phase_hint,
                    "to": phase_hint,
                    "iteration": i,
                    "game_id": game_id,
                    "region": region,
                },
            })
            last_phase_hint = phase_hint

        if active_title != last_active_title:
            writer.emit({
                "kind": "window",
                "event": "active_window_title_changed",
                "payload": {
                    "from": last_active_title,
                    "to": active_title,
                    "iteration": i,
                    "game_id": game_id,
                    "region": region,
                },
            })
            last_active_title = active_title

        for r in candidate_regions:
            base = r["base_address"]
            data = read_region(proc, base, 256)
            data_hex = short_hex(data, max_len=128)
            data_hash = _sha256_hex(data)

            writer.emit({
                "kind": "memory",
                "event": "region_probe_sample",
                "payload": {
                    "iteration": i,
                    "base_address": hex(base),
                    "region_size": r["region_size"],
                    "protect": hex(r["protect"]),
                    "type": hex(r["type"]),
                    "data_hex": data_hex,
                    "data_sha256": data_hash,
                    "game_id": game_id,
                    "region": region,
                },
            })

            old_hash = last_region_hashes.get(base)
            if data_hash != old_hash:
                writer.emit({
                    "kind": "memory",
                    "event": "region_probe_change_candidate",
                    "payload": {
                        "iteration": i,
                        "base_address": hex(base),
                        "old_sha256": old_hash,
                        "new_sha256": data_hash,
                        "game_id": game_id,
                        "region": region,
                    },
                })
                last_region_hashes[base] = data_hash

        time.sleep(1)