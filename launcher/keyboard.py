"""Keyboard controls for player 1 (RetroArch). A layout maps each RetroPad button to one key."""
from __future__ import annotations

ROLES = [("up", "D-pad up"), ("down", "D-pad down"), ("left", "D-pad left"), ("right", "D-pad right"),
         ("a", "A (right button)"), ("b", "B (bottom button)"), ("x", "X (top button)"), ("y", "Y (left button)"),
         ("l", "L (left shoulder)"), ("r", "R (right shoulder)"), ("start", "Start"), ("select", "Select")]
ROLE_IDS = [r for r, _ in ROLES]

PRESETS = {
    "default": {"label": "Classic (arrow keys)", "note": "RetroArch's own keys: arrows move, Z/X/A/S are the buttons, Enter is Start.",
                "keys": {"up": "up", "down": "down", "left": "left", "right": "right", "a": "x", "b": "z", "x": "s", "y": "a",
                         "l": "q", "r": "w", "start": "enter", "select": "rshift"}},
    "wasd": {"label": "WASD", "note": "Left hand moves with W A S D, right hand presses J K L I. Q and E are the shoulders.",
             "keys": {"up": "w", "down": "s", "left": "a", "right": "d", "a": "l", "b": "k", "x": "i", "y": "j",
                      "l": "q", "r": "e", "start": "enter", "select": "tab"}},
}
VALID_KEYS = (set("abcdefghijklmnopqrstuvwxyz") | {f"num{i}" for i in range(10)} |
              {"up", "down", "left", "right", "enter", "space", "backspace", "tab", "shift", "rshift", "ctrl", "rctrl", "alt", "ralt"})


def resolved(cfg: dict | None) -> dict:
    cfg = cfg or {}
    layout = cfg.get("layout", "default")
    keys = dict(PRESETS["default"]["keys"])
    if layout in PRESETS:
        keys = dict(PRESETS[layout]["keys"])
    elif layout == "custom":
        keys.update({k: v for k, v in (cfg.get("keys") or {}).items() if k in ROLE_IDS and v in VALID_KEYS})
    return keys


def validate(body: dict) -> dict:
    layout = str(body.get("layout", "default"))
    if layout in PRESETS:
        return {"layout": layout, "keys": {}}
    if layout != "custom":
        raise ValueError("Unknown keyboard layout.")
    keys = {}
    for role, key in (body.get("keys") or {}).items():
        if role not in ROLE_IDS:
            raise ValueError("Unknown button.")
        if key not in VALID_KEYS:
            raise ValueError("That key can't be used (Escape and the F keys are kept for the emulator).")
        keys[role] = key
    full = dict(PRESETS["default"]["keys"]); full.update(keys)
    if len(set(full.values())) != len(full):
        raise ValueError("Two buttons use the same key. Give each button its own key.")
    return {"layout": "custom", "keys": full}


def retroarch_lines(cfg: dict | None) -> list[str]:
    """Only written for a non-default layout, so RetroArch's own defaults stay untouched otherwise."""
    if not cfg or cfg.get("layout", "default") == "default":
        return []
    return [f'input_player1_{role} = "{key}"' for role, key in resolved(cfg).items()]
