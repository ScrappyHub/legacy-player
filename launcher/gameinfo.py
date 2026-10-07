"""How many people can play a game, and how. Legacy Player has to know this to host a room sensibly: a one-player
adventure cannot be shared, and a four-player party game should offer four seats.

Three sources, always labelled so nothing is presented as more certain than it is:
  you      the player set it on the game's page
  known    a title in the built-in list below (written from the games' own specs; short, and only what is certain)
  console  nothing is known about this title, so this is what the console's controller ports allow
"""
from __future__ import annotations

import re

# console id -> (players a typical game can use, most the hardware can ever take with its usual adapter)
CONSOLE_LIMITS = {
    "atari": (2, 2), "nes": (2, 4), "snes": (2, 5), "genesis": (2, 4), "gb": (2, 2), "gbc": (2, 2), "ps1": (2, 8),
    "n64": (4, 4), "gba": (4, 4), "gamecube": (4, 4), "ps2": (2, 8), "xbox": (4, 4), "ds": (4, 4), "psp": (4, 4),
    "wii": (4, 4), "x360": (4, 4), "3ds": (4, 4), "ps3": (4, 4),
}
# mode: single | versus | coop | both | turns   (turns = players take turns on one game)
KNOWN: dict[str, tuple[int, str]] = {
    "super mario 64": (1, "single"), "super mario sunshine": (1, "single"), "ocarina of time": (1, "single"),
    "majora": (1, "single"), "wind waker": (1, "single"), "twilight princess": (1, "single"), "metroid prime": (1, "single"),
    "super metroid": (1, "single"), "chrono trigger": (1, "single"), "earthbound": (1, "single"), "link to the past": (1, "single"),
    "luigi's mansion": (1, "single"), "super mario world": (2, "turns"), "super mario bros": (2, "turns"),
    "sonic the hedgehog": (1, "single"), "sonic the hedgehog 2": (2, "both"), "sonic the hedgehog 3": (2, "both"),
    "secret of mana": (3, "coop"), "seiken densetsu 3": (2, "coop"), "crystal chronicles": (4, "coop"), "four swords": (4, "coop"),
    "mario kart": (4, "versus"), "super smash bros": (4, "versus"), "mario party": (4, "versus"), "goldeneye": (4, "versus"),
    "perfect dark": (4, "both"), "mario tennis": (4, "versus"), "mario golf": (4, "versus"), "diddy kong racing": (4, "versus"),
    "bomberman": (4, "versus"), "contra": (2, "coop"), "double dragon": (2, "both"), "streets of rage": (2, "both"),
    "teenage mutant ninja turtles": (2, "coop"), "bubble bobble": (2, "coop"), "donkey kong country": (2, "both"),
    "street fighter": (2, "versus"), "mortal kombat": (2, "versus"), "tekken": (2, "versus"), "killer instinct": (2, "versus"),
    "tetris": (2, "versus"), "pokemon": (2, "versus"), "pokémon": (2, "versus"), "final fantasy": (1, "single"),
    "dragon quest": (1, "single"), "dragon warrior": (1, "single"), "castlevania": (1, "single"), "pikmin 2": (2, "both"),
    "metal slug": (2, "coop"), "kirby super star": (2, "coop"), "kirby's dream land 3": (2, "coop"), "mega man": (1, "single"),
}
_NOISE = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")


def _norm(title: str) -> str:
    return re.sub(r"\s+", " ", _NOISE.sub("", title or "").lower().replace("_", " ")).strip()


def _best_match(title: str) -> tuple[int, str] | None:
    name = _norm(title)
    best = None
    for key in KNOWN:
        if key in name and (best is None or len(key) > len(best)):
            best = key
    return KNOWN[best] if best else None


def _label(maximum: int, mode: str) -> str:
    if maximum <= 1:
        return "Single-player only"
    how = {"versus": "versus", "coop": "co-op", "both": "co-op and versus", "turns": "taking turns"}.get(mode, "")
    return f"1 to {maximum} players" + (f" · {how}" if how else "")


def players_for(console_id: str, title: str, override: str = "") -> dict:
    """{max, hw, mode, coop, versus, shareable, source, label, note}"""
    typical, hw = CONSOLE_LIMITS.get(console_id, (2, 2))
    text = (override or "").strip()
    if text.isdigit() and 1 <= int(text) <= 8:
        n = int(text)
        mode, source = ("single" if n == 1 else "both"), "you"
    else:
        found = _best_match(title)
        if found:
            n, mode = found
            source = "known"
        else:
            n, mode, source = typical, "", "console"
    note = {"you": "Set by you.", "known": "From Legacy Player's built-in list.",
            "console": "Not known for this game. This is what the console usually allows; check the box, or set it yourself."}[source]
    return {"max": n, "hw": max(hw, n), "mode": mode, "coop": mode in ("coop", "both"), "versus": mode in ("versus", "both"),
            "shareable": n >= 2, "source": source, "label": _label(n, mode), "note": note}
