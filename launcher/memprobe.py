"""The Dolphin memory probe, step by step, for any GameCube or Wii game.

What it answers: "when I do ONE thing in this game, which part of Dolphin's emulated memory changes?"

How: it reads all of the game's emulated RAM as 4 KB pages and keeps a short fingerprint of each page. A baseline is
read twice a moment apart, and any page that changed on its own is marked as noise and ignored. After you do the one
thing in the game, RAM is read again and the pages that changed are the answer. The answer is remembered per game under
the label you gave it; doing the same thing again keeps only the pages that changed both times, so a label becomes more
trustworthy the more you repeat it. Every capture is also compared with the other labels learned for the same game, so
the probe can say "this looks like what you called start_minigame".

It is read-only and local: it only reads memory from the Dolphin program you have open, never writes to it, and never
sends anything anywhere. Windows only (it uses ReadProcessMemory).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

PAGE = 4096
CHUNK = 1024 * 1024
MAX_SCAN = 64 * 1024 * 1024
NOISE_GAP = 0.2
POST_SNAPSHOTS = 3
POST_DELAY = 0.125
STRONG_OVERLAP = 2
STRONG_SCORE = 0.5
MAX_LISTED = 400


class ProbeError(RuntimeError):
    pass


def _base_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_label(raw: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", (raw or "").strip()).strip("_")[:60]
    return text or "unlabeled_action"


def game_key(game: dict) -> tuple[str, str]:
    """(storage key, display name). Dolphin's window title carries the six-character game id when it knows the game; if
    not, the title itself is used so any game still gets its own memory."""
    gid = (game or {}).get("game_id") or "unknown"
    title = ((game or {}).get("active_window_title") or "").strip()
    if gid != "unknown":
        return gid, f"{gid} ({(game or {}).get('region') or '?'})"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
    return (f"title-{slug}" if slug else "unknown-game"), title or "an unrecognised game"


def read_pages(read_region, proc, ram: dict) -> list[str | None]:
    """A short fingerprint of every 4 KB page of the game's RAM (None where Windows would not let us read)."""
    base, size = int(ram["base_address"]), min(int(ram["region_size"]), MAX_SCAN)
    out: list[str | None] = []
    offset = 0
    while offset < size:
        want = min(CHUNK, size - offset)
        data = read_region(proc, base + offset, want)
        for start in range(0, want, PAGE):
            if data is None or start + PAGE > len(data):
                out.append(None)
            else:
                out.append(hashlib.blake2b(data[start:start + PAGE], digest_size=8).hexdigest())
        offset += want
    return out


def diff_pages(before: list, after: list, noisy: set[int]) -> list[int]:
    return [i for i in range(min(len(before), len(after)))
            if i not in noisy and before[i] is not None and after[i] is not None and before[i] != after[i]]


def score(changed: set[int], cluster: set[int]) -> dict:
    overlap = len(changed & cluster)
    recall = overlap / len(cluster) if cluster else 0.0
    precision = overlap / len(changed) if changed else 0.0
    return {"overlap_count": overlap, "cluster_size": len(cluster), "changed_count": len(changed),
            "overlap_ratio": round(recall, 6), "precision_ratio": round(precision, 6), "score": round(recall * 0.7 + precision * 0.3, 6)}


