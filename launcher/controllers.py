"""Per-console controller layouts. Physical pads are read through the browser's
"standard" gamepad layout (indexes 0-15), so any modern pad maps the same way."""
from __future__ import annotations

# Standard Gamepad indexes: 0 south, 1 east, 2 west, 3 north, 4 L1, 5 R1, 6 L2, 7 R2,
# 8 select/back, 9 start, 10 L3, 11 R3, 12 up, 13 down, 14 left, 15 right, 16 home.
STANDARD_NAMES = {
    0: "Bottom face (A / Cross)", 1: "Right face (B / Circle)", 2: "Left face (X / Square)",
    3: "Top face (Y / Triangle)", 4: "Left bumper (L1)", 5: "Right bumper (R1)",
    6: "Left trigger (L2)", 7: "Right trigger (R2)", 8: "Select / Back", 9: "Start",
    10: "Left stick click", 11: "Right stick click", 12: "D-pad up", 13: "D-pad down",
    14: "D-pad left", 15: "D-pad right", 16: "Home",
}
DPAD = {"Up": 12, "Down": 13, "Left": 14, "Right": 15}

LAYOUTS: dict[str, dict] = {
    "atari": {"label": "Atari joystick", "buttons": {"Fire": 0, **DPAD}},
    "nes": {"label": "NES pad", "buttons": {"A": 1, "B": 0, "Select": 8, "Start": 9, **DPAD}},
    "snes": {"label": "SNES pad", "buttons": {"B": 0, "A": 1, "Y": 2, "X": 3, "L": 4, "R": 5, "Select": 8, "Start": 9, **DPAD}},
    "genesis": {"label": "Genesis 6-button", "buttons": {"A": 2, "B": 0, "C": 1, "X": 3, "Y": 4, "Z": 5, "Start": 9, **DPAD}},
    "gb": {"label": "Game Boy", "buttons": {"A": 1, "B": 0, "Select": 8, "Start": 9, **DPAD}},
    "gba": {"label": "Game Boy Advance", "buttons": {"A": 1, "B": 0, "L": 4, "R": 5, "Select": 8, "Start": 9, **DPAD}},
    "ps1": {"label": "PlayStation pad", "buttons": {"Cross": 0, "Circle": 1, "Square": 2, "Triangle": 3, "L1": 4, "R1": 5, "L2": 6, "R2": 7, "Select": 8, "Start": 9, "L3": 10, "R3": 11, **DPAD}},
    "ps2": {"label": "DualShock 2", "buttons": {"Cross": 0, "Circle": 1, "Square": 2, "Triangle": 3, "L1": 4, "R1": 5, "L2": 6, "R2": 7, "Select": 8, "Start": 9, "L3": 10, "R3": 11, **DPAD}},
    "ps3": {"label": "DualShock 3", "buttons": {"Cross": 0, "Circle": 1, "Square": 2, "Triangle": 3, "L1": 4, "R1": 5, "L2": 6, "R2": 7, "Select": 8, "Start": 9, "L3": 10, "R3": 11, "PS": 16, **DPAD}},
    "psp": {"label": "PSP", "buttons": {"Cross": 0, "Circle": 1, "Square": 2, "Triangle": 3, "L": 4, "R": 5, "Select": 8, "Start": 9, **DPAD}},
    "n64": {"label": "Nintendo 64", "buttons": {"A": 0, "B": 2, "Z": 6, "L": 4, "R": 5, "Start": 9, "C-Up": 3, "C-Down": 1, **DPAD}},
    "gamecube": {"label": "GameCube pad", "buttons": {"A": 0, "B": 2, "X": 1, "Y": 3, "Z": 5, "L": 6, "R": 7, "Start": 9, **DPAD}},
    "wii": {"label": "Wii (Classic Controller style)", "buttons": {"A": 0, "B": 1, "X": 2, "Y": 3, "L": 6, "R": 7, "ZL": 4, "ZR": 5, "Minus": 8, "Plus": 9, "Home": 16, **DPAD}},
    "ds": {"label": "Nintendo DS", "buttons": {"A": 1, "B": 0, "X": 3, "Y": 2, "L": 4, "R": 5, "Select": 8, "Start": 9, **DPAD}},
    "3ds": {"label": "Nintendo 3DS", "buttons": {"A": 1, "B": 0, "X": 3, "Y": 2, "L": 4, "R": 5, "ZL": 6, "ZR": 7, "Select": 8, "Start": 9, **DPAD}},
    "xbox": {"label": "Xbox controller S", "buttons": {"A": 0, "B": 1, "X": 2, "Y": 3, "Black": 4, "White": 5, "LT": 6, "RT": 7, "Back": 8, "Start": 9, "L3": 10, "R3": 11, **DPAD}},
    "x360": {"label": "Xbox 360 controller", "buttons": {"A": 0, "B": 1, "X": 2, "Y": 3, "LB": 4, "RB": 5, "LT": 6, "RT": 7, "Back": 8, "Start": 9, "L3": 10, "R3": 11, "Guide": 16, **DPAD}},
}

NOTES = {
    "n64": "N64 has no right stick: the four C buttons are usually the right stick. Here C-Up/C-Down are on face buttons so any pad works; change them to taste.",
    "gamecube": "GameCube's big A button sits where Cross/A is; B is to its left, like the real pad.",
    "genesis": "The six-button Genesis pad is spread across face buttons and bumpers.",
}


def layout(console_controller: str, override: dict | None = None) -> dict:
    base = LAYOUTS[console_controller]
    buttons = dict(base["buttons"])
    if override:
        for name, index in override.items():
            if name in buttons and isinstance(index, int) and not isinstance(index, bool) and 0 <= index <= 16:
                buttons[name] = index
    return {
        "label": base["label"],
        "buttons": [{"name": n, "index": i, "physical": STANDARD_NAMES[i]} for n, i in buttons.items()],
        "note": NOTES.get(console_controller, ""),
        "customized": bool(override),
    }


def validate_override(console_controller: str, override: dict) -> dict:
    if console_controller not in LAYOUTS:
        raise ValueError("unknown controller layout")
    known = LAYOUTS[console_controller]["buttons"]
    clean = {}
    for name, index in override.items():
        if name not in known:
            raise ValueError(f"unknown button: {name}")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 16:
            raise ValueError("button index must be a whole number 0-16")
        clean[name] = index
    return clean
