"""The Legacy Player World themes: eight places, each with a day and a night look. The colours and the pixel scenes live
in the page (launcher/ui/index.html, BIOMES); this file only knows their names and whether it is day, so the parts of
the app outside the page (the tray menu) can follow along."""
from __future__ import annotations

import time

BIOMES = {
    "meadow": "Martin's Meadow", "harbor": "Pixel Harbor", "ember": "Ember Peaks", "frost": "Frostfall",
    "dunes": "Mirage Dunes", "glimmer": "Glimmerwood", "neon": "Neon Arcade", "cloudtop": "Cloudtop Isles",
}
DAY_START, DAY_END = 7 * 60, 19 * 60            # "Follow my clock": day from 07:00 to 19:00 local time
TIMES = ("auto", "day", "night")


def time_now(choice: str, now: float | None = None) -> str:
    """'day' or 'night' for a time-of-day setting ('auto' reads this computer's clock)."""
    if choice in ("day", "night"):
        return choice
    t = time.localtime(now if now is not None else time.time())
    minutes = t.tm_hour * 60 + t.tm_min
    return "day" if DAY_START <= minutes < DAY_END else "night"


def looks_light(settings: dict, now: float | None = None) -> bool:
    """Is the app light right now? The Light theme always is; a World theme is light by day and dark by night."""
    theme = settings.get("theme")
    if theme == "light":
        return True
    return theme in BIOMES and time_now(settings.get("time_of_day", "auto"), now) == "day"
