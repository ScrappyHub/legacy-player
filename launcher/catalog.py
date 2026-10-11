"""User data: favorites, settings, play history, per-console overrides.
Stored as one JSON file, written atomically. Game files are never touched."""
from __future__ import annotations

import json
import threading
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
    "close_to_tray": {
        "type": "bool", "default": True, "group": "Window",
        "label": "Keep running in the tray when I close the window",
        "help": "Closing the window with X hides Legacy Player in the notification area (Windows) instead of quitting, so a server you started stays managed. Right-click its icon to open the app, start or stop your server, copy a fresh server code, or exit. Turn off to quit on X; if a server is running Legacy Player still stays in the tray so it is never stopped by surprise.",
    },
    "dolphin_manage_pads": {
        "type": "bool", "default": True, "group": "Controllers",
        "label": "Set up Dolphin's GameCube controller for me",
        "help": "When you give a player a controller (or pick a keyboard layout for player 1), Legacy Player writes it into Dolphin's GameCube pad file before Dolphin starts. The file you had is saved once as GCPadNew.ini.legacy-player-backup, and turning this off puts it back the next time Dolphin starts. Players you have not set up are left to Dolphin. Wii remotes are never touched.",
    },
    "error_reports": {
        "type": "choice", "choices": ["off", "ask", "auto"], "default": "off", "group": "Privacy",
        "labels": {"off": "Off (nothing is saved or sent)", "ask": "Ask me each time", "auto": "Send automatically"},
        "label": "Help fix problems by sending reports",
        "help": "If something breaks in Legacy Player, a short report can be sent to the people who maintain it so it gets fixed without you writing a ticket. It holds the app version, your Windows version, what failed and which action it happened in. It never holds your name, your address (IP), folder paths, game file locations, server or invite codes, or anything another player typed, and you can read the exact text first. Off sends nothing. Ask lets you read and approve each one.",
    },
    "report_url": {
        "type": "text", "default": "", "optional": True, "max": 200, "group": "Privacy",
        "label": "Send reports to (advanced)", "help": "Leave blank to use the address built into Legacy Player. It must start with https://.",
    },
    "report_prompt_seen": {
        "type": "bool", "default": False, "group": "Privacy", "hidden": True,
        "label": "Asked about reports", "help": "Remembers that the one-time question about problem reports was answered.",
    },
    "auto_network_test": {
        "type": "bool", "default": True, "group": "Multiplayer",
        "label": "Test my network when Legacy Player opens",
        "help": "Runs the quick network check in the background at start-up and again once you connect to a server, so Server Info already shows where you stand. It only talks to this computer and the server you chose. Turn off to test only when you press the button.",
    },
    "featured_title": {
        "type": "text", "default": "My GitHub", "optional": True, "max": 60, "group": "Home page",
        "label": "Featured: title", "help": "A section on the Home page for something you want to point people at. Leave blank to hide it.",
    },
    "featured_text": {
        "type": "text", "default": "Source code, releases and the rest of my projects.", "optional": True, "max": 240, "group": "Home page",
        "label": "Featured: text", "help": "One or two sentences shown under the title.",
    },
    "featured_link": {
        "type": "text", "default": "https://github.com/Alpallyoop", "optional": True, "max": 300, "group": "Home page",
        "label": "Featured: link", "help": "An https:// address the card opens. Always labelled Featured so nobody mistakes it for part of the app.",
    },
    "setup_done": {
        "type": "bool", "default": False, "group": "You",
        "label": "First-run setup finished", "help": "Turn off to see the welcome steps again next time.",
    },
    "theme": {
        "type": "choice", "choices": ["dark", "light", "ocean", "forest", "sunset", "rose", "violet", "crimson", "graphite",
                                      "meadow", "harbor", "ember", "frost", "dunes", "glimmer", "neon", "cloudtop"], "default": "dark", "group": "Look",
        "label": "Theme", "help": "The colours of the background and buttons. The Legacy Player World themes are eight places (a meadow village, a harbour, volcanic peaks, a snowy village, desert dunes, a glowing mushroom wood, an arcade city and sky islands), each with its own day and night colours and a pixel scene behind the app.",
    },
    "time_of_day": {
        "type": "choice", "choices": ["auto", "day", "night"], "default": "auto", "group": "Look", "hidden": True,
        "labels": {"auto": "Follow my clock", "day": "Always day", "night": "Always night"},
        "label": "Day or night (World themes)", "help": "Follow my clock shows day from 7 in the morning to 7 in the evening on this computer's clock. Picked next to the themes.",
    },
    "background": {
        "type": "choice", "choices": ["scene", "waves", "aurora", "grid", "stars", "dots", "crt", "bokeh", "bitworld", "bitcity", "bitforest", "plain"], "default": "waves", "group": "Look",
        "label": "Background", "help": "The picture behind the app. World scene is the pixel picture of your World theme's place, by day or night. Waves drift slowly, Aurora glows, Grid is the retro one, Stars twinkle, Dots is calm, CRT is an old television, Bokeh is soft drifting lights, 1-bit World is a tiny pixel world with Martin and the clinic, Plain is flat (the easiest on a slow computer). It uses your theme's colours.",
    },
    "view": {
        "type": "choice", "choices": ["shelf", "list"], "default": "shelf", "group": "Look", "labels": {"shelf": "Shelf (big cards)", "list": "List (compact)"},
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
    "allow_game_info": {
        "type": "bool", "default": False, "group": "Privacy",
        "label": "Look up game details online (Wikipedia)",
        "help": "Separate from downloads. When on, a game's card can ask en.wikipedia.org and www.wikidata.org for its description, release date, makers and player count. Only that game's name and console are sent, and only when you press Look it up. Off: cards show what the file name says and what you type.",
    },
    "allow_direct_connections": {
        "type": "bool", "default": False, "group": "Privacy",
        "label": "Allow direct connections (reveals your address)",
        "help": "Off (recommended): matches always go through the server relay, so other players never learn your IP address. On: Legacy Player first tries to connect computer to computer (the server only introduces you, and carries no game traffic), which is faster and gives the other player your address. If your routers do not allow it, the relay is used automatically.",
    },
    "show_pc_games": {
        "type": "bool", "default": True, "group": "Library",
        "label": "Show my installed Steam and Epic games in the library",
        "help": "Reads the list of installed games that Steam and the Epic Games Launcher keep on this computer (names only; nothing is sent anywhere) and starts them through those launchers.",
    },
    "steam_folder": {
        "type": "text", "default": "", "optional": True, "max": 260, "group": "Library",
        "label": "Steam folder (only if it is not found by itself)",
        "help": "Normally empty: Legacy Player finds Steam through Windows. If your Steam games do not show, paste the folder that holds steam.exe here (for example D:\\Steam).",
    },
    "show_steam_games": {
        "type": "bool", "default": True, "group": "Library",
        "label": "Include Steam games", "help": "Needs the setting above. Turn off to leave Steam out while keeping Epic games.",
    },
    "show_epic_games": {
        "type": "bool", "default": True, "group": "Library",
        "label": "Include Epic games", "help": "Needs the setting above. Turn off to leave Epic out while keeping Steam games.",
    },
    "use_private_link": {
        "type": "bool", "default": False, "group": "Privacy",
        "label": "Use an encrypted private link for Dolphin when everyone has Tailscale",
        "help": "Dolphin online play is not encrypted by itself. With this on, and Tailscale (a separate free service, tailscale.com) installed and signed in, Legacy Player tells the room your private Tailscale address (never your home address) and, when the host picks Automatic, plays over it if every player has done the same and can be reached. Otherwise it falls back to the normal connection.",
    },
    "friends_server": {
        "type": "text", "default": "", "optional": True, "max": 200, "group": "Friends",
        "label": "Friends link (optional)",
        "help": "A separate, optional service for friend codes, seeing who is online, room invites and short messages. Legacy Player works fully without it. Paste the friends link someone shares with you (it starts with https://), or run your own from the Friends page with one click. No account is made: your app gets a friend code to give out, nothing more.",
    },
    "friends_host_port": {
        "type": "int", "default": 8791, "min": 1024, "max": 65535, "group": "Friends",
        "label": "Port for the friends service you run",
        "help": "Only used when you run a friends service on this computer (Friends > Run my own). Legacy Player opens it on your router by itself, like your server's port.",
    },
    "friends_requests_open": {
        "type": "bool", "default": True, "group": "Friends",
        "label": "Let people send me friend requests",
        "help": "Someone needs your friend code to ask, and only friends can ever message or invite you. Turn off to stop new requests entirely; you can still add other people's codes yourself.",
    },
    "friends_filter": {
        "type": "bool", "default": True, "group": "Friends",
        "label": "Filter bad language in messages and names",
        "help": "Hides common swear words (and the words you add below) with asterisks in messages, names and invites from other players. Only changes what you see.",
    },
    "friends_filter_words": {
        "type": "text", "default": "", "optional": True, "max": 2000, "group": "Friends",
        "label": "Extra words to filter",
        "help": "Your own words to hide too, separated by commas. Disguises like l33t letters and s p a c e s are caught.",
    },
    "friends_share_room": {
        "type": "bool", "default": True, "group": "Friends",
        "label": "Let friends see the room I am in and join it",
        "help": "While you host or sit in a room, friends see its name and can join with one click (your room's invite code and the server code travel to friends only, never to anyone else). Off: friends only see that you are online.",
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
        "help": "Leave blank: the app finds your public address itself when it opens the router. Only fill this in if you forward the port yourself or use a VPN address. A host name (like home.example.org) or an IPv6 address works too; the code is then a longer LP2- one.",
    },
    "minimize_on_launch": {
        "type": "bool", "default": True, "group": "Playing",
        "label": "Minimise Legacy Player while a game runs",
        "help": "When you start a game from Legacy Player, the app steps aside and comes back when the game closes.",
    },
    "server_autostart": {
        "type": "bool", "default": True, "group": "Your server",
        "label": "Start my server by itself when I host or join",
        "help": "If your own server is not running when you host a room or look for rooms, Legacy Player starts it for you.",
    },
    "mp_auto_agree": {
        "type": "bool", "default": False, "group": "Multiplayer",
        "label": "Join the games a host picks without asking each time",
        "help": "When the host of a room you are in starts a game you already have, you agree automatically and it opens. Off by default: otherwise you are asked every time.",
    },
    "server_auto_open": {
        "type": "bool", "default": True, "group": "Your server",
        "label": "Open my router for friends automatically",
        "help": "When you let friends connect, ask your home router (UPnP) to forward the server port, and close it again when the server stops. Turn off if you set up the router yourself.",
    },
    "server_use_fallback": {
        "type": "bool", "default": True, "group": "Your server",
        "label": "Use a shared server when mine can't be reached",
        "help": "If your internet connection can't be reached from outside (a phone hotspot, or a provider that shares addresses), meet friends on a shared relay server instead. Game traffic stays encrypted between players.",
    },
    "fallback_server_code": {
        "type": "text", "default": "", "group": "Your server", "optional": True, "max": 60,
        "label": "Shared server code (optional)",
        "help": "A server code for the shared server to fall back to. Blank uses the one built into Legacy Player, if there is one.",
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
    "server_remote_port": {
        "type": "int", "default": 8765, "min": 1, "max": 65535, "group": "Multiplayer", "hidden": True,
        "label": "Friend's server port", "help": "Set for you when you connect with a server code.",
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
    "server_access_key": {
        "type": "text", "default": "", "optional": True, "max": 20, "group": "Multiplayer", "hidden": True,
        "label": "Server access key", "help": "Comes from the server code you connect with. Set for you; not something to type.",
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
    "netcheck_good": None,  # the last time the server answered: {"at", "avg_ms", "name"}
    "backup_root": "",      # where whole-library save backups are kept ("" = inside the data folder)
    "game_meta": {},        # game id -> {"title", "hidden", "emulator", "args", "note"} the player chose for that one game
    "collections": {},      # collection name -> [game ids], like Steam categories
    "video": {},            # "all" or console id -> display choices (see launcher/app.py VIDEO_FIELDS)
    "router_mapped": {},   # {"port", "location"} while the app has a port open on the router, so a crash can be cleaned up later
    "overlay": {"enabled": True, "hotkey": "ctrl+shift+l", "pad": ["back", "start"], "hold": 0.8},   # the in-game overlay and how to open it
    "display_prefs": {"modes": {}, "monitor": ""},   # emulator id -> "ask"|"fullscreen"|"windowed"; monitor "" = automatic, else "1","2",...
    "play_prefs": {},       # emulator id -> {"res": "1920x1080" or "", "borderless": bool} from the Play options box
    "last_rescan": None,    # when the games folders were last read
    "doctor_dismissed": [], # things the user told the doctor not to worry about
    "save_root": "",        # managed save folder root ("" = inside the data folder)
    "pad_profiles": {},     # pad key -> profile (see launcher/pads.py)
    "player_pads": {},      # "1".."4" -> pad key
    "keyboard": {"layout": "default", "keys": {}},   # player 1 keyboard controls (see launcher/keyboard.py)
    "privacy_ok": {},       # privacy item id -> the setting value the player said yes to (see launcher/privacy.py)
    "friends": {},          # this app's identity on the friends service: {"server", "id", "secret", "code"}; empty until hello
}


def dedupe_paths(paths) -> list[str]:
    """The same folder written twice (different capitals, a trailing slash) is one folder, in the order first given."""
    seen, out = set(), []
    for p in paths:
        if not isinstance(p, str):
            continue
        key = p.strip().replace("/", "\\").rstrip("\\").lower()
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return out


class CatalogError(ValueError):
    pass


class Catalog:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "user_data.json"
        self.data = json.loads(json.dumps(DEFAULT_DATA))
        self._lock = threading.RLock()
        self.read_only = ""                       # set when the settings file exists but could not be read: never save over it
        if self.path.exists():
            text = None
            for attempt in range(6):              # antivirus, OneDrive or a backup tool can hold the file for a moment
                try:
                    text = self.path.read_text(encoding="utf-8")
                    break
                except UnicodeDecodeError:
                    text = b"\xff"               # bad encoding: treated as damaged below
                    break
                except OSError as exc:
                    if attempt == 5:
                        self.read_only = f"Could not read your settings file ({exc}). Nothing will be saved until Legacy Player is restarted."
                    else:
                        time.sleep(0.25)
            if text is not None:
                try:
                    if isinstance(text, bytes):
                        raise ValueError("bad text encoding")
                    loaded = json.loads(text)
                    if not isinstance(loaded, dict):
                        raise ValueError("the settings file is not a settings object")
                    # keep only values of the same kind as the defaults, so a damaged file can not put text where a list belongs
                    self.data.update({k: v for k, v in loaded.items()
                                      if k in DEFAULT_DATA and (DEFAULT_DATA[k] is None or isinstance(v, type(DEFAULT_DATA[k])))})
                except ValueError:                    # really damaged (bad JSON or encoding): keep it aside, start fresh
                    try:
                        self.path.replace(self.path.with_name("user_data." + time.strftime("%Y%m%d-%H%M%S") + ".corrupt"))
                    except OSError:
                        self.read_only = "Your settings file is damaged and could not be set aside, so it was left as it is."
        if self.data.get("settings", {}).get("featured_link") == "https://github.com/ScrappyHub":
            self.data["settings"]["featured_link"] = "https://github.com/Alpallyoop"      # the account was renamed
        for key in ("roots", "emulator_folders"):
            if isinstance(self.data.get(key), list):
                self.data[key] = dedupe_paths(self.data[key])
        if not self.data.get("install_id"):
            import secrets
            self.data["install_id"] = secrets.token_hex(2)
            self.save()

    def player_tag(self) -> str:
        """Display name plus a 4-character tag, like a gamertag. Carries nothing about the computer."""
        return f"{self.settings()['display_name']}#{self.data.get('alias_tag') or self.data['install_id']}"

    def save(self) -> None:
        if self.read_only:                         # never overwrite a settings file we could not read
            return
        with self._lock:
            fd, tmp = tempfile.mkstemp(prefix=".ud-", dir=self.dir)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(self.data, stream, indent=2, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                for attempt in range(5):                       # Windows refuses the swap for a moment if a scanner has the file open
                    try:
                        os.replace(tmp, self.path)
                        break
                    except PermissionError:
                        if attempt == 4:
                            raise
                        time.sleep(0.05)
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

    META_LIMITS = {"title": 80, "emulator": 40, "args": 200, "note": 400, "players": 1,
                   # the game card: what the player typed or looked up about one game
                   "description": 1200, "release": 24, "version": 40, "developer": 80, "publisher": 80, "genre": 60,
                   "hidden_by": 12}

    def set_game_meta(self, game_id: str, **fields) -> dict:
        """Per-game choices (name, hidden, emulator, launch options, note). An empty value clears the choice."""
        meta = dict(self.data["game_meta"].get(game_id, {}))
        for key, value in fields.items():
            if key == "hidden":
                if value:
                    meta["hidden"] = True
                else:
                    meta.pop("hidden", None)
            elif key in self.META_LIMITS:
                text = str(value or "").strip()
                if any(ch in text for ch in "\r\n\x00"):
                    raise CatalogError("That text cannot contain line breaks.")
                if len(text) > self.META_LIMITS[key]:
                    raise CatalogError(f"Keep it under {self.META_LIMITS[key]} characters.")
                if text:
                    meta[key] = text
                else:
                    meta.pop(key, None)
        if meta:
            self.data["game_meta"][game_id] = meta
        else:
            self.data["game_meta"].pop(game_id, None)
        self.save()
        return meta

    def collection_op(self, action: str, name: str, game_id: str | None = None) -> None:
        name = str(name or "").strip()
        if not name or len(name) > 40 or any(ch in name for ch in "\r\n\x00"):
            raise CatalogError("Give the collection a short name (up to 40 characters).")
        cols = self.data["collections"]
        key = next((k for k in cols if k.lower() == name.lower()), None)
        if action == "create":
            if key is None:
                if len(cols) >= 50:
                    raise CatalogError("That is plenty of collections already (50).")
                cols[name] = []
        elif key is None:
            raise CatalogError("That collection does not exist.")
        elif action == "delete":
            del cols[key]
        elif action in {"add", "remove"} and game_id:
            ids = set(cols[key])
            (ids.add if action == "add" else ids.discard)(game_id)
            cols[key] = sorted(ids)
        else:
            raise CatalogError("Unknown collection action.")
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
        self.data["roots"] = dedupe_paths(cleaned)
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
