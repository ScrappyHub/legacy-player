"""The game card: what Legacy Player can say about one game.

Two layers, always labelled so nothing is presented as more certain than it is:

  local    read from the file name and the library (region, revision or version tag, players, size, play history).
           Costs nothing and never touches the network.
  looked up  asked from Wikipedia (the article summary) and Wikidata (release date, developer, publisher, genre, number of
           players), only when the player allows internet access and presses the button. Only the game's name and
           console are sent. The answer is kept on this computer so it is asked once per game.

The player can overwrite any field on the card; what they typed always wins over what was looked up."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

WIKI_HOSTS = {"en.wikipedia.org", "www.wikidata.org"}
USER_AGENT = "LegacyPlayer/1.0 (https://github.com/Alpallyoop/legacy-player; game card lookup)"
MAX_BODY = 3_000_000

# Wikidata properties
P_RELEASE, P_DEVELOPER, P_PUBLISHER, P_GENRE, P_MAX_PLAYERS, P_MIN_PLAYERS, P_PLATFORM = "P577", "P178", "P123", "P136", "P1872", "P1873", "P400"

_VERSION = re.compile(r"\b(?:rev(?:ision)?\s*([A-Z0-9.]+)|v(\d+(?:\.\d+)+)|(beta|proto(?:type)?|demo|sample|alpha|unl|pirate|hack)\b(?:\s*(\d+))?)", re.I)


def local_card(game: dict, meta: dict | None = None) -> dict:
    """What the file name and the library already say. `game` is a library entry; `meta` the player's own choices."""
    meta = meta or {}
    tags = [str(t) for t in game.get("tags") or []]
    version_bits: list[str] = []
    other: list[str] = []
    for tag in tags:
        m = _VERSION.search(tag)
        if m:
            if m.group(1):
                version_bits.append(f"Revision {m.group(1)}")
            elif m.group(2):
                version_bits.append(f"v{m.group(2)}")
            else:
                word = m.group(3).capitalize().replace("Proto", "Prototype") if m.group(3).lower().startswith("proto") else m.group(3).capitalize()
                version_bits.append(word + (f" {m.group(4)}" if m.group(4) else ""))
        else:
            other.append(tag)
    version = meta.get("version") or ", ".join(version_bits)
    return {
        "region": game.get("region") or "",
        "version": version,
        "version_source": "you" if meta.get("version") else ("file" if version_bits else ""),
        "file_tags": other,
        "extension": game.get("extension") or "",
    }