class MemProbe:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir) / "probe"
        self.out_dir = Path(data_dir) / "probe_exports"
        self._baseline: dict | None = None

    # --- loading (kept separate so tests can swap it) ---------------------------------------------------
    def _load(self) -> SimpleNamespace:
        if sys.platform != "win32":
            raise ProbeError("The memory probe reads another program's memory through Windows, so it only works on Windows.")
        try:
            from tools.memory_probe.dolphin_attach.attach import find_dolphin_process
            from tools.memory_probe.dolphin_attach.ram_map import find_dolphin_ram_region
            from tools.memory_probe.game_fingerprint.fingerprint import detect_game
            from tools.memory_probe.memory_reader.reader import read_region
        except (ImportError, AttributeError, OSError) as exc:
            raise ProbeError(f"The probe tools could not be loaded here ({type(exc).__name__}: {exc}). "
                             "If psutil is missing, run: python -m pip install psutil") from exc
        return SimpleNamespace(find_process=find_dolphin_process, find_ram=find_dolphin_ram_region,
                               detect_game=detect_game, read_region=read_region)

    def _attach(self, deps):
        proc = deps.find_process()
        if not proc:
            raise ProbeError("Dolphin is not running. Start Dolphin and open a game first.")
        game = deps.detect_game(proc) or {}
        ram = deps.find_ram(proc)
        if not ram:
            raise ProbeError("Could not find the game's emulated RAM in Dolphin's memory. Is a game running (not paused on the game list)?")
        return proc, game, ram

    # --- what has been learned, per game ----------------------------------------------------------------
    def _store_path(self, key: str) -> Path:
        return self.dir / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', key)}.json"

    def _load_store(self, key: str) -> dict:
        path = self._store_path(key)
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc.get("labels"), dict):
                return doc
        except (OSError, ValueError):
            pass
        doc = {"schema": "legacy_player.probe_labels.v1", "game": key, "labels": {}}
        self._seed(key, doc)
        return doc

    def _seed(self, key: str, doc: dict) -> None:
        """Mario Party 4 (USA) ships with the pages found for it so far; every other game starts empty."""
        if key != "GMPE01":
            return
        try:
            pack = json.loads((_base_dir() / "game_packs" / "mario_party_4" / "ACTION_PAGE_CLUSTERS_v1.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for name, cluster in pack.get("clusters", {}).items():
            offsets = [int(o) for o in cluster.get("page_offsets", [])]
            if offsets:
                doc["labels"][name] = {"runs": 1, "pages": sorted({o // PAGE for o in offsets}), "confidence": "shipped",
                                       "updated": _now(), "note": "from the Mario Party 4 game pack"}

    def _save_store(self, key: str, doc: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._store_path(key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @staticmethod
    def _listing(doc: dict) -> list[dict]:
        return [{"name": n, "runs": v.get("runs", 1), "pages": len(v.get("pages", [])), "confidence": v.get("confidence", "candidate"),
                 "updated": v.get("updated")} for n, v in sorted(doc["labels"].items())]

    # --- steps -------------------------------------------------------------------------------------------
    def status(self) -> dict:
        out = {"supported": sys.platform == "win32", "waiting_for_action": self._baseline is not None,
               "label": (self._baseline or {}).get("label", ""), "folder": str(self.out_dir)}
        try:
            deps = self._load()
        except ProbeError as exc:
            return {**out, "supported": False, "why": str(exc)}
        try:
            proc, game, ram = self._attach(deps)
        except ProbeError as exc:
            return {**out, "ready": False, "why": str(exc)}
        key, name = game_key(game)
        doc = self._load_store(key)
        return {**out, "ready": True, "game": {"key": key, "name": name, "region": game.get("region"),
                                               "title": game.get("active_window_title")},
                "ram": {"base": hex(ram["base_address"]), "size": ram["region_size"], "pages": min(ram["region_size"], MAX_SCAN) // PAGE},
                "learned": self._listing(doc)}

    def baseline(self, label: str) -> dict:
        label = safe_label(label)
        deps = self._load()
        proc, game, ram = self._attach(deps)
        key, name = game_key(game)
        first = read_pages(deps.read_region, proc, ram)
        time.sleep(NOISE_GAP)
        second = read_pages(deps.read_region, proc, ram)
        noisy = {i for i in range(min(len(first), len(second))) if first[i] != second[i]}
        if sum(1 for d in second if d is not None) == 0:
            raise ProbeError("Windows would not let the probe read Dolphin's memory. Try running Legacy Player and Dolphin as the same user.")
        self._baseline = {"pages": second, "noisy": noisy, "label": label, "key": key, "name": name, "ram": ram,
                          "game": game, "pid": getattr(proc, "pid", None)}
        return {"waiting_for_action": True, "label": label, "game": name, "pages": len(second), "noisy_pages": len(noisy)}

    def capture(self) -> dict:
        base = self._baseline
        if base is None:
            raise ProbeError("Take the baseline first, then do the action in the game, then capture.")
        deps = self._load()
        proc, game, ram = self._attach(deps)
        key, name = game_key(game)
        if key != base["key"]:
            self._baseline = None
            raise ProbeError("The game in Dolphin changed since the baseline. Start again with the new game.")
        best, best_name, summary = [], None, []
        for i in range(POST_SNAPSHOTS):
            if i:
                time.sleep(POST_DELAY)
            snap = read_pages(deps.read_region, proc, ram)
            changed = diff_pages(base["pages"], snap, base["noisy"])
            summary.append({"snapshot_name": f"snapshot_{chr(ord('b') + i)}", "changed_page_count": len(changed)})
            if best_name is None or len(changed) > len(best):
                best, best_name, best_pages = changed, summary[-1]["snapshot_name"], snap
        changed_set = set(best)
        label = base["label"]
        doc = self._load_store(key)
        results = {n: score(changed_set, set(v.get("pages", []))) for n, v in doc["labels"].items() if n != label}
        top = max(results, key=lambda n: results[n]["score"]) if results else None
        top_score = results[top] if top else None
        strong = bool(top_score and top_score["overlap_count"] >= STRONG_OVERLAP and top_score["score"] >= STRONG_SCORE)
        learned = None
        if changed_set:
            old = doc["labels"].get(label)
            if old:
                both = sorted(changed_set & set(old.get("pages", [])))
                agreed = bool(both)
                pages = both if agreed else sorted(changed_set)
                runs = old.get("runs", 1) + 1
                conf = "grounded" if agreed and runs >= 2 else "candidate"
                learned = {"runs": runs, "pages": len(pages), "confidence": conf, "agreed_with_before": agreed,
                           "note": None if agreed else "This run shared no pages with the earlier one, so the earlier pages were replaced."}
            else:
                pages, learned = sorted(changed_set), {"runs": 1, "pages": len(changed_set), "confidence": "candidate", "agreed_with_before": None, "note": None}
            doc["labels"][label] = {"runs": learned["runs"], "pages": pages, "confidence": learned["confidence"], "updated": _now()}
            self._save_store(key, doc)
        if not changed_set:
            token = "NOTHING_CHANGED"
        elif strong:
            token = "MATCH_" + top.upper()
        else:
            token = "NO_STRONG_MATCH"
        run_id = "probe-" + uuid.uuid4().hex[:8]
        listed = [{"page": i, "page_offset": i * PAGE, "absolute_address": hex(int(ram["base_address"]) + i * PAGE),
                   "before": base["pages"][i], "after": best_pages[i]} for i in best[:MAX_LISTED]]
        record = {"schema": "legacy_player.probe_capture.v2", "captured_at_utc": _now(), "run_id": run_id, "action_label": label,
                  "game": {"key": key, "name": name, "info": game}, "ram": {"base_address": hex(int(ram["base_address"])), "region_size": ram["region_size"]},
                  "noise_page_count": len(base["noisy"]), "changed_page_count": len(best), "changed_pages": listed,
                  "compare_summary": summary, "other_labels": results, "best_other_label": top, "token": token, "learned": learned}
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{run_id}_{label}.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
        self._baseline = None
        return {"run_id": run_id, "label": label, "game": name, "token": token, "changed_pages": len(best),
                "noise_pages": len(base["noisy"]), "best_label": top, "best_score": top_score, "matched": strong,
                "learned": learned, "compare": summary, "file": str(path), "waiting_for_action": False,
                "top_pages": [{"address": r["absolute_address"], "offset": r["page_offset"]} for r in listed[:12]]}

    def forget(self, label: str) -> dict:
        deps = self._load()
        _, game, _ = self._attach(deps)
        key, _ = game_key(game)
        doc = self._load_store(key)
        if doc["labels"].pop(safe_label(label), None) is None:
            raise ProbeError("That label is not saved for this game.")
        self._save_store(key, doc)
        return {"learned": self._listing(doc)}

    def cancel(self) -> dict:
        self._baseline = None
        return {"waiting_for_action": False}
