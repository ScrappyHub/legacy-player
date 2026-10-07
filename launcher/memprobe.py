"""The Dolphin memory probe, step by step, for the app's Tools menu.

This wraps the command-line tools in tools/memory_probe (the hot-action validator) so a player can run the same
workflow without a terminal: take a baseline, do ONE thing in the game, capture, and see which known cluster of
Dolphin's emulated RAM changed. It is read-only and local: it only reads memory from the Dolphin program you have
open, never writes to it, and never sends anything anywhere. Windows only (it uses ReadProcessMemory).
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

POST_SNAPSHOTS = 4
POST_DELAY = 0.125


class ProbeError(RuntimeError):
    pass


def _base_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


class MemProbe:
    def __init__(self, data_dir: Path) -> None:
        self.out_dir = Path(data_dir) / "probe_exports"
        self._baseline: dict | None = None
        self._label = ""

    # --- loading (kept separate so tests can swap it) ---------------------------------------------------
    def _load(self) -> SimpleNamespace:
        if sys.platform != "win32":
            raise ProbeError("The memory probe reads another program's memory through Windows, so it only works on Windows.")
        try:
            from tools.memory_probe import hot_action_validator as hav
            from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
            from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
            from tools.memory_probe.game_fingerprint.fingerprint import detect_game
        except (ImportError, AttributeError, OSError) as exc:
            raise ProbeError(f"The probe tools could not be loaded here ({type(exc).__name__}: {exc}). "
                             "If psutil is missing, run: python -m pip install psutil") from exc
        hav.CLUSTER_PATH = _base_dir() / "game_packs" / "mario_party_4" / "ACTION_PAGE_CLUSTERS_v1.json"
        return SimpleNamespace(hav=hav, find_process=find_dolphin_process, find_ram=find_dolphin_ram_region, detect_game=detect_game)

    def _clusters(self, deps) -> tuple[dict, list[int]]:
        try:
            doc = deps.hav.load_clusters()
        except (OSError, ValueError) as exc:
            raise ProbeError(f"The cluster file for Mario Party 4 is missing or unreadable: {exc}") from exc
        clusters = doc["clusters"]
        offsets = sorted({int(o) for c in clusters.values() for o in c.get("page_offsets", [])})
        return clusters, offsets

    def _attach(self, deps):
        proc = deps.find_process()
        if not proc:
            raise ProbeError("Dolphin is not running. Start Dolphin and open the game first.")
        game = deps.detect_game(proc)
        if not game or game.get("game_id") == "unknown":
            raise ProbeError("Dolphin is running but no known game was recognised. Open Mario Party 4 (USA) in it.")
        ram = deps.find_ram(proc)
        if not ram:
            raise ProbeError("Could not find Dolphin's emulated RAM in its memory.")
        return proc, game, ram

    # --- steps -------------------------------------------------------------------------------------------
    def status(self) -> dict:
        out = {"supported": sys.platform == "win32", "waiting_for_action": self._baseline is not None, "label": self._label,
               "folder": str(self.out_dir)}
        try:
            deps = self._load()
        except ProbeError as exc:
            return {**out, "supported": False, "why": str(exc)}
        try:
            clusters, offsets = self._clusters(deps)
        except ProbeError as exc:
            return {**out, "ready": False, "why": str(exc)}
        out["actions"] = [{"name": n, "confidence": c.get("confidence"), "pages": len(c.get("page_offsets", []))} for n, c in clusters.items()]
        out["tracked_pages"] = len(offsets)
        try:
            proc, game, ram = self._attach(deps)
        except ProbeError as exc:
            return {**out, "ready": False, "why": str(exc)}
        return {**out, "ready": True, "game": {"id": game.get("game_id"), "region": game.get("region"), "phase": game.get("phase_hint")},
                "ram": {"base": hex(ram["base_address"]), "size": ram["region_size"]}}

    def baseline(self, label: str) -> dict:
        label = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in (label or "").strip().replace(" ", "_"))[:60] or "unlabeled_action"
        deps = self._load()
        clusters, offsets = self._clusters(deps)
        if not offsets:
            raise ProbeError("No pages are tracked yet in the cluster file.")
        proc, game, ram = self._attach(deps)
        self._baseline = {"snapshot": deps.hav.read_snapshot(proc, ram, offsets), "offsets": offsets, "label": label,
                          "game": game, "ram": ram, "pid": getattr(proc, "pid", None)}
        self._label = label
        return {"waiting_for_action": True, "label": label, "tracked_pages": len(offsets)}

    def capture(self) -> dict:
        if self._baseline is None:
            raise ProbeError("Take the baseline first, then do the action in the game, then capture.")
        base = self._baseline
        deps = self._load()
        clusters, _ = self._clusters(deps)
        proc, game, ram = self._attach(deps)
        hav = deps.hav
        posts, summary = {}, []
        best_name, best_pages = None, []
        for i in range(POST_SNAPSHOTS):
            if i:
                time.sleep(POST_DELAY)
            name = f"snapshot_{chr(ord('b') + i)}"
            posts[name] = hav.read_snapshot(proc, ram, base["offsets"])
            changed = hav.diff_snapshots(base["snapshot"], posts[name])
            summary.append({"snapshot_name": name, "changed_page_count": len(changed), "changed_byte_count": sum(c.get("changed_byte_count", 0) for c in changed)})
            if len(changed) > len(best_pages) or best_name is None:
                best_name, best_pages = name, changed
        changed_offsets = {c["page_offset"] for c in best_pages}
        results, best_cluster, best_score = {}, None, None
        for cname, cluster in clusters.items():
            score = hav.cluster_score(changed_offsets, {int(o) for o in cluster.get("page_offsets", [])})
            results[cname] = score
            if best_score is None or score["score"] > best_score["score"]:
                best_cluster, best_score = cname, score
        zero = {"overlap_count": 0, "cluster_size": 0, "changed_count": 0, "overlap_ratio": 0.0, "precision_ratio": 0.0, "score": 0.0}
        token = hav.choose_token(best_cluster, best_score or zero)
        run_id = "validator-" + uuid.uuid4().hex[:8]
        record = {"schema": "legacy_player.hot_action_validator.v1", "captured_at_utc": hav.utc_now(), "run_id": run_id,
                  "action_label": base["label"], "game": base["game"],
                  "ram_candidate": {"base_address": hex(ram["base_address"]), "region_size": ram["region_size"]},
                  "tracked_page_offsets": base["offsets"], "snapshot_a": base["snapshot"], "post_snapshots": posts,
                  "selected_post_snapshot": best_name, "changed_page_count": len(best_pages), "changed_pages": best_pages,
                  "compare_summary": summary, "cluster_results": results, "best_cluster_name": best_cluster,
                  "best_cluster_score": best_score, "token": token, "source": "legacy-player-app"}
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{run_id}_{base['label']}.json"
        hav.write_json(path, record)
        self._baseline = None
        return {"run_id": run_id, "label": base["label"], "token": token, "changed_pages": len(best_pages),
                "best_cluster": best_cluster, "best_score": best_score, "clusters": results, "compare": summary, "file": str(path),
                "waiting_for_action": False}

    def cancel(self) -> dict:
        self._baseline = None
        return {"waiting_for_action": False}
