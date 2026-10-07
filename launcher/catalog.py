"""User data: favorites, settings, play history, per-console overrides.
Stored as one JSON file, written atomically. Game files are never touched."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

# Every setting carries plain-language help so the UI can explain itself.
SETTINGS_SCHEMA: dict[str, dict] = {
    "display_name": {
        "type": "text", "default": "Player", "group": "You",
        "label": "Display name",
        "help": "The name other players see in a room. It is not an account and is not checked by anyone.",
    },
    "avatar": {
        "type": "text", "default": "martin", "group": "You", "hidden": True,
        "label": "Avatar", "help": "Your little 8-bit picture. Pick it from the Account menu.",
    },
    "auto_network_test": {
        "type": "bool", "default": True, "group": "Multiplayer",
        "label": "Test my network when Legacy Player opens",
        "help": "Runs the quick network check in the background at start-up and again once you connect to a server, so Server Info already shows where you stand. It only talks to this computer and the server you chose. Turn off to test only when you press the button.",
    },
    "featured_title": {
        "type": "text", "default": "", "optional": True, "max": 60, "group": "Home page",
        "label": "Featured: title", "help": "A section on the Home page for something you want to point people at. Leave blank to hide it.",
    },
    "featured_text": {
        "type": "text", "default": "", "optional": True, "max": 240, "group": "Home page",
        "label": "Featured: text", "help": "One or two sentences shown under the title.",
    },
    "featured_link": {
        "type": "text", "default": "", "optional": True, "max": 300, "group": "Home page",
        "label": "Featured: link", "help": "An https:// address the card opens. Always labelled Featured so nobody mistakes it for part of the app.",
    },
    "setup_done": {
        "type": "bool", "default": False, "group": "You",
        "label": "First-run setup finished", "help": "Turn off to see the welcome steps again next time.",
    },
    "theme": {
        "type": "choice", "choices": ["dark", "light"], "default": "dark", "group": "Look",
        "label": "Theme", "help": "Dark is easier on the eyes in a dim room.",
    },
    "view": {
        "type": "choice", "choices": ["shelf", "list"], "default": "shelf", "group": "Look",
        "label": "Library view", "help": "Shelf shows big cards by console. List is denser and good for big libraries.",
    },
    "show_region": {
        "type": "bool", "default": True, "group": "Look",
        "label": "Show region tags", "help": "Shows tags like USA or Europe. Multiplayer needs everyone on the same region.",
    },
    "confirm_launch": {
        "type": "bool", "default": False, "group": "Playing",
        "label": "Ask before launching", "help": "Shows a confirmation with the emulator that will open.",
    },
    "encrypt_matches": {
        "type": "bool", "default": True, "group": "Multiplayer",
        "label": "Encrypt match traffic",
        "help": "Wraps RetroArch games in an encrypted tunnel with a one-time key shared through the room. Both players need this app. Turn off only on a trusted home network.",
    },
    "allow_internet": {
        "type": "bool", "default": False, "group": "Privacy",
        "label": "Allow internet downloads",
        "help": "Off means Legacy Player never downloads anything. On lets Setup and the Engines page fetch emulators from their official sites, and only when you press a Get button. Playing with friends uses only the server address you set.",
    },
    "allow_direct_connections": {
        "type": "bool", "default": False, "group": "Privacy",
        "label": "Allow direct connections (reveals your address)",
        "help": "Off (recommended): matches always go through the server relay, so other players never learn your IP address. On: lets a host choose a direct connection, which hands the host's address to every guest. Only turn on for a home network or a VPN such as Tailscale.",
    },
    "server_host": {
        "type": "text", "default": "127.0.0.1", "group": "Multiplayer",
        "label": "Server address",
        "help": "Where the multiplayer server runs. 127.0.0.1 means this computer. For a friend's server, use its address.",
    },
    "server_port": {
        "type": "int", "default": 8765, "min": 1, "max": 65535, "group": "Multiplayer",
        "label": "Server port", "help": "The network port the server listens on.",
    },
    "server_public_address": {
        "type": "text", "default": "", "group": "Your server",
        "label": "Address friends use to reach your server",
        "help": "Blank means this computer's home-network address, which works on the same network or a VPN such as Tailscale. For friends on the internet, enter your public IPv4 address and forward the server port on your router. Needed only for the short server code.",
    },
    "server_max_players": {
        "type": "int", "default": 4, "min": 2, "max": 8, "group": "Your server",
        "label": "Players per room", "help": "Applies when you start the server from this app. Rooms can choose fewer.",
    },
    "server_max_rooms": {
        "type": "int", "default": 32, "min": 1, "max": 10000, "group": "Your server",
        "label": "Rooms at once", "help": "How many rooms your server will hold. Each room is a few kilobytes.",
    },
    "server_max_waiting": {
        "type": "int", "default": 16, "min": 0, "max": 500, "group": "Your server",
        "label": "Waiting line per room", "help": "0 turns waiting lines off: a full room simply says it is full.",
    },
    "server_tls": {
        "type": "bool", "default": False, "group": "Multiplayer",
        "label": "Encrypted connection (TLS)",
        "help": "Turn on when the server was started with a certificate. Required for play over the internet.",
    },
    "server_fingerprint": {
        "type": "text", "default": "-", "group": "Multiplayer",
        "label": "Server certificate fingerprint",
        "help": "For a friend's Legacy Player server: paste the fingerprint their app shows (Play Together > server card). It proves you are talking to their server and not an impostor. Leave as - for a server with a real certificate.",
    },
    "server_tls_verify": {
        "type": "bool", "default": True, "group": "Multiplayer",
        "label": "Verify server certificate",
        "help": "Leave on for a real certificate. Turn off only for a friend's self-signed server you trust.",
    },
}

DEFAULT_DATA = {
    "version": 1,
    "settings": {},
    "roots": [],
    "favorites": [],
    "history": {},          # game id -> {"plays": n, "last_played": epoch}
    "emulator_paths": {},   # emulator id -> executable path
    "console_emulator": {}, # console id -> emulator id override
    "controller_overrides": {},  # console id -> {button: standard index}
    "save_sources": {},     # console id -> folder where the emulator writes saves
    "emulator_folders": [], # extra folders searched for emulator programs
    "alias_tag": "",        # the #1234 the server gave this player's name (never shared with another active player)
    "netcheck_last": None,  # {"at": epoch, "result": {...}} from the last network test
    "install_id": "",       # random tag so two players with the same name never collide
    "bios_found": {},       # bios kind -> list of files found by the last scan
    "last_scan": None,
    "last_rescan": None,    # when the games folders were last read
    "doctor_dismissed": [], # things the user told the doctor not to worry about
    "save_root": "",        # managed save folder root ("" = inside the data folder)
    "pad_profiles": {},     # pad key -> profile (see launcher/pads.py)
    "player_pads": {},      # "1".."4" -> pad key
}


class CatalogError(ValueError):
    pass


class Catalog:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "user_data.json"
        self.data = json.loads(json.dumps(DEFAULT_DATA))
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                self.data.update({k: v for k, v in loaded.items() if k in DEFAULT_DATA})
            except (OSError, json.JSONDecodeError):
                self.path.replace(self.path.with_suffix(".corrupt"))
        if not self.data.get("install_id"):
            import secrets
            self.data["install_id"] = secrets.token_hex(2)
            self.save()

    def player_tag(self) -> str:
        """Display name plus a 4-character tag, like a gamertag. Carries nothing about the computer."""
        return f"{self.settings()['display_name']}#{self.data.get('alias_tag') or self.data['install_id']}"

    def save(self) -> None:
        fd, tmp = tempfile.mkstemp(prefix=".ud-", dir=self.dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # settings -----------------------------------------------------------
    def settings(self) -> dict:
        return {k: self.data["settings"].get(k, spec["default"]) for k, spec in SETTINGS_SCHEMA.items()}

    def set_setting(self, key: str, value) -> None:
        spec = SETTINGS_SCHEMA.get(key)
        if spec is None:
            raise CatalogError(f"unknown setting: {key}")
        kind = spec["type"]
        if kind == "bool" and not isinstance(value, bool):
            raise CatalogError(f"{key} must be true or false")
        if kind == "int":
            if isinstance(value, bool) or not isinstance(value, int) or not spec["min"] <= value <= spec["max"]:
                raise CatalogError(f"{key} must be a whole number from {spec['min']} to {spec['max']}")
        if kind == "text":
            limit = spec.get("max", 64)
            if not isinstance(value, str) or (not value.strip() and not spec.get("optional")) or len(value) > limit:
                raise CatalogError(f"{key} must be {'0' if spec.get('optional') else '1'}-{limit} characters")
            value = value.strip()
            if key == "featured_link" and value and not value.startswith("https://"):
                raise CatalogError("the featured link must start with https://")
        if kind == "choice" and value not in spec["choices"]:
            raise CatalogError(f"{key} must be one of {spec['choices']}")
        if key == "display_name" and self.data["settings"].get("display_name") != value:
            self.data["alias_tag"] = ""      # a new name needs a new tag from the server
        self.data["settings"][key] = value
        self.save()

    # favorites / history ---------------------------------------------------
    def set_favorite(self, game_id: str, favorite: bool) -> None:
        favorites = set(self.data["favorites"])
        (favorites.add if favorite else favorites.discard)(game_id)
        self.data["favorites"] = sorted(favorites)
        self.save()

    def record_play(self, game_id: str) -> None:
        entry = self.data["history"].setdefault(game_id, {"plays": 0, "last_played": 0})
        entry["plays"] += 1
        entry["last_played"] = time.time()
        self.save()

    # roots ------------------------------------------------------------------
    def set_roots(self, roots: list[str]) -> None:
        cleaned = []
        for root in roots:
            if not isinstance(root, str) or not Path(root).is_dir():
                raise CatalogError(f"not a folder: {root}")
            cleaned.append(str(Path(root)))
        self.data["roots"] = cleaned
        self.save()

    def set_emulator_folders(self, folders: list[str]) -> None:
        cleaned = []
        for folder in folders:
            if not isinstance(folder, str) or not Path(folder).is_dir():
                raise CatalogError(f"not a folder: {folder}")
            if str(Path(folder)) not in cleaned:
                cleaned.append(str(Path(folder)))
        self.data["emulator_folders"] = cleaned
        self.save()

    def set_mapping(self, section: str, key: str, value) -> None:
        if section not in {"emulator_paths", "console_emulator", "controller_overrides", "save_sources", "pad_profiles", "player_pads"}:
            raise CatalogError("unknown section")
        if value is None:
            self.data[section].pop(key, None)
        else:
            self.data[section][key] = value
        self.save()
