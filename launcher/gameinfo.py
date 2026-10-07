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
    "metal slug": (2, "coop"),
    "link's awakening": (1, "single"), "minish cap": (1, "single"), "oracle of seasons": (1, "single"), "oracle of ages": (1, "single"),
    "phantom hourglass": (1, "single"), "spirit tracks": (1, "single"), "legend of zelda": (1, "single"), "metroid": (1, "single"),
    "metroid fusion": (1, "single"), "zero mission": (1, "single"), "metroid prime hunters": (4, "versus"), "symphony of the night": (1, "single"),
    "kingdom hearts": (1, "single"), "metal gear solid": (1, "single"), "resident evil": (1, "single"), "silent hill": (1, "single"),
    "shadow of the colossus": (1, "single"), "god of war": (1, "single"), "persona": (1, "single"), "paper mario": (1, "single"),
    "super mario rpg": (1, "single"), "yoshi's island": (1, "single"), "kirby's adventure": (1, "single"), "banjo-kazooie": (1, "single"),
    "conker's bad fur day": (4, "versus"), "star fox 64": (4, "both"), "pilotwings 64": (1, "single"), "wave race 64": (2, "versus"),
    "f-zero x": (4, "versus"), "pokemon stadium": (4, "versus"), "pokemon snap": (1, "single"), "pikmin": (1, "single"),
    "wii sports": (4, "versus"), "wii party": (4, "versus"), "dr. mario": (2, "versus"), "dr mario": (2, "versus"),
    "bust-a-move": (2, "versus"), "puzzle bobble": (2, "versus"), "soul calibur": (2, "versus"), "worms": (4, "versus"),
    "gauntlet": (4, "coop"), "golden axe": (2, "coop"), "final fight": (2, "coop"), "battletoads": (2, "coop"), "river city": (2, "coop"),
    "the simpsons": (4, "coop"), "monster hunter": (4, "coop"), "super mario land": (1, "single"), "earthworm jim": (1, "single"), "kirby super star": (2, "coop"), "kirby's dream land 3": (2, "coop"), "mega man": (1, "single"),
}
_NOISE = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")


def _norm(title: str) -> str:
    return re.sub(r"\s+", " ", _NOISE.sub("", title or "").lower().replace("_", " ").replace("\u2019", "'")).strip()


def _best_match(title: str) -> tuple[int, str] | None:
    """The most specific known title inside this one. A multiplayer entry beats a broad single-player one
    ("legend of zelda" is single-player, "four swords" is not), otherwise the longest name wins."""
    name = _norm(title)
    hits = [key for key in KNOWN if key in name]
    if not hits:
        return None
    multi = [k for k in hits if KNOWN[k][0] >= 2]
    return KNOWN[max(multi or hits, key=len)]


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
