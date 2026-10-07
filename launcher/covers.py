"""Cover art from the libretro thumbnails project (thumbnails.libretro.com), the same pictures RetroArch uses.
Only game names are sent (as part of a file address); nothing else. It runs only when the user presses the button
and has allowed internet access, one picture at a time, and every picture is kept on this computer."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOST = "thumbnails.libretro.com"
SYSTEMS = {
    "nes": "Nintendo - Nintendo Entertainment System", "snes": "Nintendo - Super Nintendo Entertainment System",
    "gb": "Nintendo - Game Boy", "gbc": "Nintendo - Game Boy Color", "gba": "Nintendo - Game Boy Advance",
    "n64": "Nintendo - Nintendo 64", "ds": "Nintendo - Nintendo DS", "3ds": "Nintendo - Nintendo 3DS",
    "gamecube": "Nintendo - GameCube", "wii": "Nintendo - Wii", "genesis": "Sega - Mega Drive - Genesis",
    "ps1": "Sony - PlayStation", "ps2": "Sony - PlayStation 2", "psp": "Sony - PlayStation Portable", "ps3": "Sony - PlayStation 3",
    "xbox": "Microsoft - Xbox", "x360": "Microsoft - Xbox 360", "atari": "Atari - 2600",
}
MAX_BYTES = 3_000_000
REGIONS = ("USA", "World", "Europe", "Japan", "USA, Europe", "Japan, USA")


def clean_name(name: str) -> str:
    """libretro stores names with these characters turned into underscores."""
    return re.sub(r'[&*/:`<>?\\|"]', "_", name).strip()


def candidates(game: dict) -> list[str]:
    stem = Path(game["path"]).stem
    out = [stem]
    base = re.sub(r"\s*[\(\[].*$", "", stem).strip() or game["title"]
    if game.get("region"):
        out.append(f"{base} ({game['region']})")
    out += [f"{base} ({r})" for r in REGIONS]
    seen, uniq = set(), []
    for c in out:
        c = clean_name(c)
        if c and c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def cover_path(cache: Path, game_id: str) -> Path:
    return Path(cache) / (re.sub(r"[^A-Za-z0-9_-]", "_", game_id) + ".png")


def fetch_png(system: str, name: str, opener=urllib.request.urlopen, scheme: str = "https", host: str = HOST) -> bytes | None:
    url = f"{scheme}://{host}/{urllib.parse.quote(system)}/Named_Boxarts/{urllib.parse.quote(name)}.png"
    try:
        with opener(urllib.request.Request(url, headers={"User-Agent": "LegacyPlayer-covers"}), timeout=12) as resp:
            data = resp.read(MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) <= MAX_BYTES else None


class CoverFetcher:
    def __init__(self, cache: Path, opener=urllib.request.urlopen, scheme: str = "https", host: str = HOST, pause: float = 0.05) -> None:
        self.cache, self.opener, self.scheme, self.host, self.pause = Path(cache), opener, scheme, host, pause
        self.cache.mkdir(parents=True, exist_ok=True)
        self.state, self.done, self.total, self.found, self.current = "idle", 0, 0, 0, ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._miss_file = self.cache / "_misses.json"

    def misses(self) -> dict:
        try:
            return json.loads(self._miss_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def start(self, games: list[dict]) -> dict:
        if self.state == "running":
            return self.view()
        misses = self.misses()
        todo = [g for g in games if g["console"] in SYSTEMS and not cover_path(self.cache, g["id"]).exists()
                and time.time() - misses.get(g["id"], 0) > 7 * 86400]
        self._stop.clear()
        self.state, self.done, self.total, self.found = "running", 0, len(todo), 0

        def work() -> None:
            try:
                for g in todo:
                    if self._stop.is_set():
                        break
                    self.current = g["title"]
                    data = None
                    for name in candidates(g):
                        data = fetch_png(SYSTEMS[g["console"]], name, self.opener, self.scheme, self.host)
                        if data:
                            break
                    if data:
                        cover_path(self.cache, g["id"]).write_bytes(data)
                        self.found += 1
                    else:
                        misses[g["id"]] = time.time()
                    self.done += 1
                    time.sleep(self.pause)
                self._miss_file.write_text(json.dumps(misses), encoding="utf-8")
                self.state = "stopped" if self._stop.is_set() else "done"
            except Exception:
                self.state = "error"

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        return self.view()

    def cancel(self) -> dict:
        self._stop.set()
        return self.view()

    def view(self) -> dict:
        have = sum(1 for _ in self.cache.glob("*.png"))
        return {"state": self.state, "done": self.done, "total": self.total, "found": self.found, "current": self.current, "have": have}
