"""Physical controller profiles ("pads").

Two layers keep this simple for any controller:
  1. A pad profile maps what *this* physical pad sends (raw button N, or an axis moved a
     direction) to one of 17 standard controls (south face button, shoulder, d-pad...).
  2. A console layout (controllers.py) maps standard controls to a console's buttons.

Browsers already present most pads (Xbox, PlayStation, Switch Pro, 8BitDo...) in the
standard layout, so mapping is only needed for odd pads or to rebind a button.
"""
from __future__ import annotations

import re

from .controllers import STANDARD_NAMES

MAX_PLAYERS = 4
MAX_RAW_INDEX = 63

# RetroPad role for each standard control. Triggers (6, 7) are axes in XInput, so they are
# left to RetroArch's own autoconfig.
RETROPAD_ROLE = {0: "b", 1: "a", 2: "y", 3: "x", 4: "l", 5: "r", 6: "l2", 7: "r2", 8: "select",
                 9: "start", 10: "l3", 11: "r3", 12: "up", 13: "down", 14: "left", 15: "right"}
# Standard button index -> bit in XInput's wButtons mask (XINPUT_GAMEPAD_*). Used for Dolphin's XInput names.
XINPUT_BIT = {0: 12, 1: 13, 2: 14, 3: 15, 4: 8, 5: 9, 8: 5, 9: 4, 10: 6, 11: 7, 12: 0, 13: 1, 14: 2, 15: 3}
# Standard button index -> the button number RetroArch's xinput joypad driver uses. That driver numbers buttons by
# its button_index_to_bitmap_code table: A, B, X, Y, LB, RB, START, BACK, L3, R3, GUIDE (input/drivers_joypad/
# xinput_joypad.c), and reads the d-pad as hat 0 ("h0up"...). Its own XInput autoconfig uses the same numbers.
RETROARCH_XINPUT_BUTTON = {0: "0", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 9: "6", 8: "7", 10: "8", 11: "9", 16: "10",
                           12: "h0up", 13: "h0down", 14: "h0left", 15: "h0right"}
MAX_DEVICE_INDEX = 15


def pad_key(pad_id: str) -> str:
    key = re.sub(r"\s+", " ", str(pad_id)).strip().lower()
    if not key or len(key) > 160:
        raise ValueError("unknown controller id")
    return key


def parse_vendor_product(pad_id: str) -> tuple[str | None, str | None]:
    match = re.search(r"vendor:\s*([0-9a-f]{4})\s+product:\s*([0-9a-f]{4})", pad_id, re.I) \
        or re.match(r"([0-9a-f]{4})-([0-9a-f]{4})-", pad_id, re.I)
    return (match.group(1).lower(), match.group(2).lower()) if match else (None, None)


def _binding(raw) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("a binding must be an object")
    index = raw.get("i")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= MAX_RAW_INDEX:
        raise ValueError("binding index must be a whole number")
    if raw.get("t") == "b":
        return {"t": "b", "i": index}
    if raw.get("t") == "a" and raw.get("d") in (-1, 1):
        return {"t": "a", "i": index, "d": raw["d"]}
    raise ValueError("a binding must be a button or an axis direction")


def validate_profile(pad_id: str, body: dict) -> dict:
    key = pad_key(pad_id)
    bindings = {}
    for slot, raw in (body.get("bindings") or {}).items():
        if not str(slot).isdigit() or int(slot) not in STANDARD_NAMES:
            raise ValueError(f"unknown standard control: {slot}")
        bindings[str(int(slot))] = _binding(raw)
    if len({(b["t"], b["i"], b.get("d")) for b in bindings.values()}) != len(bindings):
        raise ValueError("two controls use the same physical input")
    name = str(body.get("name") or "Controller").strip()[:80] or "Controller"
    vendor, product = parse_vendor_product(str(pad_id))
    profile = {"key": key, "name": name, "standard": bool(body.get("standard")),
               "vendor": vendor, "product": product, "bindings": bindings}
    index = body.get("index")
    if index is not None:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= MAX_DEVICE_INDEX:
            raise ValueError("controller index must be a whole number from 0 to 15")
        profile["index"] = index
    return profile


def with_device_index(profile: dict, index) -> dict:
    """A copy of the profile that remembers which connected controller it is (the slot the browser/XInput reports),
    or the profile unchanged when the index is not a sensible number."""
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= MAX_DEVICE_INDEX:
        return profile
    return {**profile, "index": index}


def device_index(profile: dict | None, player: int) -> int:
    """Which connected controller drives this player: the index stored with the assigned pad, or (for profiles saved
    before the index was recorded) the player's own position."""
    index = (profile or {}).get("index")
    if isinstance(index, int) and not isinstance(index, bool) and 0 <= index <= MAX_DEVICE_INDEX:
        return index
    return player - 1


def translate(profile: dict | None, slot: int) -> dict | None:
    """The physical input that triggers a standard control for this pad."""
    if profile and str(slot) in profile["bindings"]:
        return profile["bindings"][str(slot)]
    if profile and any(b["t"] == "b" and b["i"] == slot for b in profile["bindings"].values()):
        return None  # that physical button was given to another control
    return {"t": "b", "i": slot}


def retroarch_pad_config(profile: dict, player: int) -> tuple[list[str], list[str]]:
    """RetroArch config lines for an XInput-style pad. Returns (lines, notes)."""
    lines, notes = [], []
    if not profile.get("standard"):
        return lines, ["This pad is not in the standard layout, so RetroArch's own auto-detection is left in charge."]
    lines.append(f'input_player{player}_joypad_index = "{device_index(profile, player)}"')
    for slot, role in RETROPAD_ROLE.items():
        if slot in (6, 7):                       # triggers are axes in XInput
            continue
        binding = translate(profile, slot)
        if binding is None:
            continue
        if binding["t"] != "b" or binding["i"] not in RETROARCH_XINPUT_BUTTON:
            notes.append(f"{STANDARD_NAMES[slot]} uses an axis or trigger, so RetroArch's own setting is kept.")
            continue
        lines.append(f'input_player{player}_{role}_btn = "{RETROARCH_XINPUT_BUTTON[binding["i"]]}"')
    return lines, notes