def _get_json(url: str, opener=urllib.request.urlopen, timeout: float = 12) -> dict:
    host = urllib.parse.urlsplit(url).hostname or ""
    if host not in WIKI_HOSTS:
        raise ValueError(f"not a lookup host: {host}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with opener(request, timeout=timeout) as response:
        return json.loads(response.read(MAX_BODY))


def _year_from_time(value: str) -> str:
    m = re.match(r"[+-]?(\d{4})-(\d{2})-(\d{2})", value or "")
    if not m:
        return ""
    y, mo, d = m.groups()
    if mo == "00" or d == "00":
        return y
    return f"{y}-{mo}-{d}"


def lookup(title: str, console_name: str, opener=urllib.request.urlopen) -> dict:
    """Ask Wikipedia and Wikidata about one game. Returns the fields found (possibly none) and where they came from.
    Raises LookupError when nothing could be reached."""
    q = urllib.parse.quote(f"{title} {console_name} video game")
    try:
        search = _get_json(f"https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch={q}", opener)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise LookupError(f"Could not reach Wikipedia ({getattr(exc, 'reason', exc)}).") from exc
    hits = (search.get("query") or {}).get("search") or []
    if not hits:
        return {"found": False, "fields": {}, "source": ""}
    page_title = str(hits[0].get("title") or "")
    out: dict = {"found": True, "fields": {}, "source": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title.replace(' ', '_'))}",
                 "page": page_title}
    try:
        summary = _get_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(page_title)}", opener)
    except (urllib.error.URLError, OSError, ValueError):
        summary = {}
    extract = str(summary.get("extract") or "").strip()
    if extract:
        out["fields"]["description"] = extract[:1200]
    if summary.get("description"):
        out["fields"]["genre"] = str(summary["description"])[:60]
    item = str(summary.get("wikibase_item") or "")
    if re.fullmatch(r"Q\d+", item):
        try:
            data = _get_json(f"https://www.wikidata.org/wiki/Special:EntityData/{item}.json", opener)
            claims = ((data.get("entities") or {}).get(item) or {}).get("claims") or {}
        except (urllib.error.URLError, OSError, ValueError):
            claims = {}
        dates = []
        for c in claims.get(P_RELEASE, []):
            v = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
            if isinstance(v, dict) and v.get("time"):
                dates.append(_year_from_time(v["time"]))
        dates = sorted(d for d in dates if d)
        if dates:
            out["fields"]["release"] = dates[0]
        for prop, key in ((P_MAX_PLAYERS, "max_players"), (P_MIN_PLAYERS, "min_players")):
            for c in claims.get(prop, []):
                v = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
                amount = str(v.get("amount") or "").lstrip("+") if isinstance(v, dict) else ""
                if amount.isdigit():
                    out["fields"][key] = int(amount)
                    break
        ids: dict[str, list[str]] = {}
        for prop, key in ((P_DEVELOPER, "developer"), (P_PUBLISHER, "publisher"), (P_GENRE, "genre_item")):
            for c in claims.get(prop, [])[:3]:
                v = (((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
                if isinstance(v, dict) and re.fullmatch(r"Q\d+", str(v.get("id") or "")):
                    ids.setdefault(key, []).append(v["id"])
        wanted = sorted({i for lst in ids.values() for i in lst})
        if wanted:
            try:
                labels = _get_json("https://www.wikidata.org/w/api.php?action=wbgetentities&props=labels&languages=en&format=json&ids="
                                   + "|".join(wanted[:12]), opener)
                ents = labels.get("entities") or {}
                name = lambda i: (((ents.get(i) or {}).get("labels") or {}).get("en") or {}).get("value", "")
                for key, lst in ids.items():
                    names = [name(i) for i in lst if name(i)]
                    if names:
                        out["fields"]["genre" if key == "genre_item" else key] = ", ".join(names)[:80]
            except (urllib.error.URLError, OSError, ValueError):
                pass
    return out


class CardLookups:
    """Runs look-ups in the background and keeps the answers in <data>/gamecards/<id>.json."""

    def __init__(self, folder: Path, opener=urllib.request.urlopen) -> None:
        self.folder = Path(folder)
        self.opener = opener
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}        # game id -> {"state", "error"}

    def _path(self, game_id: str) -> Path:
        return self.folder / (re.sub(r"[^A-Za-z0-9_-]", "_", game_id) + ".json")

    def cached(self, game_id: str) -> dict | None:
        try:
            return json.loads(self._path(game_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def forget(self, game_id: str) -> None:
        try:
            self._path(game_id).unlink()
        except OSError:
            pass

    def state(self, game_id: str) -> dict:
        with self.lock:
            return dict(self.jobs.get(game_id) or {"state": "idle", "error": ""})

    def start(self, game_id: str, title: str, console_name: str, run_inline: bool = False) -> dict:
        with self.lock:
            if (self.jobs.get(game_id) or {}).get("state") == "running":
                return dict(self.jobs[game_id])
            self.jobs[game_id] = {"state": "running", "error": ""}

        def work() -> None:
            try:
                result = lookup(title, console_name, self.opener)
                result["at"] = time.time()
                self.folder.mkdir(parents=True, exist_ok=True)
                tmp = self._path(game_id).with_suffix(".tmp")
                tmp.write_text(json.dumps(result, indent=1), encoding="utf-8")
                tmp.replace(self._path(game_id))
                with self.lock:
                    self.jobs[game_id] = {"state": "done", "error": ""}
            except LookupError as exc:
                with self.lock:
                    self.jobs[game_id] = {"state": "error", "error": str(exc)}
            except Exception as exc:          # a surprise must not leave the card spinning forever
                with self.lock:
                    self.jobs[game_id] = {"state": "error", "error": f"The look-up failed ({type(exc).__name__})."}
        if run_inline:
            work()
        else:
            threading.Thread(target=work, daemon=True, name="gamecard").start()
        return self.state(game_id)
