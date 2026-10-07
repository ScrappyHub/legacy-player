"""Application logic behind the local UI. Independent of HTTP so it can be tested directly."""
from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import random
import re
import shlex
import shutil
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

from adapters.retroarch import (
    CORES, EXPERIMENTAL, NETPLAY_NOTES, NetplayError, build_guest_command, build_host_command, build_solo_command, detect_lan_address, find_core,
)

from adapters.dolphin.netplay_guide import (
    DEFAULT_PORT as DOLPHIN_PORT, SUPPORTED_CONSOLES as DOLPHIN_CONSOLES, DolphinNetplayError,
    build_open_command as dolphin_open_command, steps as dolphin_steps,
)

from adapters.retroarch import tunnel as netplay_tunnel

from . import overlay as overlaymod
from . import procs
from . import controllers, emulators, engines, pads, savefolders, saves
from .installer import EngineInstaller, InstallError, latest_release, pick_asset
from . import dolphinpads, firewall, gameinfo, portmap, winplace, keyboard, memprobe, netcheck, reports, selfuninstall, sysinfo
from .covers import (CONTENT_TYPES, CoverFetcher, SYSTEMS as COVER_SYSTEMS, clear_custom_cover, cover_path,
                     custom_cover, set_custom_cover)
from .pcscan import PcScan
from .version import PUBLIC_SERVER_CODE, REPO, VERSION
from .setup import Setup, SetupError
from .catalog import SETTINGS_SCHEMA, Catalog, CatalogError
from .consoles import BY_ID, CONSOLES
from .lobby_client import LobbyClient, LobbyClientError
from .scanner import DEFAULT_EXCLUDES, scan

ZIP_OK = {"nes", "snes", "gb", "gbc", "gba", "genesis", "atari"}

# Consoles whose usual emulator has no netplay at all: say so plainly instead of "not yet".
NO_NETPLAY = {
    "ps2": "PCSX2 has no netplay and no deterministic core, so PlayStation 2 cannot be played together. Kaillera-style forks are unmaintained.",
    "psp": "PSP games with multiplayer use PPSSPP's ad hoc mode (Settings > Networking, built-in PRO ad hoc server on the host). It is direct player-to-player; the app's relay cannot carry it.",
    "xbox": "xemu has no netplay. System Link works only on one home network.",
    "x360": "Xenia has no netplay.",
    "ps3": "RPCS3 has no netplay. Some games' online modes work through RPCN, RPCS3's own service; follow the steps below.",
    "3ds": "Legacy Player cannot start 3DS matches itself. Azahar has its own multiplayer rooms; follow the steps below (they show your address to the others, so a VPN is safer).",
    "gamecube": "GameCube uses Dolphin NetPlay (guided).", "wii": "Wii uses Dolphin NetPlay (guided).",
}


NETPLAY_STEPS = {
    "psp": [
        "Everyone: open PPSSPP, then Settings > Networking and turn on Enable networking / WLAN.",
        "Each player needs a different MAC address: Settings > Networking > Change Mac Address, press Randomize on every computer.",
        "Host: turn on Enable built-in PRO ad hoc server. Then tell the others this computer's address, ideally a VPN address such as Tailscale, because PPSSPP ad hoc is direct and shows addresses.",
        "Guests: Settings > Networking > Change PRO ad hoc server IP address, and type the host's address.",
        "Everyone: start the same game, choose its Ad hoc / Wireless / Local multiplayer menu, and join each other from there.",
    ],
    "3ds": [
        "Everyone: use Azahar 2120 or newer, and the same game file.",
        "Host: Multiplayer > Create Room, pick the game, choose a port, and send guests the room address (shows your address; a VPN is safer).",
        "Guests: Multiplayer > Direct Connect to Room, type the host's address, then start the same game.",
    ],
    "ps3": [
        "Everyone: RPCS3 > Configuration > Network: set Network status to Connected and PSN status to RPCN.",
        "Create an RPCN account once (Configuration > Network > Configure RPCN), then start a game that has online play and use its own online menu.",
    ],
}


GITHUB_HOSTS_SHOWN = {"api.github.com", "github.com", "objects.githubusercontent.com"}


class AppError(ValueError):
    """An error whose message is safe and useful to show the user."""


EVENT_TEXT = {
    "participant_joined": "{participant_id} joined the room.",
    "participant_left": "{participant_id} left the room.",
    "participant_kicked": "{participant_id} was removed by the host ({reason}).",
    "participant_disconnected": "{participant_id} lost connection.",
    "participant_reconnected": "{participant_id} is back.",
    "join_requested": "{participant_id} wants to join. Approve or deny below.",
    "join_denied": "You denied {participant_id}.",
    "session_resumed": "The server restarted. Everyone needs to press Ready again.",
    "endpoint_published": "The host has launched. Press Join match.",
    "waitlist_joined": "{participant_id} is waiting for a spot (number {position} in line).",
    "waitlist_priority": "{participant_id}'s place in line was changed by the host.",
    "waitlist_dropped": "{participant_id} stopped waiting.",
    "slot_opened": "A spot opened. {waiting} waiting; the next in line will be let in.",
    "capacity_changed": "The room now holds up to {max_players} players.",
    "server_stopping": "The server is shutting down. Your room is saved and will return when it restarts.",
    "session_created": "Room created.",
    "invite_created": "A new invite code was made.",
    "invites_revoked": "All invite codes were cancelled.",
    "start_requested": "The host wants to start {title}. Say yes below and it opens for you.",
    "start_consented": "{participant_id} agreed to start.",
    "game_changed": "The host picked a different game: {title}. Check you have it.",
}


def describe_event(event: dict) -> dict:
    template = EVENT_TEXT.get(event["kind"], event["kind"])
    try:
        text = template.format(**event["data"])
    except (KeyError, IndexError):
        text = template
    warn = event["kind"] in {"participant_kicked", "participant_disconnected", "server_stopping", "join_requested"}
    return {"seq": event["seq"], "kind": event["kind"], "text": text, "level": "warn" if warn else "info",
            "at": event["at_utc"], "who": event["data"].get("participant_id")}


# Display choices. Each is None (use the default), True or False. `how` says what Legacy Player can enforce.
VIDEO_FIELDS = {
    "fullscreen": {"label": "Start full screen", "help": "RetroArch is told through its config; other emulators get their full-screen start-up flag where they have one."},
    "integer": {"label": "Sharp pixels (whole-number scaling)", "help": "RetroArch only. Keeps pixel art crisp by scaling in whole steps, with black bars if needed."},
    "keep_shape": {"label": "Keep the game's own screen shape", "help": "RetroArch only. Off stretches the picture over the whole screen."},
    "smooth": {"label": "Smooth the picture (filter)", "help": "RetroArch only. Off gives hard pixels, on blurs them slightly."},
    "vsync": {"label": "Wait for the screen refresh (vsync)", "help": "RetroArch only. Stops tearing; can add a tiny delay."},
}
VIDEO_DEFAULTS = {"fullscreen": False, "integer": False, "keep_shape": True, "smooth": False, "vsync": True}


class LauncherApp:
    def __init__(self, data_dir: Path, roots: list[str] | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.catalog = Catalog(self.data_dir)
        if roots:
            self.catalog.set_roots(roots)
        self.games: dict[str, dict] = {}
        self.skipped = {"unrecognized": 0, "duplicates": 0}
        self.room: dict | None = None
        self.waits: dict[str, dict] = {}   # rooms you are queued for while doing something else
        self._overlay_launched = 0.0
        self.overlay_opener = None            # set by the web server: opens the browser-window overlay (fallback)
        self.overlay_native = None            # set by the web server: the real overlay panel
        self.show_main_window = None          # set by the web server: bring the app window forward
        self.overlay_listeners = None         # global shortcut + controller watcher
        self.running: dict | None = None   # the game started from the library, if any
        self.tunnel = None
        self.last_ping = 0.0
        self.bye_at = 0.0
        self.quit_requested = False
        self.quit_at = 0.0
        self._specs_lock = threading.Lock()
        self.api_lock = threading.RLock()        # one ordinary API call at a time (the web layer takes it)
        self.memprobe = memprobe.MemProbe(self.data_dir)
        self.port_map: dict = {}
        self.fallback_active = False
        if self.catalog.data.get("router_mapped") and not os.environ.get("LEGACY_PLAYER_NO_BACKGROUND"):
            threading.Thread(target=self._tidy_old_router_mapping, daemon=True, name="router-tidy").start()
        self.reports = reports.ReportCenter(self.data_dir, lambda: self.catalog.settings(), lambda k, v: self.catalog.set_setting(k, v), self._report_context)
        self._scan_lock = threading.Lock()       # one disk walk at a time (rescan)
        self._server_op_lock = threading.Lock()  # starting/stopping the server: one at a time, outside api_lock
        self.tray_mode = False   # the window is closed but the app keeps running in the tray
        self._net_running = False
        self.covers = CoverFetcher(self.data_dir / "covers")
        self.setup = Setup(self.data_dir, self._retroarch_path,
                           lambda path: self.catalog.set_mapping("emulator_paths", "retroarch", path))
        self.installer = EngineInstaller(self.data_dir / "emulators")
        self.pcscan = PcScan({k: v["exes"] for k, v in emulators.EMULATORS.items()},
                             lambda: [Path(r) for r in self.catalog.data["roots"]] + [Path(f) for f in self.catalog.data.get("emulator_folders", [])],
                             matcher=emulators.program_for, archive_matcher=emulators.archive_for)
        self._prepare_certificate()
        self._load_cache()
        if not self.games and self.catalog.data["roots"]:
            self.rescan()

    # library ------------------------------------------------------------
    def _cache_path(self) -> Path:
        return self.data_dir / "library_cache.json"

    def _load_cache(self) -> None:
        try:
            cached = json.loads(self._cache_path().read_text(encoding="utf-8"))
            self.games = {g["id"]: g for g in cached["games"]}
            self.skipped = cached["skipped"]
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    def rescan(self, body: dict | None = None) -> dict:
        """Read the games folders again. The slow part (walking the disk) runs without the big lock, so the app stays
        responsive; only swapping the result in takes it."""
        roots = [Path(r) for r in self.catalog.data["roots"]]
        if not roots:
            raise AppError("Add a games folder first (Library folders).")
        started = time.time()
        with self._scan_lock:                     # one disk walk at a time
            result = scan(roots, DEFAULT_EXCLUDES)
            with self.api_lock:
                self.games = {g.id: g.as_dict() for g in result["games"]}
                self.skipped = result["skipped"]
                self.catalog.data["last_rescan"] = time.time()
                self.catalog.save()
                self._cache_path().write_text(json.dumps({"games": list(self.games.values()), "skipped": self.skipped}), encoding="utf-8")
                return {"games": len(self.games), "skipped": self.skipped, "seconds": round(time.time() - started, 2)}

    def api_roots(self, body: dict) -> dict:
        if "roots" in body:
            try:
                self.catalog.set_roots(body["roots"])
            except CatalogError as exc:
                raise AppError(str(exc)) from exc
        return {"roots": self.catalog.data["roots"], "excluded_folders": list(DEFAULT_EXCLUDES)}

    def api_open_url(self, body: dict) -> dict:
        """Open the Featured card's link in the computer's own browser. Only that one address, and only https."""
        import webbrowser
        url = str(body.get("url") or "").strip()
        if not url.startswith("https://") or url != str(self.catalog.settings().get("featured_link") or "").strip():
            raise AppError("Only the Featured link from Settings can be opened from here.")
        webbrowser.open(url)
        return {"opened": True}

    def api_rescan(self, body: dict) -> dict:
        return self.rescan(body)

    def _public(self, game: dict, emus: dict | None = None) -> dict:
        history = self.catalog.data["history"].get(game["id"], {})
        emus = emus if emus is not None else getattr(self, "_emus_cache", {})
        meta = self.catalog.data["game_meta"].get(game["id"], {})
        own = custom_cover(self.covers.cache, game["id"])
        auto = cover_path(self.covers.cache, game["id"])
        shown = own or (auto if auto.exists() else None)
        emulator = emulators.EMULATORS[meta["emulator"]]["name"] if meta.get("emulator") in emulators.EMULATORS else emus.get(game["console"])
        return {
            "emulator": emulator, "cover": shown is not None, "custom_cover": own is not None,
            "cover_v": int(shown.stat().st_mtime) if shown else 0,
            "hidden": bool(meta.get("hidden")), "own_title": bool(meta.get("title")), "own_emulator": meta.get("emulator", ""),
            "args": meta.get("args", ""), "note": meta.get("note", ""),
            "players": gameinfo.players_for(game["console"], meta.get("title") or game["title"], meta.get("players", "")),
            "own_players": meta.get("players", ""),
            "collections": [n for n, ids in self.catalog.data["collections"].items() if game["id"] in ids],
            "original_title": game["title"],
            "id": game["id"], "title": meta.get("title") or game["title"], "console": game["console"], "region": game["region"],
            "tags": game["tags"], "size_mb": round(game["size"] / 1048576, 1),
            "favorite": game["id"] in self.catalog.data["favorites"],
            "plays": history.get("plays", 0), "last_played": history.get("last_played", 0),
            "is_archive": game["is_archive"], "extension": game["extension"],
        }

    def api_library(self, body: dict) -> dict:
        query = str(body.get("q", "")).strip().lower()
        console = body.get("console")
        favorites_only = bool(body.get("favorites"))
        favorites = set(self.catalog.data["favorites"])
        metas = self.catalog.data["game_meta"]
        cols = self.catalog.data["collections"]
        collection = body.get("collection")
        in_collection = set(cols.get(collection, [])) if collection else None
        show_hidden = bool(body.get("hidden"))
        hidden_total = sum(1 for i in self.games if metas.get(i, {}).get("hidden"))
        counts: dict[str, int] = {}
        selected = []
        for game in self.games.values():
            if bool(metas.get(game["id"], {}).get("hidden")) != show_hidden:
                continue
            counts[game["console"]] = counts.get(game["console"], 0) + 1
            if console and game["console"] != console:
                continue
            if favorites_only and game["id"] not in favorites:
                continue
            if in_collection is not None and game["id"] not in in_collection:
                continue
            name = (metas.get(game["id"], {}).get("title") or game["title"]).lower()
            if query and query not in name:
                continue
            selected.append(game)
        sort = body.get("sort", "title")
        if sort == "recent":
            history = self.catalog.data["history"]
            selected.sort(key=lambda g: -history.get(g["id"], {}).get("last_played", 0))
        elif sort == "size":
            selected.sort(key=lambda g: -g["size"])
        else:
            selected.sort(key=lambda g: (g["console"] and BY_ID[g["console"]].order, g["sort_title"]))
        consoles = [
            {"id": c.id, "name": c.name, "maker": c.maker, "count": counts.get(c.id, 0),
             "netplay": c.netplay, "netplay_note": c.netplay_note}
            for c in CONSOLES if counts.get(c.id)
        ]
        self._emus_cache = emus = self._console_emulators()
        return {
            "consoles": consoles, "total": sum(counts.values()), "shown": len(selected),
            "hidden_total": hidden_total, "showing_hidden": show_hidden,
            "collections": [{"name": n, "count": len(set(ids) & set(self.games))} for n, ids in sorted(cols.items(), key=lambda kv: kv[0].lower())],
            "favorites_total": len(favorites & set(self.games)),
            "games": [self._public(g) for g in selected[:1000]],
            "truncated": len(selected) > 1000, "skipped": self.skipped,
            "roots": self.catalog.data["roots"],
        }

    def api_favorite(self, body: dict) -> dict:
        game = self._game(body)
        self.catalog.set_favorite(game["id"], bool(body.get("favorite", True)))
        return {"favorite": game["id"] in self.catalog.data["favorites"]}

    def _game(self, body: dict) -> dict:
        game = self.games.get(body.get("id"))
        if game is None:
            raise AppError("That game is no longer in the library. Try Rescan.")
        return game

    # emulators / launching --------------------------------------------------
    def _search_roots(self) -> list[Path]:
        roots = []
        for root in self.catalog.data["roots"]:
            roots.append(Path(root))
            if (Path(root) / "Emulators").is_dir():
                roots.append(Path(root) / "Emulators")
        roots += [Path(folder) for folder in self.catalog.data.get("emulator_folders", []) if Path(folder).is_dir()]
        if (self.data_dir / "emulators").is_dir():
            roots.append(self.data_dir / "emulators")
        return roots

    def _core_ok(self, console_id: str, exe: str) -> bool:
        """RetroArch is only useful for a console once a core for it is installed."""
        if console_id not in CORES:
            return False
        try:
            find_core(exe, console_id)
            return True
        except NetplayError:
            return False

    def _emulator_for(self, console_id: str, found: dict | None = None, prefer: str | None = None):
        found = found or emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        preferred = self.catalog.data["console_emulator"].get(console_id)
        order = ([prefer] if prefer else []) + ([preferred] if preferred else []) + list(BY_ID[console_id].emulators)
        for emulator_id in order:
            if emulator_id in found and found[emulator_id]["path"]:
                if emulator_id == "retroarch" and not self._core_ok(console_id, found[emulator_id]["path"]):
                    continue    # installed, but with nothing to run this console yet: try the next emulator
                return emulator_id, found[emulator_id]
        return None, None

    def _console_emulators(self) -> dict[str, str | None]:
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        return {c.id: (self._emulator_for(c.id, found)[1] or {}).get("name") for c in CONSOLES}

    def _meta(self, game: dict) -> dict:
        return self.catalog.data["game_meta"].get(game["id"], {})

    def _user_args(self, game: dict) -> list[str]:
        """Launch options the player typed for this one game (like Steam's launch options), split into arguments."""
        text = self._meta(game).get("args", "")
        if not text:
            return []
        try:
            return [t.strip('"') for t in shlex.split(text, posix=False)]
        except ValueError as exc:
            raise AppError("The launch options for this game have a quote that is not closed.") from exc

    def launch_check(self, game: dict) -> dict:
        emulator_id, info = self._emulator_for(game["console"], prefer=self._meta(game).get("emulator"))
        if game["is_archive"] and not (game["console"] in ZIP_OK and game["extension"] == ".zip"):
            return {"ready": False, "reason": f"This game is a {game['extension']} archive. Extract it first; the launcher never changes your files."}
        if emulator_id is None:
            names = ", ".join(emulators.EMULATORS[e]["name"] for e in BY_ID[game["console"]].emulators if e in emulators.EMULATORS)
            ra = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"]).get("retroarch", {}).get("path")
            if ra and game["console"] in CORES:
                return {"ready": False, "reason": f"RetroArch is installed but has no core for {BY_ID[game['console']].name} yet. Open Setup and press Install missing cores, or add another emulator for it ({names})."}
            return {"ready": False, "reason": f"No emulator set for {BY_ID[game['console']].name}. Supported: {names}. Set its path in Emulators."}
        return {"ready": True, "emulator": info["name"], "emulator_id": emulator_id, "reason": ""}

    def _save_dir(self, game: dict) -> str | None:
        """Configured save folder, else (cartridge consoles) the game's own folder,
        where emulators such as mGBA write .sav files by default."""
        console = BY_ID[game["console"]]
        configured = self.catalog.data["save_sources"].get(console.id)
        if configured:
            return configured
        if console.id in CORES and self._emulator_for(console.id)[0] == "retroarch":
            return str(savefolders.console_dir(self._save_root(), console.id))
        if console.save_style == "cartridge":
            return str(Path(game["path"]).parent)
        return None

    def _save_root(self) -> Path:
        configured = self.catalog.data.get("save_root")
        return Path(configured) if configured else savefolders.default_root(self.data_dir)

    def _prepare_dolphin(self, exe: str, console_id: str) -> list[str]:
        """Write the player's GameCube pad choices into Dolphin before it starts. Returns notes; never stops a launch."""
        if console_id != "gamecube":
            return []
        if not self.catalog.settings()["dolphin_manage_pads"]:
            dolphinpads.restore(exe)          # switched off: give the player's own file back
            return []
        out = dolphinpads.apply(exe, self.catalog.data["player_pads"], self.catalog.data["pad_profiles"], self.catalog.data.get("keyboard"))
        return out.get("notes", [])

    # problem reports (opt in) -------------------------------------------------------------------------------
    def _report_context(self) -> dict:
        """Extra facts for a report. Never an address, a name or a path."""
        last = (self.catalog.data.get("netcheck_last") or {}).get("result") or {}
        s = self.catalog.settings()
        net = {"address_kind": last.get("address_kind"), "server_is_local": last.get("server_is_local"),
               "server_uses_tls": bool(s.get("server_tls")), "direct_connections_allowed": bool(s.get("allow_direct_connections"))}
        room = self.room or {}
        doing = {"playing": bool(self._running_now()), "emulator": (self.running or {}).get("emulator"),
                 "in_room": bool(room), "room_role": room.get("role"), "console": room.get("console")}
        return {"network": net, "doing": doing, "_roots": list(self.catalog.data.get("roots", []))}

    def api_report_status(self, body: dict) -> dict:
        out = self.reports.status()
        out["prompt"] = self.reports.prompt() if body.get("prompt") else None
        return out

    def api_report_preview(self, body: dict) -> dict:
        report = self.reports.get(str(body.get("id", "")))
        if report is None:
            raise AppError("That report is no longer here.")
        return {"report": report, "text": json.dumps(report, indent=2)}

    def api_report_list(self, body: dict) -> dict:
        items = self.reports.pending() + ([self.reports.held] if self.reports.held else [])
        return {"reports": [{"id": r["id"], "kind": r["kind"], "created": r["created"], "message": r["error"]["message"][:160],
                             "occurrences": r.get("occurrences", 1)} for r in items], **self.reports.status()}

    def api_report_decide(self, body: dict) -> dict:
        try:
            return self.reports.decide(str(body.get("id", "")), str(body.get("choice", "")))
        except ValueError as exc:
            raise AppError("Unknown choice.") from exc

    def api_report_send_all(self, body: dict) -> dict:
        if self.reports.mode() == "off":
            raise AppError("Problem reports are off. Turn them on in Settings > Privacy first.")
        return self.reports.send_all()

    def api_report_clear(self, body: dict) -> dict:
        return {"removed": self.reports.discard(None)}

    def api_report_client_error(self, body: dict) -> dict:
        """A problem the window itself ran into (the page threw while drawing). Only text; rate limited and cleaned."""
        message = str(body.get("message") or "")[:400]
        report = self.reports.capture("page-error", None, message, {"page": str(body.get("page") or "")[:30], "where": str(body.get("where") or "")[:40],
                                                                   "stack": str(body.get("stack") or "")[:1500]})
        return {"captured": report is not None}

    # Dolphin memory probe (Tools menu) --------------------------------------------------------------------
    def _probe(self, fn, *args) -> dict:
        try:
            return fn(*args)
        except memprobe.ProbeError as exc:
            raise AppError(str(exc)) from exc
        except OSError as exc:
            raise AppError(f"The probe could not read Dolphin's memory: {exc}") from exc

    def api_probe_status(self, body: dict) -> dict:
        return self.memprobe.status()

    def api_probe_baseline(self, body: dict) -> dict:
        if not body.get("consent"):
            raise AppError("Please confirm: the probe will read memory from your open Dolphin program (read-only, on this computer).")
        return self._probe(self.memprobe.baseline, str(body.get("label") or ""))

    def api_probe_capture(self, body: dict) -> dict:
        return self._probe(self.memprobe.capture)

    def api_probe_forget(self, body: dict) -> dict:
        return self._probe(self.memprobe.forget, str(body.get("label") or ""))

    def api_probe_cancel(self, body: dict) -> dict:
        return self.memprobe.cancel()

    def api_dolphin_pads(self, body: dict) -> dict:
        """What Legacy Player would write into Dolphin's GameCube pad file, or put the player's own file back."""
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        exe = found.get("dolphin", {}).get("path")
        if not exe:
            raise AppError("Dolphin is not set up yet.")
        if body.get("restore"):
            return dolphinpads.restore(exe)
        text, notes = dolphinpads.build(self.catalog.data["player_pads"], self.catalog.data["pad_profiles"], self.catalog.data.get("keyboard"))
        user = dolphinpads.find_user_dir(exe)
        return {"will_write": bool(text), "notes": notes, "settings_folder": str(user) if user else None,
                "enabled": self.catalog.settings()["dolphin_manage_pads"]}

    def _retroarch_extra(self, console_id: str, exe: str, netplay: bool = False, fullscreen: bool | None = None) -> list[str]:
        """Extra RetroArch arguments: managed save folders and any custom pad bindings."""
        lines: list[str] = ["netplay_public_announce = \"false\""] if netplay else []  # private rooms stay private
        for player in range(1, pads.MAX_PLAYERS + 1):
            key = self.catalog.data["player_pads"].get(str(player))
            profile = self.catalog.data["pad_profiles"].get(key) if key else None
            if profile:
                lines += pads.retroarch_pad_config(profile, player)[0]
        lines += keyboard.retroarch_lines(self.catalog.data.get("keyboard"))
        v = self._video_for(console_id)
        if fullscreen is not None:
            v["fullscreen"] = fullscreen
        lines += [f'video_fullscreen = "{str(v["fullscreen"]).lower()}"', f'video_scale_integer = "{str(v["integer"]).lower()}"',
                  f'video_force_aspect = "{str(v["keep_shape"]).lower()}"', f'video_smooth = "{str(v["smooth"]).lower()}"',
                  f'video_vsync = "{str(v["vsync"]).lower()}"']
        try:
            cfg = savefolders.retroarch_append_config(self.data_dir, self._save_root(), console_id, exe, lines)
        except (OSError, ValueError) as exc:
            raise AppError(f"Could not prepare the save folders: {exc}") from exc
        return ["--appendconfig", str(cfg)]

    def netplay_check(self, game: dict) -> dict:
        """Can this game be launched into emulator-native netplay (RetroArch)?"""
        if game["console"] in DOLPHIN_CONSOLES:
            found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
            exe = found.get("dolphin", {}).get("path")
            if not exe:
                return {"ready": False, "engine": "dolphin", "reason": "Dolphin is not set up. Set its path in Emulators or use Setup."}
            if game["is_archive"]:
                return {"ready": False, "engine": "dolphin", "reason": f"Extract this {game['extension']} archive first."}
            return {"ready": True, "engine": "dolphin", "reason": "", "exe": exe}
        if game["console"] not in CORES:
            return {"ready": False, "reason": NO_NETPLAY.get(game["console"], f"{BY_ID[game['console']].name} has no netplay launcher yet."),
                    "steps": NETPLAY_STEPS.get(game["console"], [])}
        if game["is_archive"] and not (game["extension"] == ".zip"):
            return {"ready": False, "reason": f"Extract this {game['extension']} archive first."}
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        exe = found.get("retroarch", {}).get("path")
        if not exe:
            return {"ready": False, "reason": "RetroArch is not set up. Set its path in Emulators."}
        try:
            core = find_core(exe, game["console"])
        except NetplayError as exc:
            return {"ready": False, "reason": str(exc)}
        return {"ready": True, "engine": "retroarch", "reason": "", "exe": exe, "core": core,
                "experimental": game["console"] in EXPERIMENTAL, "note": NETPLAY_NOTES.get(game["console"], "")}

    def _retroarch_path(self) -> str | None:
        found = emulators.find_emulators(self._search_roots() + [self.setup.install_root], self.catalog.data["emulator_paths"])
        return found.get("retroarch", {}).get("path")

    def api_setup_status(self, body: dict) -> dict:
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        return self.setup.check(found.get("dolphin", {}).get("path"))

    def _internet_ok(self, body: dict) -> None:
        if not self.catalog.settings()["allow_internet"]:
            raise AppError("Internet downloads are off. Turn on 'Allow internet downloads' in Settings first.")
        if not body.get("confirm"):
            raise AppError("Please confirm the download.")

    def api_setup_install(self, body: dict) -> dict:
        self._internet_ok(body)
        try:
            return {"job": self.setup.start(str(body.get("what", "all")))}
        except SetupError as exc:
            raise AppError(str(exc)) from exc

    def api_game(self, body: dict) -> dict:
        game = self._game(body)
        console = BY_ID[game["console"]]
        save_dir = self._save_dir(game)
        save_files = []
        if save_dir:
            save_files = [str(p.name) for p in saves.find_save_files(Path(save_dir), Path(game["path"]).stem)]
        return {
            **self._public(game), "path": game["path"],
            "console_name": console.name, "netplay": console.netplay, "netplay_note": console.netplay_note,
            "launch": self.launch_check(game), "compat_id": game["compat_id"],
            "netplay_launch": {k: v for k, v in self.netplay_check(game).items() if k in {"ready", "reason", "experimental", "note"}},
            "controller": controllers.layout(console.controller, self.catalog.data["controller_overrides"].get(console.id)),
            "save_style": console.save_style, "save_source": save_dir, "save_files": save_files,
            "backups": saves.list_backups(self.data_dir, console.id, game["compat_id"]),
            "emulator_choices": self._emulator_choices(console.id),
        }

    def _emulator_choices(self, console_id: str) -> list[dict]:
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        return [{"id": e, "name": emulators.EMULATORS[e]["name"], "installed": bool(found.get(e, {}).get("path"))}
                for e in BY_ID[console_id].emulators if e in emulators.EMULATORS]

    # where games open: full screen or a window, and on which monitor ------------------------------------------
    def _display_prefs(self) -> dict:
        prefs = self.catalog.data.setdefault("display_prefs", {"modes": {}, "monitor": ""})
        prefs.setdefault("modes", {})
        prefs.setdefault("monitor", "")
        return prefs

    def _monitor_for(self, key: str) -> dict | None:
        key = str(key or "")
        return next((m for m in winplace.list_monitors() if str(m["index"]) == key), None) if key else None

    def _display_choice(self, eid: str, console: str, body: dict) -> tuple[str | None, str, bool]:
        """(mode, monitor key, must_ask). `display` in the request is the player's answer to the question."""
        prefs = self._display_prefs()
        chosen = body.get("display")
        if isinstance(chosen, dict) and chosen.get("mode") in ("fullscreen", "windowed"):
            monitor = str(chosen.get("monitor") or "")
            if chosen.get("remember"):
                prefs["modes"][eid] = chosen["mode"]
                prefs["monitor"] = monitor
                self.catalog.save()
            return chosen["mode"], monitor, False
        stored = prefs["modes"].get(eid)
        if stored in ("fullscreen", "windowed"):
            return stored, prefs["monitor"], False
        if body.get("interactive") and stored in (None, "ask"):
            return None, prefs["monitor"], True
        return ("fullscreen" if self._video_for(console)["fullscreen"] else "windowed"), prefs["monitor"], False

    def _note_running(self, pid: int, title: str, emulator: str, eid: str) -> None:
        self.running = {"pid": pid, "title": title, "emulator": emulator, "emulator_id": eid, "started": procs.start_time(pid),
                        "since": time.time()}
        if self.catalog.settings().get("minimize_on_launch", True) and not os.environ.get("LEGACY_PLAYER_NO_BACKGROUND"):
            threading.Thread(target=self._step_aside_for, args=(pid, self.running["started"]), daemon=True, name="step-aside").start()

    def _step_aside_for(self, pid: int, started) -> None:
        """Legacy Player gets out of the way while a game runs and comes back when it ends (Xbox / Steam style)."""
        time.sleep(1.5)                                    # let the game's own window appear first
        hidden = winplace.minimize_titled(winplace.APP_TITLE_MARK)
        while procs.is_alive(pid, started):
            time.sleep(1.0)
        other = self._running_now()
        if hidden and not self.quit_requested and not (other and other.get("pid") != pid):   # not while another game is still going
            winplace.restore_titled(winplace.APP_TITLE_MARK)

    def _running_now(self) -> dict | None:
        """The game started from here, but only if it is still running (a closed game, or a reused process number, clears it)."""
        r = self.running
        if r and r.get("pid") and not procs.is_alive(r["pid"], r.get("started")):
            self.running = r = None
        return r

    def _bring_forward(self, pid: int, eid: str, mode: str | None = None, monitor_key: str | None = None, explicit: bool = False) -> None:
        """Once the game's window exists: in front of Legacy Player, on the chosen monitor, full screen or windowed."""
        prefs = self._display_prefs()
        mode = mode or prefs["modes"].get(eid)
        mode = mode if mode in ("fullscreen", "windowed") else "windowed"
        key = prefs["monitor"] if monitor_key is None else monitor_key
        has_flag = eid == "retroarch" or bool(emulators.EMULATORS.get(eid, {}).get("fullscreen"))
        winplace.arrange_async(pid, self._monitor_for(key), mode, has_flag, explicit=explicit)

    def api_monitors(self, body: dict) -> dict:
        return {"monitors": winplace.list_monitors()}

    def api_display_prefs(self, body: dict) -> dict:
        prefs = self._display_prefs()
        if "emulator" in body:
            eid, mode = body["emulator"], body.get("mode")
            if eid not in emulators.EMULATORS or mode not in ("ask", "fullscreen", "windowed"):
                raise AppError("Unknown emulator or choice.")
            prefs["modes"][eid] = mode
        if "monitor" in body:
            key = str(body["monitor"] or "")
            if key and self._monitor_for(key) is None:
                raise AppError("That monitor is not connected right now.")
            prefs["monitor"] = key
        self.catalog.save()
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        return {"monitor": prefs["monitor"], "monitors": winplace.list_monitors(),
                "emulators": [{"id": k, "name": v["name"], "mode": prefs["modes"].get(k, "ask"),
                               "flag": emulators.fullscreen_status(k)} for k, v in found.items() if v["path"]]}

    def api_launch(self, body: dict) -> dict:
        game = self._game(body)
        check = self.launch_check(game)
        if not check["ready"]:
            raise AppError(check["reason"])
        eid = check["emulator_id"]
        mode, monitor, must_ask = self._display_choice(eid, game["console"], body)
        if must_ask:
            return {"needs_display": {"emulator": check["emulator"], "emulator_id": eid, "title": game["title"], "monitor": monitor,
                                      "monitors": winplace.list_monitors(), "flag": emulators.fullscreen_status(eid)}}
        fullscreen = mode == "fullscreen"
        _, info = self._emulator_for(game["console"], prefer=self._meta(game).get("emulator"))
        try:
            if eid == "retroarch":
                if game["console"] not in CORES:
                    raise AppError("RetroArch has no core set up for this console.")
                core = find_core(info["path"], game["console"])
                command = build_solo_command(info["path"], core, game["path"],
                                             self._retroarch_extra(game["console"], info["path"], fullscreen=fullscreen) + self._user_args(game))
                pid = emulators.launch_command(command)
            else:
                if eid == "dolphin":
                    self._prepare_dolphin(info["path"], game["console"])
                pid = emulators.launch(eid, info["path"], game["path"], emulators.video_args(eid, fullscreen) + self._user_args(game))
        except NetplayError as exc:
            raise AppError(str(exc)) from exc
        except (OSError, FileNotFoundError) as exc:
            self.reports.capture("launch-failed", exc, context={"emulator": check.get("emulator_id"), "console": game["console"], "extension": game.get("extension")})
            raise AppError(f"Could not start {check['emulator']}: {exc}") from exc
        self._bring_forward(pid, eid, mode, monitor)
        self.catalog.record_play(game["id"])
        self._note_running(pid, game["title"], check["emulator"], eid)
        return {"launched": game["title"], "emulator": check["emulator"], "pid": pid}

    def api_emulators(self, body: dict) -> dict:
        if "folder" in body:
            folders = list(self.catalog.data.get("emulator_folders", []))
            folder = str(body["folder"] or "").strip().strip('"')
            if body.get("remove"):
                folders = [f for f in folders if f != folder]
            elif folder and folder not in folders:
                folders.append(folder)
            try:
                self.catalog.set_emulator_folders(folders)
            except CatalogError as exc:
                raise AppError(f"I can't find that folder: {exc}") from exc
        if "emulator" in body:
            emulator_id, path = body["emulator"], body.get("path")
            if emulator_id not in emulators.EMULATORS:
                raise AppError("Unknown emulator.")
            if path is not None and not Path(path).is_file():
                raise AppError("That file does not exist. Paste the full path to the emulator program.")
            self.catalog.set_mapping("emulator_paths", emulator_id, path or None)
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        return {
            "folders": self.catalog.data.get("emulator_folders", []),
            "emulators": [{"id": k, **v} for k, v in found.items()],
            "consoles": [
                {"id": c.id, "name": c.name, "emulator": (self._emulator_for(c.id, found)[1] or {}).get("name"),
                 "chosen": self.catalog.data["console_emulator"].get(c.id),
                 "options": [{"id": e, "name": emulators.EMULATORS[e]["name"], "installed": bool(found.get(e, {}).get("path"))}
                             for e in c.emulators if e in emulators.EMULATORS]}
                for c in CONSOLES
            ],
        }

    def api_network_check(self, body: dict) -> dict:
        """Measure whether this computer and connection are ready to host or join. Touches only this
        computer and the server you already chose."""
        s = self.catalog.settings()
        address = detect_lan_address()
        local = s["server_host"] in {"127.0.0.1", "localhost", "::1"}
        mock = netcheck.loopback_test()
        room = netcheck.room_load_test()
        def probe() -> None:
            try:
                self._client().call({"operation": "status", "session_id": "probe", "participant_id": "probe", "credential": "probe"})
            except LobbyClientError as exc:
                if "unknown session" not in str(exc):
                    raise
        server = netcheck.ping_server(probe)
        kind = netcheck.classify_address(address)
        result = self._netcheck_result(address, kind, mock, room, server, local, s)
        if server.get("ok"):
            self.catalog.data["netcheck_good"] = {"at": time.time(), "avg_ms": server["avg_ms"], "name": result["server_name"]}
        result["last_good"] = self.catalog.data.get("netcheck_good")
        self.catalog.data["netcheck_last"] = {"at": time.time(), "result": result}
        self.catalog.save()
        return {**result, "at": self.catalog.data["netcheck_last"]["at"]}

    def api_network_start(self, body: dict) -> dict:
        """Run the network test in the background so the app stays responsive; read it with network_last."""
        if not self._net_running:
            self._net_running = True

            def work() -> None:
                try:
                    self.api_network_check({})
                except Exception:      # a failed test just leaves the old result
                    pass
                finally:
                    self._net_running = False

            threading.Thread(target=work, daemon=True).start()
        return {"running": True}

    def api_network_last(self, body: dict) -> dict:
        """What the last test found, without testing again. `running` is true while a test is in progress."""
        last = self.catalog.data.get("netcheck_last")
        base = {**last["result"], "at": last["at"]} if last else {"at": None}
        return {**base, "running": self._net_running}

    def _netcheck_result(self, address, kind, mock, room, server, local, s) -> dict:
        return {"address": address, "address_kind": kind["kind"], "address_text": kind["text"], "mock": mock, "room_load": room,
                "server": server, "server_is_local": local, "server_name": "this computer" if local else s["server_host"],
                "advice": netcheck.advise(kind["kind"], mock, room, server, local)}

    def api_scan_pc(self, body: dict) -> dict:
        """Look through this computer for emulator programs. Starts only on an explicit request."""
        action = body.get("action", "status")
        if action == "start":
            if not body.get("consent"):
                raise AppError("Say yes first: the scan lists folder and file names on this computer. It does not open, change or send anything.")
            self.pcscan.start()
        elif action == "cancel":
            self.pcscan.cancel()
        view = self.pcscan.view()
        have = {eid: v["path"] for eid, v in emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"]).items()}
        view["emulators"] = {eid: {"name": emulators.EMULATORS[eid]["name"], "paths": paths, "in_use": have.get(eid)}
                             for eid, paths in view["found"].items()}
        view["packages"] = {eid: {"name": emulators.EMULATORS[eid]["name"], "paths": paths}
                            for eid, paths in view.get("archives", {}).items() if eid not in view["found"] and not have.get(eid)}
        return view

    def api_scan_apply(self, body: dict) -> dict:
        """After a scan: use the first match for every emulator that has none yet, and look for BIOS files
        next to what was found. Never overrides a program you chose yourself."""
        view = self.pcscan.view()
        chosen = {}
        for eid, paths in view["found"].items():
            if paths and not self.catalog.data["emulator_paths"].get(eid) \
                    and not emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])[eid]["path"]:
                self.catalog.set_mapping("emulator_paths", eid, paths[0])
                chosen[eid] = paths[0]
        extra = [Path(p).parent for p in self.catalog.data["emulator_paths"].values() if p]
        self.catalog.data["bios_found"] = {kind: engines.find_bios(kind, self._search_roots(), extra) for kind in engines.BIOS}
        self.catalog.data["last_scan"] = time.time()
        self.catalog.save()
        return {"applied": chosen, "found": {eid: len(v) for eid, v in view["found"].items()}}

    def api_console_emulator(self, body: dict) -> dict:
        """Choose which emulator a console opens with (None = automatic)."""
        console, emulator = body.get("console"), body.get("emulator")
        if console not in BY_ID:
            raise AppError("Unknown console.")
        if emulator is not None and emulator not in BY_ID[console].emulators:
            raise AppError("That emulator does not run this console.")
        self.catalog.set_mapping("console_emulator", console, emulator or None)
        return self.api_emulators({})

    # engines (the owned shell's view of emulators) -----------------------------------
    def _engines_payload(self) -> dict:
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        rows = []
        for engine_id, spec in engines.ENGINES.items():
            info = found.get(engine_id, {})
            rows.append({
                "id": engine_id, "name": spec["name"], "consoles": spec["consoles"], "license": spec["license"],
                "path": info.get("path"), "source": info.get("source"), "official": spec["source"],
                "can_download": spec["source"]["kind"] == "github", "bios": spec.get("bios"),
            })
        bios = []
        for kind, spec in engines.BIOS.items():
            cached = self.catalog.data.get("bios_found", {}).get(kind, [])
            bios.append({"kind": kind, "name": spec["name"], "for": spec["for"], "how": spec["how"], "found": cached})
        consoles = []
        for c in CONSOLES:
            eid, info = self._emulator_for(c.id, found)
            consoles.append({"id": c.id, "name": c.name, "ready": bool(eid), "via": info["name"] if info else None})
        return {"engines": rows, "bios": bios, "consoles": consoles, "allow_internet": self.catalog.settings()["allow_internet"],
                "install_folder": str(self.data_dir / "emulators"), "job": self.installer.snapshot(),
                "last_scan": self.catalog.data.get("last_scan")}

    def api_engines(self, body: dict) -> dict:
        return self._engines_payload()

    # display and video -----------------------------------------------------------
    def _video_for(self, console_id: str) -> dict:
        data = self.catalog.data.get("video", {})
        out = dict(VIDEO_DEFAULTS)
        for scope in ("all", console_id):
            for k, v in (data.get(scope) or {}).items():
                if k in VIDEO_FIELDS and isinstance(v, bool):
                    out[k] = v
        return out

    def api_video(self, body: dict) -> dict:
        """Display choices for every console. scope is 'all' or a console id; value null clears a console's own choice."""
        if "key" in body:
            scope, key, value = body.get("scope", "all"), body.get("key"), body.get("value")
            if scope != "all" and scope not in BY_ID:
                raise AppError("Unknown console.")
            if key not in VIDEO_FIELDS or (value is not None and not isinstance(value, bool)):
                raise AppError("Unknown display setting.")
            if value is None and scope == "all":
                raise AppError("The defaults always have a value.")
            store = self.catalog.data.setdefault("video", {}).setdefault(scope, {})
            if value is None:
                store.pop(key, None)
            else:
                store[key] = value
            self.catalog.save()
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        rows = []
        for c in CONSOLES:
            eid, info = self._emulator_for(c.id, found)
            own = self.catalog.data.get("video", {}).get(c.id) or {}
            if eid == "retroarch":
                how = "RetroArch: every display choice is applied each time Legacy Player opens a game."
            elif eid and emulators.EMULATORS[eid].get("fullscreen"):
                how = f"{info['name']}: only 'start full screen' can be applied. Everything else is set inside {info['name']} once (Graphics settings)."
                if emulators.fullscreen_status(eid) == "unconfirmed":
                    how += f" The start-up flag is a best guess for some {info['name']} versions; if it does not go full screen, press F11 or Alt+Enter once inside it."
            elif eid:
                how = f"{info['name']}: has no start-up option for this. Set the display inside {info['name']} once; it remembers."
            else:
                how = "No emulator for this console yet."
            applies = list(VIDEO_FIELDS) if eid == "retroarch" else (["fullscreen"] if eid and emulators.EMULATORS[eid].get("fullscreen") else [])
            rows.append({"id": c.id, "name": c.name, "emulator": info["name"] if info else None, "how": how, "own": own, "applies": applies,
                         "effective": self._video_for(c.id), "pad_layout_customized": c.id in self.catalog.data["controller_overrides"]})
        return {"fields": VIDEO_FIELDS, "defaults": self.catalog.data.get("video", {}).get("all") or {}, "base": VIDEO_DEFAULTS, "consoles": rows}

    # cover art ---------------------------------------------------------------------
    def api_covers(self, body: dict) -> dict:
        action = body.get("action", "status")
        if action == "start":
            if not self.catalog.settings()["allow_internet"]:
                raise AppError("Internet access is off. Turn on 'Allow internet downloads' in Settings first.")
            if not body.get("consent"):
                raise AppError("Please confirm: game names are sent to thumbnails.libretro.com to ask for their box art.")
            self.covers.start([g for g in self.games.values()])
        elif action == "cancel":
            self.covers.cancel()
        return self.covers.view()

    def cover_file(self, game_id: str):
        """The picture to show for a game: one the player picked, else the downloaded box art. Returns (path, content type)."""
        own = custom_cover(self.covers.cache, game_id)
        if own is not None:
            return own, CONTENT_TYPES.get(own.suffix.lstrip("."), "image/png")
        p = cover_path(self.covers.cache, game_id)
        return (p, "image/png") if p.is_file() else None

    def api_game_meta(self, body: dict) -> dict:
        """Per-game choices: name, hidden, emulator, launch options, note."""
        game = self._game(body)
        fields = {k: body[k] for k in ("title", "hidden", "emulator", "args", "note", "players") if k in body}
        if fields.get("emulator") and fields["emulator"] not in emulators.EMULATORS:
            raise AppError("That emulator is not one Legacy Player knows.")
        try:
            self.catalog.set_game_meta(game["id"], **fields)
        except CatalogError as exc:
            raise AppError(str(exc)) from exc
        return self._public(game)

    def api_game_cover(self, body: dict) -> dict:
        """Set or remove the picture shown for one game. The page shrinks the picture first and sends it as base64."""
        game = self._game(body)
        if body.get("action") == "remove":
            clear_custom_cover(self.covers.cache, game["id"])
        else:
            try:
                data = base64.b64decode(str(body.get("data", "")), validate=True)
                set_custom_cover(self.covers.cache, game["id"], data)
            except (ValueError, TypeError) as exc:
                raise AppError(str(exc) if "picture" in str(exc) else "That picture could not be read.") from exc
        return self._public(game)

    def api_game_fetch_cover(self, body: dict) -> dict:
        game = self._game(body)
        if not self.catalog.settings()["allow_internet"]:
            raise AppError("Internet access is off. Turn on 'Allow internet downloads' in Settings first.")
        if not body.get("consent"):
            raise AppError("Please confirm: this game's name is sent to thumbnails.libretro.com to ask for its box art.")
        if game["console"] not in COVER_SYSTEMS:
            raise AppError("There is no box art library for this console.")
        self.covers.start([game], force=True)
        return self.covers.view()

    def api_game_files(self, body: dict) -> dict:
        """Show the game's file or its save folder in the computer's file manager (this app runs on the same computer)."""
        game = self._game(body)
        what = body.get("what", "game")
        if what == "saves":
            target = self._save_dir(game)
            if not target or not Path(target).is_dir():
                raise AppError("This game has no save folder yet. Play it once, or set one on the Saves page.")
            target, select = Path(target), False
        else:
            target, select = Path(game["path"]), True
            if not target.exists():
                raise AppError("That file is no longer there. Try Rescan.")
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", f"/select,{target}"] if select else ["explorer", str(target)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(target)] if select else ["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target.parent if select else target)])
        except OSError as exc:
            raise AppError(f"Could not open the file manager: {exc}") from exc
        return {"opened": str(target)}

    # uninstalling a game ----------------------------------------------------------------------------------------
    COMPANION_EXTS = {".cue", ".bin", ".sub", ".ccd", ".img", ".mds", ".mdf", ".sbi", ".gdi", ".m3u", ".ecm", ".raw"}

    def _within_roots(self, path: Path) -> bool:
        try:
            real = path.resolve()
        except OSError:
            return False
        for root in self.catalog.data["roots"]:
            try:
                base = Path(root).resolve()
            except OSError:
                continue
            if real != base and base in real.parents:
                return True
        return False

    def _game_files(self, game: dict) -> list[Path]:
        """The game's file plus the files that only make sense with it (cue sheets and their tracks). Never anything else."""
        main = Path(game["path"])
        files = [main]
        folder, stem = main.parent, main.stem.lower()
        try:
            siblings = [p for p in folder.iterdir() if p.is_file()]
        except OSError:
            siblings = []
        others = {str(Path(g["path"])).lower() for g in self.games.values() if g["id"] != game["id"]}   # files that are another game's own
        for p in siblings:
            if p != main and p.stem.lower() == stem and p.suffix.lower() in self.COMPANION_EXTS and str(p).lower() not in others:
                files.append(p)
        shared_tracks: set[str] = set()                          # tracks another game's cue sheet also lists stay put
        for other in self.games.values():
            op = Path(other["path"])
            if other["id"] != game["id"] and op.suffix.lower() == ".cue" and op.parent == folder:
                try:
                    shared_tracks.update(Path(n).name.lower() for n in re.findall(r'FILE\s+"([^"]+)"', op.read_text(encoding="utf-8", errors="ignore"), flags=re.I))
                except OSError:
                    pass
        for cue in [p for p in files if p.suffix.lower() == ".cue"]:
            try:
                text = cue.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for name in re.findall(r'FILE\s+"([^"]+)"', text, flags=re.I):
                track = folder / Path(name).name
                if track.is_file() and track not in files and track.suffix.lower() in self.COMPANION_EXTS and track.name.lower() not in shared_tracks:
                    files.append(track)
        return [p for p in files if self._within_roots(p) and p.is_file() and not p.is_symlink()]

    def _shares_saves(self, game: dict) -> bool:
        """Another game with the same file name would use the same save file (Mario.gb and Mario.gbc side by side)."""
        stem, save_dir = Path(game["path"]).stem.lower(), self._save_dir(game)
        return any(g["id"] != game["id"] and Path(g["path"]).stem.lower() == stem and self._save_dir(g) == save_dir for g in self.games.values())

    def _game_saves(self, game: dict) -> list[Path]:
        """Save files that belong to this game alone: the name must match exactly up to the first dot (Name.srm, Name.state1).
        When another game would use the very same save file, none are listed: deleting them would take that game's progress too."""
        save_dir = self._save_dir(game)
        if not save_dir or not Path(save_dir).is_dir() or self._shares_saves(game):
            return []
        stem = Path(game["path"]).stem.lower()
        return [p for p in saves.find_save_files(Path(save_dir), Path(game["path"]).stem)
                if (p.name.lower().startswith(stem + ".") or p.stem.lower() == stem) and p.is_file()]

    @staticmethod
    def _trash(paths: list[Path]) -> str:
        """Send files to the Recycle Bin / Trash. Returns where they went; raises OSError if that is not possible here."""
        if not paths:
            return "nothing to remove"
        if sys.platform.startswith("win"):
            import ctypes
            from ctypes import wintypes

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                            ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                            ("lpszProgressTitle", wintypes.LPCWSTR)]
            op = SHFILEOPSTRUCTW()
            op.wFunc = 3                                  # FO_DELETE
            op.pFrom = "\0".join(str(p) for p in paths) + "\0\0"
            op.fFlags = 0x40 | 0x10 | 0x4 | 0x400          # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
            if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) != 0 or op.fAnyOperationsAborted:
                raise OSError("Windows could not move the files to the Recycle Bin")
            return "the Recycle Bin"
        if sys.platform == "darwin":
            for p in paths:
                safe = str(p).replace("\\", "\\\\").replace('"', '\\"')
                subprocess.run(["osascript", "-e", f'tell application "Finder" to delete POSIX file "{safe}"'], check=True, capture_output=True)
            return "the Trash"
        for tool in (["gio", "trash"], ["trash-put"]):
            try:
                subprocess.run(tool + [str(p) for p in paths], check=True, capture_output=True)
                return "the Trash"
            except (OSError, subprocess.CalledProcessError):
                continue
        raise OSError("this computer has no Trash tool Legacy Player can use")

    @staticmethod
    def _delete_file(path: Path) -> None:
        """Delete one file. A read-only file (common on game dumps copied from discs or archives) is made writable first."""
        try:
            path.unlink()
        except PermissionError:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            path.unlink()

    def api_game_uninstall(self, body: dict) -> dict:
        """Uninstall one game: its files (to the Recycle Bin), and everything Legacy Player keeps about it. Saves only if asked."""
        game = self._game(body)
        files = self._game_files(game)
        if not files:
            raise AppError("Legacy Player can only uninstall files that sit inside your games folders, and this one does not.")
        save_files = self._game_saves(game)
        console = BY_ID[game["console"]]
        backup_folder = saves.backup_dir(self.data_dir, console.id, game["compat_id"])
        backups = sum(1 for f in backup_folder.rglob("*") if f.is_file()) if backup_folder.is_dir() else 0
        if not body.get("confirm"):
            return {"title": self._meta(game).get("title") or game["title"],
                    "files": [{"name": p.name, "folder": str(p.parent), "mb": round(p.stat().st_size / 1048576, 1)} for p in files],
                    "total_mb": round(sum(p.stat().st_size for p in files) / 1048576, 1),
                    "saves": [p.name for p in save_files], "backups": backups,
                    "saves_shared": self._shares_saves(game)}
        delete_saves = bool(body.get("delete_saves"))
        victims = files + (save_files if delete_saves else [])
        try:
            if body.get("permanent"):
                for p in victims:
                    self._delete_file(p)
                where = "removed for good"
            else:
                where = "moved to " + self._trash(victims)
        except PermissionError as exc:
            raise AppError(f"Windows refused to delete {Path(exc.filename or '').name or 'a file'} (access denied). It may be open in an emulator or another program, "
                           "or the folder is protected or read-only for your account. Close anything using it and try again, or check the folder's permissions.") from exc
        except OSError as exc:
            hint = "" if body.get("permanent") else " Tick 'Delete permanently' if you want to skip the Recycle Bin."
            raise AppError(f"The game was not removed: {exc}.{hint}") from exc
        if delete_saves and backup_folder.is_dir() and not any(g["id"] != game["id"] and g.get("compat_id") == game["compat_id"] and g["console"] == game["console"] for g in self.games.values()):
            shutil.rmtree(backup_folder, ignore_errors=True)
        gid = game["id"]
        self.games.pop(gid, None)
        data = self.catalog.data
        data["favorites"] = [i for i in data["favorites"] if i != gid]
        data["history"].pop(gid, None)
        data["game_meta"].pop(gid, None)
        for name in data["collections"]:
            data["collections"][name] = [i for i in data["collections"][name] if i != gid]
        self.catalog.save()
        clear_custom_cover(self.covers.cache, gid)
        cover_path(self.covers.cache, gid).unlink(missing_ok=True)
        self._cache_path().write_text(json.dumps({"games": list(self.games.values()), "skipped": self.skipped}), encoding="utf-8")
        return {"removed": game["title"], "where": where, "files": len(files), "saves_deleted": len(save_files) if delete_saves else 0,
                "saves_kept": 0 if delete_saves else len(save_files)}

    def api_collections(self, body: dict) -> dict:
        action = body.get("action", "list")
        if action != "list":
            if body.get("id"):
                self._game(body)
            try:
                self.catalog.collection_op(action, body.get("name"), body.get("id"))
            except CatalogError as exc:
                raise AppError(str(exc)) from exc
        cols = self.catalog.data["collections"]
        return {"collections": [{"name": n, "count": len(set(ids) & set(self.games))} for n, ids in sorted(cols.items(), key=lambda kv: kv[0].lower())]}

    # whole-library save backups -----------------------------------------------------
    def _save_sources(self) -> dict[str, Path]:
        root = self._save_root()
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        out = {}
        for c in CONSOLES:
            eid, _ = self._emulator_for(c.id, found)
            managed = c.id in CORES and eid == "retroarch"
            folder = self.catalog.data["save_sources"].get(c.id) or (str(savefolders.console_dir(root, c.id)) if managed else None)
            if folder and Path(folder).is_dir():
                out[c.id] = Path(folder)
        return out

    def _backup_root(self) -> Path:
        configured = self.catalog.data.get("backup_root")
        return Path(configured) if configured else self.data_dir / "save_backups" / "all"

    def api_backups(self, body: dict) -> dict:
        if "folder" in body:
            folder = str(body["folder"] or "").strip().strip('"')
            if folder:
                if not Path(folder).is_absolute():
                    raise AppError("Use a full folder path, for example E:\\Backups\\LegacyPlayer.")
                try:
                    Path(folder).mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise AppError(f"Could not use that folder: {exc}") from exc
            self.catalog.data["backup_root"] = folder
            self.catalog.save()
        root = self._backup_root()
        return {"folder": str(root), "custom": bool(self.catalog.data.get("backup_root")), "backups": saves.list_all_backups(root)[:50],
                "sources": {k: str(v) for k, v in self._save_sources().items()}}

    def api_backup_all(self, body: dict) -> dict:
        try:
            made = saves.backup_all(self._save_sources(), self._backup_root())
        except ValueError as exc:
            raise AppError(str(exc)) from exc
        except OSError as exc:
            raise AppError(f"Could not write the backup: {exc}") from exc
        return {**made, **self.api_backups({})}

    def api_restore_all(self, body: dict) -> dict:
        try:
            done = saves.restore_all(self._backup_root(), str(body.get("name", "")), self._save_sources(), self.data_dir / "save_backups" / "before_restore")
        except (ValueError, OSError) as exc:
            raise AppError(str(exc)) from exc
        return done

    def api_credits(self, body: dict) -> dict:
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        rows = [{"id": eid, "name": spec["name"], "consoles": spec["consoles"], "license": spec["license"],
                 "homepage": engines.HOMEPAGES.get(eid, spec["source"].get("url", "")),
                 "redistributable": eid not in engines.NOT_REDISTRIBUTABLE, "path": found.get(eid, {}).get("path")}
                for eid, spec in engines.ENGINES.items()]
        return {"engines": rows, "mirror": engines.MIRROR, "also": [
            {"name": "libretro cores", "text": "Per-console emulation plug-ins for RetroArch, each under its own license (listed in RetroArch > Information > Core Information)."},
            {"name": "Legacy Player", "text": "Shell, server, encryption and installer: this project, MIT licensed (see LICENSE). Uses only the Python standard library."},
        ]}

    def api_engines_install_all(self, body: dict) -> dict:
        """One click: fetch every missing engine that has an official GitHub release, one after another."""
        self._internet_ok(body)
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        wanted = [eid for eid, spec in engines.ENGINES.items()
                  if spec["source"]["kind"] == "github" and not found.get(eid, {}).get("path") and eid not in engines.NOT_REDISTRIBUTABLE]
        try:
            return {"job": self.installer.start_many(wanted, consent=True), "queued": wanted}
        except InstallError as exc:
            raise AppError(str(exc)) from exc

    def api_engines_scan(self, body: dict) -> dict:
        """User-directed read-only sweep of the usual program folders for emulators and BIOS."""
        if not body.get("confirm"):
            raise AppError("Please confirm the scan.")
        wanted = {eid: spec["exes"] for eid, spec in emulators.EMULATORS.items()}
        hits = engines.scan_computer(wanted, self._search_roots())
        for engine_id, path in hits.items():
            if not self.catalog.data["emulator_paths"].get(engine_id):
                self.catalog.set_mapping("emulator_paths", engine_id, path)
        extra = [Path(p).parent for p in self.catalog.data["emulator_paths"].values() if p]
        bios_found = {kind: engines.find_bios(kind, self._search_roots(), extra) for kind in engines.BIOS}
        self.catalog.data["bios_found"] = bios_found
        self.catalog.data["last_scan"] = time.time()
        self.catalog.save()
        return {**self._engines_payload(), "new": hits}

    def api_engines_source(self, body: dict) -> dict:
        """Where an engine would come from: always the fixed facts; with lookup=true (internet downloads on) also
        the latest release's tag, date and the exact file that would be downloaded. Downloads nothing."""
        spec = engines.ENGINES.get(body.get("engine"))
        if spec is None:
            raise AppError("Unknown engine.")
        src = spec["source"]
        out = {"name": spec["name"], "license": spec["license"], "kind": src["kind"], "homepage": engines.HOMEPAGES.get(body.get("engine"), src.get("url", ""))}
        if src["kind"] != "github":
            out["note"] = src.get("note", "This engine is not fetched automatically.")
            out["url"] = src.get("url", "")
            return out
        repo = src["repo"]
        out.update(repo=repo, repo_url=f"https://github.com/{repo}", releases_url=f"https://github.com/{repo}/releases",
                   api_url=f"https://api.github.com/repos/{repo}/releases/latest", asset_pattern=src["asset"],
                   hosts=sorted(GITHUB_HOSTS_SHOWN))
        if body.get("lookup"):
            if not self.catalog.settings()["allow_internet"]:
                raise AppError("Internet access is off. Turn on 'Allow internet downloads' in Settings to look up the latest release.")
            try:
                release = latest_release(repo)
            except InstallError as exc:
                raise AppError(str(exc)) from exc
            asset = pick_asset(release["assets"], src["asset"])
            out["release"] = {"tag": release["tag"], "name": release["name"], "published_at": release["published_at"],
                              "prerelease": release["prerelease"], "page": release["page"],
                              "asset": asset, "other_assets": len(release["assets"]) - (1 if asset else 0)}
        return out

    def api_engines_install(self, body: dict) -> dict:
        self._internet_ok(body)
        try:
            return {"job": self.installer.start(str(body.get("engine", "")), consent=True)}
        except InstallError as exc:
            raise AppError(str(exc)) from exc

    # controllers ------------------------------------------------------------
    def api_controllers(self, body: dict) -> dict:
        console = BY_ID.get(body.get("console"))
        if console is None:
            raise AppError("Unknown console.")
        if "buttons" in body:
            try:
                clean = controllers.validate_override(console.controller, body["buttons"]) if body["buttons"] else None
            except ValueError as exc:
                raise AppError(str(exc)) from exc
            self.catalog.set_mapping("controller_overrides", console.id, clean)
        return {
            "console": console.name,
            "layout": controllers.layout(console.controller, self.catalog.data["controller_overrides"].get(console.id)),
            "all": [{"id": c.id, "name": c.name} for c in CONSOLES],
        }

    def api_keyboard(self, body: dict) -> dict:
        """Player 1's keyboard controls: pick a layout or set each button's key."""
        if "layout" in body:
            try:
                self.catalog.data["keyboard"] = keyboard.validate(body)
            except ValueError as exc:
                raise AppError(str(exc)) from exc
            self.catalog.save()
        cfg = self.catalog.data.get("keyboard") or {"layout": "default", "keys": {}}
        layout = cfg.get("layout", "default")
        return {"layout": layout, "keys": keyboard.resolved(cfg), "roles": [{"id": r, "name": n} for r, n in keyboard.ROLES],
                "presets": {k: {"label": v["label"], "note": v["note"], "keys": v["keys"]} for k, v in keyboard.PRESETS.items()},
                "name": keyboard.PRESETS[layout]["label"] if layout in keyboard.PRESETS else "Custom"}

    # physical pads ------------------------------------------------------------
    def _pads_payload(self) -> dict:
        data = self.catalog.data
        return {"profiles": data["pad_profiles"], "players": data["player_pads"],
                "standard_names": {str(k): v for k, v in controllers.STANDARD_NAMES.items()},
                "max_players": pads.MAX_PLAYERS}

    def api_pads(self, body: dict) -> dict:
        return self._pads_payload()

    def api_pad_save(self, body: dict) -> dict:
        try:
            profile = pads.validate_profile(str(body.get("id", "")), body)
        except ValueError as exc:
            raise AppError(str(exc)) from exc
        self.catalog.set_mapping("pad_profiles", profile["key"], profile)
        return self._pads_payload()

    def api_pad_delete(self, body: dict) -> dict:
        try:
            key = pads.pad_key(str(body.get("id", "")))
        except ValueError as exc:
            raise AppError(str(exc)) from exc
        self.catalog.set_mapping("pad_profiles", key, None)
        for slot, assigned in list(self.catalog.data["player_pads"].items()):
            if assigned == key:
                self.catalog.set_mapping("player_pads", slot, None)
        return self._pads_payload()

    def api_pad_assign(self, body: dict) -> dict:
        player = body.get("player")
        if isinstance(player, bool) or not isinstance(player, int) or not 1 <= player <= pads.MAX_PLAYERS:
            raise AppError(f"Player must be 1 to {pads.MAX_PLAYERS}.")
        key = body.get("id")
        if key:
            try:
                key = pads.pad_key(str(key))
            except ValueError as exc:
                raise AppError(str(exc)) from exc
            if key not in self.catalog.data["pad_profiles"]:
                # a pad with no custom mapping still gets a (default) profile so it can be assigned
                self.catalog.set_mapping("pad_profiles", key, pads.validate_profile(key, {
                    "name": body.get("name") or "Controller", "standard": bool(body.get("standard")), "bindings": {}}))
        self.catalog.set_mapping("player_pads", str(player), key or None)
        return self._pads_payload()

    # settings ---------------------------------------------------------------
    def api_settings(self, body: dict) -> dict:
        if "key" in body:
            try:
                self.catalog.set_setting(body["key"], body.get("value"))
            except CatalogError as exc:
                raise AppError(str(exc)) from exc
        return {"values": self.catalog.settings(), "schema": SETTINGS_SCHEMA}

    # saves ------------------------------------------------------------------
    def api_save_source(self, body: dict) -> dict:
        console = BY_ID.get(body.get("console"))
        if console is None:
            raise AppError("Unknown console.")
        path = body.get("path")
        if path and not Path(path).is_dir():
            raise AppError("That folder does not exist.")
        self.catalog.set_mapping("save_sources", console.id, path or None)
        return {"save_source": path or None}

    def api_save_folders(self, body: dict) -> dict:
        if "root" in body:
            root = body["root"]
            if root:
                if not isinstance(root, str) or not Path(root).is_absolute():
                    raise AppError("Use a full folder path, for example D:\\LegacyPlayer\\Saves.")
                try:
                    Path(root).mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise AppError(f"Could not create that folder: {exc}") from exc
            self.catalog.data["save_root"] = root or ""
            self.catalog.save()
        root = self._save_root()
        if body.get("create"):
            try:
                savefolders.ensure(root, [c.id for c in CONSOLES if c.id in CORES])
            except OSError as exc:
                raise AppError(f"Could not create the save folders: {exc}") from exc
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        rows = []
        for console in CONSOLES:
            emulator_id, _ = self._emulator_for(console.id, found)
            managed = console.id in CORES and emulator_id == "retroarch"
            folder = self.catalog.data["save_sources"].get(console.id) or (
                str(savefolders.console_dir(root, console.id)) if managed else None)
            exists = bool(folder) and Path(folder).is_dir()
            rows.append({
                "console": console.id, "name": console.name, "folder": folder, "exists": exists,
                "files": len(saves.find_save_files(Path(folder), "")) if exists else 0,
                "mode": "custom" if console.id in self.catalog.data["save_sources"] else ("managed" if managed else "emulator"),
                "emulator": emulators.EMULATORS[emulator_id]["name"] if emulator_id else None,
                "hint": "" if managed else savefolders.EMULATOR_HINTS.get(emulator_id or "", ""),
            })
        return {"root": str(root), "custom_root": bool(self.catalog.data.get("save_root")), "consoles": rows,
                "backups_folder": str(self.data_dir / "save_backups")}

    def _save_ctx(self, body: dict):
        game = self._game(body)
        console = BY_ID[game["console"]]
        source = self._save_dir(game)
        if not source:
            raise AppError(f"Tell the launcher where {console.name} saves are kept first (Save folder).")
        return game, console, Path(source)

    def api_backup(self, body: dict) -> dict:
        game, console, source = self._save_ctx(body)
        files = saves.find_save_files(source, Path(game["path"]).stem)
        try:
            return saves.create_backup(self.data_dir, console.id, game["compat_id"], files, source)
        except ValueError as exc:
            raise AppError(str(exc)) from exc

    def api_restore(self, body: dict) -> dict:
        game, console, source = self._save_ctx(body)
        try:
            return saves.restore_backup(self.data_dir, console.id, game["compat_id"], str(body.get("backup")), source, Path(game["path"]).stem)
        except ValueError as exc:
            raise AppError(str(exc)) from exc

    # multiplayer -------------------------------------------------------------
    def _client(self) -> LobbyClient:
        s = self.catalog.settings()
        fingerprint = "" if s["server_fingerprint"].strip() in {"", "-"} else s["server_fingerprint"]
        key = s["server_access_key"]
        if s["server_host"] in {"127.0.0.1", "localhost", "::1"}:      # our own server: always read its current key
            key = self._own_server_key() or key
        local = s["server_host"] in {"127.0.0.1", "localhost", "::1"}
        return LobbyClient(s["server_host"], s["server_port"] if local else s["server_remote_port"], tls=s["server_tls"], verify=s["server_tls_verify"],
                           fingerprint=fingerprint, access_key=key)

    def _own_server_key(self) -> str:
        path = self.data_dir / "server" / "access_key.bin"
        try:
            return path.read_bytes().hex() if path.is_file() else ""
        except OSError:
            return ""

    def _call(self, request: dict) -> dict:
        try:
            return self._client().call(request)
        except LobbyClientError as exc:
            if self._own_server_refused(exc) and self._start_own_server():
                try:
                    return self._client().call(request)
                except LobbyClientError as again:
                    raise AppError(str(again)) from again
            raise AppError(str(exc)) from exc

    _auto_started_at: float | None = None      # not 0.0: a computer that booted under 30 seconds ago would count as "just tried"

    def _own_server_refused(self, exc: Exception) -> bool:
        """Only a refused call to our own server, never while quitting and never right after the player stopped it."""
        s = self.catalog.settings()
        return (s["server_host"] in {"127.0.0.1", "localhost", "::1"} and isinstance(exc.__cause__, ConnectionRefusedError)
                and bool(s.get("server_autostart", True)) and not self.quit_requested and not self._user_stopped)

    _user_stopped = False

    def _start_own_server(self) -> bool:
        """Your own server is not running (the app was restarted, or it stopped): start it, so hosting just works.
        At most once every 30 seconds, and only for the server on this computer."""
        if self._auto_started_at is not None and time.monotonic() - self._auto_started_at < 30:
            return False
        self._auto_started_at = time.monotonic()
        share = bool(self.catalog.data.get("server_share_wanted"))     # shared only if the player last started it that way
        try:
            self.api_server_control({"action": "start", "share": share})
            return True
        except AppError:
            return False

    def api_server_activity(self, body: dict) -> dict:
        """What is going on at your own server right now: how many people, rooms, how long it has been up."""
        from server import cli
        try:
            info = cli._admin_call(self.data_dir / "server", "admin_status", timeout=2.0)
        except (OSError, ConnectionError, ValueError):
            return {"online": False}
        return {"online": True, "uptime_seconds": info.get("uptime_seconds", 0), "players": info.get("players_in_live_sessions", 0),
                "rooms": info.get("sessions_live", 0), "open_rooms": info.get("open_rooms", 0), "waiting": info.get("waiting_total", 0),
                "shared": bool(self.catalog.settings().get("server_tls"))}

    def _profile(self, game: dict) -> dict:
        return {"game_id": game["compat_id"], "region": game["region"] or "unspecified"}

    def _auth(self) -> dict:
        r = self.room
        if r is None:
            raise AppError("You are not in a room.")
        return {"session_id": r["session_id"], "participant_id": r["me"], "credential": r["credential"]}

    # who you are on servers --------------------------------------------------------
    _ALIAS_OK = __import__("re").compile(r"^[A-Za-z0-9 _.\-]{1,24}$")

    def _claim_alias(self) -> str | None:
        """Ask the server for a #tag no other active player with this name has. Best effort: an older server
        or no server means the local tag is used."""
        s = self.catalog.settings()
        name = s["display_name"]
        if not self._ALIAS_OK.match(name):
            return None
        try:
            got = self._client().call({"operation": "claim_alias", "alias": name, "install_id": self.catalog.data["install_id"],
                                       "tag": self.catalog.data.get("alias_tag") or ""})
        except (LobbyClientError, OSError, ValueError, KeyError):
            return None
        self.catalog.data["alias_tag"] = got["tag"]
        self.catalog.save()
        return got["tag"]

    def api_profile(self, body: dict) -> dict:
        """Your name and picture. The #tag comes from the server so nobody active shares your name and tag."""
        if "alias" in body:
            name = str(body["alias"]).strip()
            if not self._ALIAS_OK.match(name):
                raise AppError("A name is 1 to 24 letters, numbers, spaces, dots, dashes or underscores.")
            self.catalog.set_setting("display_name", name)
        if "avatar" in body:
            self.catalog.set_setting("avatar", str(body["avatar"])[:24])
        claimed = self._claim_alias() if ("alias" in body or body.get("claim")) else None
        s = self.catalog.settings()
        tag = self.catalog.data.get("alias_tag") or ""
        return {"alias": s["display_name"], "avatar": s["avatar"], "tag": tag, "claimed": bool(tag),
                "player": f"{s['display_name']}#{tag or self.catalog.data['install_id']}",
                "note": "" if tag else "No server gave this name a tag yet, so a local tag is used. It is claimed when you connect to a server."}

    def api_storage(self, body: dict) -> dict:
        per: dict[str, dict] = {}
        for g in self.games.values():
            row = per.setdefault(g["console"], {"id": g["console"], "name": BY_ID[g["console"]].name, "count": 0, "bytes": 0})
            row["count"] += 1
            row["bytes"] += g["size"]
        rows = sorted(per.values(), key=lambda r: -r["bytes"])
        free = None
        try:
            import shutil
            roots = self.catalog.data["roots"]
            if roots:
                free = shutil.disk_usage(roots[0]).free
        except OSError:
            pass
        return {"consoles": rows, "total_bytes": sum(r["bytes"] for r in rows), "total_games": sum(r["count"] for r in rows), "free_bytes": free}

    def api_home(self, body: dict) -> dict:
        history = self.catalog.data["history"]
        hidden = {i for i, m in self.catalog.data["game_meta"].items() if m.get("hidden")}
        recent = sorted((g for g in self.games.values() if history.get(g["id"], {}).get("last_played") and g["id"] not in hidden),
                        key=lambda g: -history[g["id"]]["last_played"])[:8]
        favs = [g for g in self.games.values() if g["id"] in set(self.catalog.data["favorites"]) and g["id"] not in hidden][:8]
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        emus = self._console_emulators()
        s = self.catalog.settings()
        featured = None
        if s["featured_title"]:
            featured = {"title": s["featured_title"], "text": s["featured_text"], "link": s["featured_link"]}
        ready = [c.id for c in CONSOLES if self._emulator_for(c.id, found)[0]]
        return {
            "recent": [self._public(g, emus) for g in recent], "favorites": [self._public(g, emus) for g in favs],
            "emulators": [{"id": k, "name": v["name"], "path": v["path"]} for k, v in found.items() if v["path"]],
            "consoles_ready": len(ready), "consoles_total": len(CONSOLES), "games_total": len(self.games),
            "featured": featured, "version": VERSION, "alias": s["display_name"], "avatar": s["avatar"],
        }

    def api_doctor(self, body: dict) -> dict:
        """A health check of everything the app needs, in plain facts. Nothing is changed."""
        found = emulators.find_emulators(self._search_roots(), self.catalog.data["emulator_paths"])
        have = [v["name"] for v in found.values() if v["path"]]
        counts: dict[str, int] = {}
        for g in self.games.values():
            counts[g["console"]] = counts.get(g["console"], 0) + 1
        dismissed = set(self.catalog.data.get("doctor_dismissed", []))
        issues = []
        ra = found.get("retroarch", {}).get("path")
        for c in CONSOLES:
            if counts.get(c.id) and not self._emulator_for(c.id, found)[0]:
                names = ", ".join(emulators.EMULATORS[e]["name"] for e in c.emulators if e in emulators.EMULATORS)
                if ra and c.id in CORES:
                    issues.append({"key": c.id, "kind": "core", "text": f"{counts[c.id]} {c.name} games: RetroArch is here but has no {c.name} core yet.",
                                   "dismissed": c.id in dismissed})
                else:
                    issues.append({"key": c.id, "kind": "emulator", "text": f"{counts[c.id]} {c.name} games still need an emulator ({names}).",
                                   "dismissed": c.id in dismissed})
        bios_found = self.catalog.data.get("bios_found", {})
        bios_needed = bios_have = 0
        for eid, v in found.items():
            kind = engines.ENGINES.get(eid, {}).get("bios")
            if v["path"] and kind:
                bios_needed += 1
                if bios_found.get(kind):
                    bios_have += 1
                else:
                    issues.append({"key": "bios:" + kind, "kind": "bios", "text": f"{engines.BIOS[kind]['name']} not found; {v['name']} needs it.",
                                   "dismissed": ("bios:" + kind) in dismissed})
        active = [i for i in issues if not i["dismissed"]]
        if not self.games or not have:
            mood = "sad"
        elif active:
            mood = "worried"
        else:
            mood = "happy"
        chosen = {c.id: self._emulator_for(c.id, found)[0] for c in CONSOLES}
        cards = []
        for eid, v in found.items():
            if not v["path"]:
                continue
            mine = [c for c in CONSOLES if chosen.get(c.id) == eid]
            cards.append({"id": eid, "name": v["name"], "path": v["path"], "consoles": [c.name for c in mine],
                          "games": sum(counts.get(c.id, 0) for c in mine)})
        library = [{"name": c.name, "count": counts[c.id], "emulator": (emulators.EMULATORS.get(chosen[c.id]) or {}).get("name")}
                   for c in CONSOLES if counts.get(c.id)]
        return {"emulator_cards": cards, "library": library,
                "mood": mood, "games": len(self.games), "emulators": have, "saves_ready": self._save_root().is_dir(),
                "bios_needed": bios_needed, "bios_have": bios_have, "issues": issues,
                "last_rescan": self.catalog.data.get("last_rescan"), "last_scan": self.catalog.data.get("last_scan"),
                "consoles_ready": sum(1 for c in CONSOLES if self._emulator_for(c.id, found)[0]), "consoles_total": len(CONSOLES)}

    def api_specs(self, body: dict) -> dict:
        """The computer's CPU, memory, graphics card and system, read locally. Cached; pass refresh to read again."""
        with self._specs_lock:          # slow (PowerShell): runs outside the big API lock, one read at a time
            if body.get("refresh") or getattr(self, "_specs", None) is None:
                self._specs = sysinfo.collect()
            return self._specs

    def api_doctor_dismiss(self, body: dict) -> dict:
        key = str(body.get("key", ""))[:40]
        cur = set(self.catalog.data.get("doctor_dismissed", []))
        (cur.discard if body.get("undo") else cur.add)(key)
        self.catalog.data["doctor_dismissed"] = sorted(cur)
        self.catalog.save()
        return self.api_doctor({})

    def api_scan_everything(self, body: dict) -> dict:
        """The quick, no-wait parts of a full check: read the games folders again and make the save folders.
        The slower program-and-BIOS scan is started separately with scan_pc."""
        out = {}
        if self.catalog.data["roots"]:
            out["rescan"] = self.rescan()
        try:
            with self.api_lock:
                self.api_save_folders({"create": True})
            out["saves"] = True
        except Exception:
            out["saves"] = False
        return out

    def api_check_update(self, body: dict) -> dict:
        """Ask GitHub whether a newer release exists. Only when the user presses the button and allows internet."""
        if not self.catalog.settings()["allow_internet"]:
            raise AppError("Internet access is off. Turn on 'Allow internet downloads' in Settings to check for updates (it only asks api.github.com).")
        try:
            rel = latest_release(REPO)
        except InstallError as exc:
            return {"current": VERSION, "ok": False, "message": f"Could not check: {exc}"}
        def nums(v: str) -> tuple:
            return tuple(int(x) for x in __import__("re").findall(r"\d+", v)[:3])
        newer = nums(rel["tag"]) > nums(VERSION) if nums(rel["tag"]) else False
        return {"current": VERSION, "ok": True, "latest": rel["tag"], "newer": newer, "page": rel["page"], "published_at": rel["published_at"],
                "message": ("Version " + rel["tag"] + " is available.") if newer else "You have the latest version."}

    def api_mp_host(self, body: dict) -> dict:
        self._claim_alias()
        game = self._game(body)
        me = self.catalog.player_tag()
        _, info = self._emulator_for(game["console"])
        who = gameinfo.players_for(game["console"], game["title"], self.catalog.data["game_meta"].get(game["id"], {}).get("players", ""))
        if who["max"] < 2 and who["source"] != "console":
            raise AppError(f"{game['title']} is a single-player game, so there is nobody to invite. Pick a game with two or more players "
                           "(if that is wrong, set the number of players on the game's page).")
        ceiling = who["max"] if who["source"] != "console" else who["hw"]
        wanted = int(body.get("max_players") or max(2, who["max"]))
        created = self._call({
            "operation": "create", "participant_id": me, "profile": self._profile(game),
            "adapter_id": (self._emulator_for(game["console"])[0] or "unconfigured"), "game_pack_id": "generic",
            "require_approval": bool(body.get("require_approval", True)),
            "max_players": max(2, min(wanted, ceiling, 8)),
            "open": bool(body.get("open", False)), "label": str(body.get("label") or "")[:48],
        })
        self.room = {
            "session_id": created["session"]["session_id"], "me": me, "credential": created["credential"],
            "role": "host", "game_id": game["id"], "game": game["title"], "console": game["console"], "invite_code": created["invite_code"],
            "invite_expires_at": created["invite_expires_at"], "events": [], "last_seq": 0, "session": created["session"],
            "approval": created["require_approval"], "waiting": None, "problem": None,
            "queue": None, "max_players": created["max_players"], "waitlist": [], "open": created.get("open", False),
        }
        return self.api_mp_state({})

    def api_mp_join(self, body: dict) -> dict:
        """Join with an invite code, or an open room by id. With background=true the join
        only queues you (keep playing); you switch over when a spot is ready."""
        game = self._game(body)
        self._claim_alias()
        me = self.catalog.player_tag()
        request = {"operation": "join", "participant_id": me, "profile": self._profile(game)}
        if body.get("session_id"):
            request.update(session_id=str(body["session_id"]), open=True)
        else:
            request["invite_code"] = str(body.get("invite_code", ""))
        result = self._call(request)
        record = {
            "session_id": result.get("session_id") or result["session"]["session_id"], "me": me, "credential": result.get("credential"),
            "role": "guest", "game_id": game["id"], "game": game["title"], "console": game["console"], "invite_code": None, "invite_expires_at": None,
            "events": [], "last_seq": 0, "session": result.get("session"), "approval": result["status"] == "pending",
            "waiting": result.get("request_token"), "problem": None,
            "queue": result if result["status"] == "waiting" else None, "max_players": None, "waitlist": [],
        }
        if body.get("background") or (self.room is not None and result["status"] != "joined"):
            if result["status"] == "joined":
                # a seat was free right away: it is held for you in the roster, switch when ready
                record["ready_to_switch"] = True
            self.waits[record["session_id"]] = record
            return self.api_mp_state({})
        self.room = record
        return self.api_mp_state({})

    def api_mp_browse(self, body: dict) -> dict:
        """Open rooms on the server: game, how full, line length. No names, no addresses."""
        listing = self._call({"operation": "browse"})
        by_compat = {g["compat_id"]: g for g in self.games.values()}
        rooms = []
        for r in listing["rooms"]:
            mine = by_compat.get(r["game_id"])
            rooms.append({**r, "title": mine["title"] if mine else r["game_id"], "console": mine["console"] if mine else r["game_id"].split(":")[0],
                          "you_have_it": mine is not None, "local_game_id": mine["id"] if mine else None,
                          "console_name": BY_ID[mine["console"]].name if mine else r["game_id"].split(":")[0],
                          "emulator": (self._emulator_for(mine["console"])[1] or {}).get("name") if mine else None,
                          "full": r["players"] >= r["max_players"]})
        return {"rooms": rooms, "limits": listing["limits"]}

    def api_mp_open(self, body: dict) -> dict:
        result = self._host_action(body, "set_open", open=bool(body.get("open", True)))
        if self.room:
            self.room["open"] = bool(body.get("open", True))
        return result

    def api_mp_switch(self, body: dict) -> dict:
        """Your turn came: leave what you were doing and take the seat.

        close_game=true asks the game you were playing to close politely (the emulator gets a
        normal close request, so it writes its save files as it would when you click X).
        auto_join=true then joins the match straight away if the host has launched."""
        sid = str(body.get("session_id", ""))
        record = self.waits.get(sid)
        if record is None:
            raise AppError("You are not waiting for that room.")
        closed = None
        if body.get("close_game") and self._running_now():
            emulators.close_pid(self.running["pid"])
            closed = self.running["title"]
            self.running = None
        if self.room is not None:
            self.api_mp_leave({})
        del self.waits[sid]
        record.pop("ready_to_switch", None)
        self.room = record
        state = self.api_mp_state({})
        if body.get("auto_join"):
            try:
                launched = self.api_mp_launch({})
                state["joined_match"] = launched
            except AppError as exc:
                state["join_note"] = str(exc)   # usually "the host has not launched yet"
        state["closed_game"] = closed
        return state

    def api_mp_cancel_wait(self, body: dict) -> dict:
        sid = str(body.get("session_id", ""))
        record = self.waits.pop(sid, None)
        if record is not None:
            try:
                if record["waiting"]:
                    self._call({"operation": "cancel_wait", "session_id": sid, "participant_id": record["me"], "request_token": record["waiting"]})
                elif record.get("credential"):
                    self._call({"operation": "leave", "session_id": sid, "participant_id": record["me"], "credential": record["credential"]})
            except AppError:
                pass
        return self.api_mp_state({})

    def _poll_waits(self) -> list[dict]:
        notices = []
        for sid, w in list(self.waits.items()):
            if not w["waiting"]:
                continue
            try:
                status = self._call({"operation": "join_status", "session_id": sid, "participant_id": w["me"], "request_token": w["waiting"]})
            except AppError as exc:
                self.waits.pop(sid, None)
                notices.append({"seq": -1, "kind": "wait", "level": "warn", "at": "", "text": f"Your place in line for {w['game']} was lost: {exc}"})
                continue
            if status["status"] == "waiting":
                w["queue"] = status
            elif status["status"] == "pending":
                w["queue"] = None
            elif status["status"] == "approved":
                w.update(credential=status["credential"], waiting=None, queue=None, session=status["session"], ready_to_switch=True)
                notices.append({"seq": -1, "kind": "wait", "level": "info", "at": "",
                                "text": f"A spot in {w['game']} is yours. Finish what you are doing, then press Switch."})
            elif status["status"] == "denied":
                self.waits.pop(sid, None)
                notices.append({"seq": -1, "kind": "wait", "level": "warn", "at": "", "text": f"The host of {w['game']} declined you."})
        return notices

    def _waits_view(self) -> list[dict]:
        return [{"session_id": sid, "game": w["game"], "position": (w.get("queue") or {}).get("position"),
                 "ready": bool(w.get("ready_to_switch")), "pending": w["waiting"] is not None and w.get("queue") is None}
                for sid, w in self.waits.items()]

    def api_mp_state(self, body: dict) -> dict:
        wait_notices = self._poll_waits() if self.waits else []
        r = self.room
        if r is None:
            return {"room": None, "waits": self._waits_view(), "wait_events": wait_notices}
        new_events = list(wait_notices)
        try:
            if r["waiting"]:
                status = self._call({"operation": "join_status", "session_id": r["session_id"], "participant_id": r["me"], "request_token": r["waiting"]})
                if status["status"] == "waiting":
                    before = (r.get("queue") or {}).get("position")
                    r["queue"] = status
                    if before is not None and before != status["position"]:
                        new_events.append({"seq": -1, "kind": "queue", "level": "info", "at": "",
                                           "text": f"You moved to number {status['position']} in line."})
                elif status["status"] == "pending":
                    r["queue"] = None
                    new_events.append({"seq": -1, "kind": "queue", "level": "info", "at": "",
                                       "text": "A spot is free. Waiting for the host to approve you."})
                elif status["status"] == "approved":
                    r.update(credential=status["credential"], waiting=None, queue=None, session=status["session"])
                    new_events.append({"seq": -1, "kind": "approved", "text": "You're in. The room has a spot for you.", "level": "info", "at": ""})
                elif status["status"] == "denied":
                    self.room = None
                    return {"room": None, "notice": "The host declined your request."}
            if not r["waiting"]:
                res = self._call({"operation": "events", "after_seq": r["last_seq"], **self._auth()})
                for event in res["events"]:
                    r["last_seq"] = max(r["last_seq"], event["seq"])
                    new_events.append(describe_event(event))
                t0 = time.monotonic()
                status = self._call({"operation": "status", **self._auth()})
                ping_ms = round((time.monotonic() - t0) * 1000, 1)
                r["session"], r["stats"], r["start"] = status["session"], status.get("stats"), status.get("start")
                self._maybe_auto_agree(r, new_events)
                self._report_stats(ping_ms)
                if r["role"] == "host":
                    listing = self._call({"operation": "list_waiting", **self._auth()})
                    r["waitlist"], r["max_players"] = listing["waiting"], listing["capacity"]
            r["problem"] = None
        except AppError as exc:
            message = str(exc)
            if "kicked from session" in message or "you left" in message:
                self.room = None
                return {"room": None, "notice": message[0].upper() + message[1:], "level": "warn"}
            r["problem"] = message
        r["events"] = (r["events"] + new_events)[-100:]
        session = r.get("session") or {}
        members = [
            {"name": name, "role": p["role"], "ready": p["ready"], "me": name == r["me"]}
            for name, p in (session.get("participants") or {}).items()
        ]
        return {"room": {
            "role": r["role"], "game": r["game"], "game_id": r["game_id"], "console": r["console"], "state": session.get("state", "waiting for host"),
            "failure": session.get("failure_reason"), "invite_code": r["invite_code"], "invite_expires_at": r["invite_expires_at"],
            "members": members, "events": r["events"], "new_events": new_events, "problem": r["problem"],
            "waiting_for_host": bool(r["waiting"]) and not r.get("queue"), "approval": r["approval"],
            "queue": r.get("queue"), "waitlist": r.get("waitlist") or [], "max_players": r.get("max_players"),
            "open": r.get("open", False),
            "stats": self._stats_for_ui(r),
            "start": self._start_for_ui(r),
            "pending": self._pending_requests(r),
            "launch": self._room_launch_state(r, session),
            "relay_errors": list(getattr(self.tunnel, "errors", []) or [])[-3:],
            "running": self._running_now(),
        }, "waits": self._waits_view()}

    def _room_launch_state(self, room: dict, session: dict) -> dict:
        game = self.games.get(room["game_id"])
        if game is None:
            return {"ready": False, "reason": "Your copy of this game is no longer in the library."}
        check = self.netplay_check(game)
        ok = check["ready"]
        reason = check["reason"]
        if ok and room["role"] == "host" and session.get("state") not in {"ready-barrier", "active"}:
            ok, reason = False, "Press 'Check everyone matches' first."
        if ok and room["role"] == "guest" and session.get("state") not in {"ready-barrier", "active"}:
            ok, reason = False, "Waiting for the host to check that everyone matches."
        engine = check.get("engine") or ("dolphin" if game["console"] in DOLPHIN_CONSOLES else "retroarch")
        return {"ready": ok, "reason": reason, "steps": check.get("steps", []), "engine": engine, "suggested_address": detect_lan_address(),
                "relay_available": netplay_tunnel.available() and engine == "retroarch",
                "direct_allowed": self.catalog.settings()["allow_direct_connections"],
                "endpoint_kind": (room.get("session") or {}).get("endpoint_kind"),
                "default_port": DOLPHIN_PORT if engine == "dolphin" else 55435}

    @staticmethod
    def _pending_requests(room: dict) -> list[str]:
        waiting: list[str] = []
        for event in room["events"]:
            who = event.get("who")
            if event["kind"] == "join_requested" and who and who not in waiting:
                waiting.append(who)
            elif event["kind"] in {"participant_joined", "join_denied", "participant_kicked"} and who in waiting:
                waiting.remove(who)
        return waiting if room["role"] == "host" else []

    def _host_action(self, body: dict, operation: str, **extra) -> dict:
        self._call({"operation": operation, **extra, **self._auth()})
        return self.api_mp_state({})

    def api_mp_invite(self, body: dict) -> dict:
        res = self._call({"operation": "invite", "priority": bool(body.get("priority")), **self._auth()})
        self.room["invite_code"], self.room["invite_expires_at"] = res["invite_code"], res["expires_at"]
        return self.api_mp_state({})

    def api_mp_decide(self, body: dict) -> dict:
        return self._host_action(body, "decide_join", target_id=str(body.get("target")), approve=bool(body.get("approve")))

    def api_mp_priority(self, body: dict) -> dict:
        return self._host_action(body, "set_priority", target_id=str(body.get("target")), priority=bool(body.get("priority", True)))

    def api_mp_capacity(self, body: dict) -> dict:
        result = self._host_action(body, "set_capacity", max_players=body.get("max_players"))
        return result

    def api_mp_kick(self, body: dict) -> dict:
        return self._host_action(body, "kick", target_id=str(body.get("target")), reason=str(body.get("reason") or "removed by host"))

    def _report_stats(self, ping_ms: float) -> None:
        """Tell the room our own numbers: ping to the server and the match tunnel's speeds. Numbers only."""
        rates = netplay_tunnel.METER.rates() if self.tunnel is not None else {}
        try:
            self._call({"operation": "report_stats", "ping_ms": ping_ms, "in_match": bool((self.room or {}).get("launched")), **rates, **self._auth()})
        except AppError:
            pass

    def _stats_for_ui(self, room: dict) -> dict:
        stats = room.get("stats") or {"people": {}, "average": {}}
        return {"people": stats.get("people", {}), "average": stats.get("average", {}),
                "playing": self.tunnel is not None}

    def _maybe_auto_agree(self, room: dict, events: list) -> None:
        """Guests who switched on "Join the games the host picks" agree to a start request by themselves, once the
        game is in their library. Everyone else is still asked every time."""
        start = room.get("start")
        if not start or room["role"] != "guest" or room["me"] in start["consented"]:
            return
        if not self.catalog.settings().get("mp_auto_agree") or self.games.get(room["game_id"]) is None:
            return
        try:
            self._call({"operation": "consent_start", "start_id": start.get("id"), **self._auth()})
            start["consented"] = list(start["consented"]) + [room["me"]]
            events.append({"seq": -1, "kind": "auto_agreed", "level": "info", "at": "", "text": "You agreed to start automatically (your setting)."})
        except AppError:
            pass

    def _start_for_ui(self, room: dict) -> dict | None:
        start = room.get("start")
        if not start:
            return None
        game = self.games.get(room["game_id"])
        mine = room["me"] in start["consented"]
        return {**start, "mine": mine, "have_game": game is not None,
                "ask_me": room["role"] == "guest" and not mine}

    def api_mp_game(self, body: dict) -> dict:
        """Host: pick a different game for the room. Guests are told and must have it too."""
        room = self.room
        if room is None or room["role"] != "host":
            raise AppError("Only the host can change the game.")
        game = self._game(body)
        self._call({"operation": "set_game", "profile": self._profile(game), "title": game["title"], **self._auth()})
        room.update(game_id=game["id"], game=game["title"], console=game["console"])
        return self.api_mp_state({})

    def api_mp_start(self, body: dict) -> dict:
        """Host: ask everyone to start. Needs the host's own yes; guests each say yes for themselves."""
        room = self.room
        if room is None or room["role"] != "host":
            raise AppError("Only the host can start the game.")
        if not body.get("consent"):
            raise AppError("Confirm that you want to start this game with everyone in the room.")
        self._call({"operation": "validate", **self._auth()})        # same game and region for everyone
        self._call({"operation": "announce_start", "title": room["game"], **self._auth()})
        return self.api_mp_state({})

    def api_mp_consent(self, body: dict) -> dict:
        """Guest: agree to the host's start request. Only with consent=true; then, if asked, open the game and connect."""
        room = self.room
        if room is None:
            raise AppError("You are not in a room.")
        if not body.get("consent"):
            raise AppError("Say yes first: nothing opens on your computer without your agreement.")
        start = room.get("start") or {}
        self._call({"operation": "consent_start", "start_id": body.get("start_id", start.get("id")), **self._auth()})
        return self.api_mp_state({})

    def api_mp_lock(self, body: dict) -> dict:
        return self._host_action(body, "validate")

    def api_mp_ready(self, body: dict) -> dict:
        return self._host_action(body, "ready", ready=bool(body.get("ready", True)))

    def api_mp_launch(self, body: dict) -> dict:
        """Host: publish the address and start RetroArch hosting. Guest: connect to the host."""
        room = self.room
        if room is None:
            raise AppError("You are not in a room.")
        game = self._game({"id": room["game_id"]})
        check = self.netplay_check(game)
        if not check["ready"]:
            raise AppError(check["reason"])
        nick = room["me"]
        if check.get("engine") == "dolphin":
            return self._launch_dolphin(room, game, check, body)
        encrypt = bool(self.catalog.settings()["encrypt_matches"])
        encrypted = False
        try:
            self._close_tunnel()
            extra = self._retroarch_extra(game["console"], check["exe"], netplay=True)
            if room["role"] == "host":
                port = body.get("port", 55435)
                address = str(body.get("address") or detect_lan_address()).strip()
                state = self._call({"operation": "status", **self._auth()})["session"]["state"]
                if state not in {"ready-barrier", "active"}:
                    raise AppError("Press 'Check everyone matches' first.")
                key = None
                ra_port = port
                settings = self.catalog.settings()
                relay = bool(body.get("relay", True))
                if not relay:
                    # Direct netplay hands the host's address to every guest. It is never the default
                    # and needs both the privacy setting and an explicit confirmation for this launch.
                    if not settings["allow_direct_connections"]:
                        raise AppError("Direct connections are off (Settings > Privacy). They would reveal your address to every guest; the relay hides it.")
                    if not body.get("expose_address"):
                        raise AppError("Confirm that you accept revealing your address to the guests, or use the relay.")
                if relay and not encrypt:
                    raise AppError("Relay mode needs 'Encrypt match traffic' on (the relay only carries encrypted bytes).")
                if encrypt:
                    if not netplay_tunnel.available():
                        raise AppError("Encrypted matches need the Legacy Player app (Python 3.13+). Turn off 'Encrypt match traffic' in Settings to play unencrypted on a trusted network.")
                    key = netplay_tunnel.new_key()
                    if relay:
                        # Guests reach RetroArch only through the relay. RetroArch itself still listens on
                        # this port on every interface (it has no bind option): keep it unforwarded at the router.
                        ra_port = port
                        client, auth = self._client(), self._auth()
                        self.tunnel = netplay_tunnel.RelayHost(
                            key, lambda track: client.open_relay("host", auth, wait_paired=True, on_socket=track), "127.0.0.1", ra_port,
                            slots=max(1, (room.get("max_players") or 4) - 1)).start()
                    else:
                        ra_port = port + 1 if port < 65535 else port - 1
                        self.tunnel = netplay_tunnel.Tunnel("host", key, "0.0.0.0", port, "127.0.0.1", ra_port).start()
                    encrypted = True
                command = build_host_command(check["exe"], check["core"], game["path"], ra_port, nick, extra)
            else:
                endpoint = self._call({"operation": "get_endpoint", **self._auth()})["endpoint"]
                if not endpoint:
                    raise AppError("The host has not launched yet. Wait for the notification.")
                if endpoint.get("kind") == "relay":
                    if not endpoint.get("psk"):
                        raise AppError("The host's relay has no key; ask them to relaunch.")
                    client, auth = self._client(), self._auth()
                    self.tunnel = netplay_tunnel.Tunnel(
                        "guest", endpoint["psk"], "127.0.0.1", 0, "", 0,
                        dial=lambda: client.open_relay("guest", auth, wait_paired=True)).start()
                    connect_address, connect_port = "127.0.0.1", self.tunnel.port
                    encrypted = True
                    relay = True
                else:
                    relay = False
                    if not self.catalog.settings()["allow_direct_connections"]:
                        raise AppError("The host chose a direct connection, which shares their address with you and yours with them. "
                                       "Allow direct connections in Settings > Privacy (or ask the host to use the relay).")
                    if not body.get("expose_address"):
                        raise AppError("Confirm that you accept exchanging addresses with the host, or ask them to use the relay.")
                    connect_address, connect_port = endpoint["address"], endpoint["port"]
                    if endpoint.get("psk"):
                        self.tunnel = netplay_tunnel.Tunnel("guest", endpoint["psk"], "127.0.0.1", 0, connect_address, connect_port).start()
                        connect_address, connect_port = "127.0.0.1", self.tunnel.port
                        encrypted = True
                command = build_guest_command(check["exe"], check["core"], game["path"], connect_address, connect_port, nick, extra)
            pid = emulators.launch_command(command)
            self._bring_forward(pid, "retroarch")
            self._note_running(pid, game["title"], "RetroArch", "retroarch")
            if room["role"] == "host":  # publish only once RetroArch is starting
                request = {"operation": "set_endpoint", "address": address, "port": port, **self._auth()}
                if relay:
                    request = {"operation": "set_endpoint", "kind": "relay", **self._auth()}
                if encrypted:
                    request["psk"] = key
                try:
                    self._call(request)
                except AppError:
                    emulators.stop_pid(pid)  # nobody can reach it anyway; do not leave it running
                    raise
        except (NetplayError, netplay_tunnel.TunnelUnavailable) as exc:
            self._close_tunnel()
            raise AppError(str(exc)) from exc
        except OSError as exc:
            self._close_tunnel()
            raise AppError(f"Could not start RetroArch: {exc}") from exc
        self.catalog.record_play(game["id"])
        room["launched"] = True
        return {"launched": game["title"], "role": room["role"], "pid": pid, "encrypted": encrypted, "relay": relay}

    def shutdown(self) -> None:
        """Called when the app window closes: leave rooms politely and drop the tunnel."""
        try:
            for sid in list(self.waits):
                self.api_mp_cancel_wait({"session_id": sid})
            if self.room is not None:
                self.api_mp_leave({})
        except AppError:
            pass
        finally:
            self._close_tunnel()

    def _close_tunnel(self) -> None:
        if self.tunnel is not None:
            self.tunnel.stop()
            self.tunnel = None

    def _launch_dolphin(self, room: dict, game: dict, check: dict, body: dict) -> dict:
        mode = body.get("mode", "traversal")
        if mode not in {"traversal", "direct"}:
            raise AppError("mode must be traversal or direct")
        # Dolphin NetPlay connects players to each other (even the traversal server only
        # introduces them), so every player learns the others' addresses. No relay exists for it.
        if not self.catalog.settings()["allow_direct_connections"]:
            raise AppError("Dolphin NetPlay shares addresses between players and cannot use the relay. "
                           "Allow direct connections in Settings > Privacy (best over a VPN such as Tailscale) to use it.")
        if not body.get("expose_address"):
            raise AppError("Confirm that you accept sharing your address with the other players.")
        try:
            if room["role"] == "host":
                state = self._call({"operation": "status", **self._auth()})["session"]["state"]
                if state not in {"ready-barrier", "active"}:
                    raise AppError("Press 'Check everyone matches' first.")
                port = body.get("port", DOLPHIN_PORT)
                address = str(body.get("address") or detect_lan_address()).strip()
                guide = dolphin_steps("host", mode=mode, address=address, port=port)
            else:
                endpoint = self._call({"operation": "get_endpoint", **self._auth()})["endpoint"]
                if not endpoint:
                    raise AppError("The host has not shared a way to connect yet. Wait for the notification.")
                mode = "traversal" if endpoint["kind"] == "code" else "direct"
                guide = dolphin_steps("guest", mode=mode, address=endpoint["address"], port=endpoint.get("port"), code=endpoint["address"])
            self._prepare_dolphin(check["exe"], game["console"])
            pid = emulators.launch_command(dolphin_open_command(check["exe"], game["path"]))
            self._bring_forward(pid, "dolphin")
            self._note_running(pid, game["title"], "Dolphin", "dolphin")
            if room["role"] == "host" and mode == "direct":
                self._call({"operation": "set_endpoint", "kind": "direct", "address": address, "port": port, **self._auth()})
        except DolphinNetplayError as exc:
            raise AppError(str(exc)) from exc
        except OSError as exc:
            raise AppError(f"Could not start Dolphin: {exc}") from exc
        self.catalog.record_play(game["id"])
        room["launched"] = True
        return {"launched": game["title"], "role": room["role"], "pid": pid, "engine": "dolphin",
                "steps": guide, "needs_code": room["role"] == "host" and mode == "traversal"}

    def api_mp_share_code(self, body: dict) -> dict:
        """Host pastes the code Dolphin's traversal server gave them."""
        if self.room is None or self.room["role"] != "host":
            raise AppError("Only the host can share a Dolphin host code.")
        self._call({"operation": "set_endpoint", "kind": "code", "address": str(body.get("code", "")).strip(), **self._auth()})
        return {"shared": True}

    def api_mp_leave(self, body: dict) -> dict:
        self._close_tunnel()
        if self.room is None:
            return {"room": None}
        try:
            if self.room["role"] == "host":
                self._call({"operation": "revoke_invites", **self._auth()})
            elif self.room["waiting"]:
                self._call({"operation": "cancel_wait", "session_id": self.room["session_id"],
                            "participant_id": self.room["me"], "request_token": self.room["waiting"]})
            else:
                self._call({"operation": "leave", **self._auth()})
        finally:
            self.room = None
        return {"room": None}

    # window lifetime (used by the packaged app so it quits when its window closes) ----------
    # calls that need no global lock: quick reads, or slow work that only touches its own cache
    UNLOCKED = frozenset({"force_quit", "server_activity", "overlay", "overlay_open", "overlay_state", "overlay_capture_pad", "game_window", "router_test", "firewall_allow", "ping", "bye", "status", "specs", "server_status", "network_last", "server_control", "rescan", "scan_everything"})

    def api_ping(self, body: dict) -> dict:
        self.last_ping, self.bye_at, self.tray_mode = time.time(), 0.0, False
        return {"ok": True, "report_prompt": self.reports.prompt(), "quitting": bool(self.quit_requested)}

    def api_status(self, body: dict) -> dict:
        """A tiny summary for the window title (shown when hovering the taskbar button). No network calls."""
        room, out = self.room, {"game": None, "room": None, "waits": []}
        if self._running_now():
            out["game"] = self.running.get("title")
        if room is not None:
            stats = (room.get("stats") or {}).get("average", {})
            session = room.get("session") or {}
            out["room"] = {"game": room["game"], "role": room["role"], "players": len(session.get("participants") or {}),
                           "max": room.get("max_players"), "ping_ms": stats.get("ping_ms"), "state": session.get("state")}
        out["waits"] = [{"game": w["game"], "position": (w.get("queue") or {}).get("position")} for w in self.waits.values()]
        return out

    def _managed_console_ids(self) -> list[str]:
        return [c.id for c in CONSOLES if c.id in CORES]

    def api_self_uninstall(self, body: dict) -> dict:
        """Uninstall Legacy Player itself. Without `confirm` it only lists what would go; with it, the doctor cleans up."""
        if not body.get("confirm"):
            plan = selfuninstall.plan(self.data_dir, self.catalog.data.get("save_root") or "",
                                      self.catalog.data.get("backup_root") or "", self._managed_console_ids())
            if firewall.exists():
                plan["items"].insert(-1, {"key": "firewall", "label": "The Windows Firewall rule for your server", "keepable": False,
                                          "why": "The door I opened so friends could connect. Windows may ask you to approve removing it.", "paths": [], "mb": 0.0})
            return plan
        why = selfuninstall.check_data_dir(self.data_dir)
        if why:
            raise AppError(why)               # checked before anything is stopped
        self.shutdown()
        server_stopped = False
        try:      # the server is its own background program; it must not be running while its folder is removed
            from server import cli
            if cli._is_running(self.data_dir / "server"):
                self.api_server_control({"action": "stop"})
                server_stopped = not cli._is_running(self.data_dir / "server")
        except (AppError, OSError):
            pass
        created = selfuninstall.created_folders(self.catalog.data.get("save_root") or "", self.catalog.data.get("backup_root") or "",
                                                self._managed_console_ids(), self.data_dir)
        keep_paths = [self._save_root(), *self.catalog.data.get("save_sources", {}).values()]
        try:
            report = selfuninstall.execute(self.data_dir, keep_saves=bool(body.get("keep_saves", True)),
                                           remove_program=bool(body.get("remove_program", True)),
                                           created=created, delete_created=bool(body.get("delete_created", False)),
                                           keep_paths=keep_paths)
        except ValueError as exc:
            raise AppError(str(exc)) from exc
        report["server_stopped"] = server_stopped
        if firewall.exists():
            gone = firewall.remove()["removed"]
            report["steps"].insert(-1 if report["steps"] and report["steps"][-1]["key"] == "program" else len(report["steps"]),
                                   {"key": "firewall", "label": "The Windows Firewall rule for your server", "status": "removed" if gone else "problem", "mb": 0.0})
            if not gone:
                report["problems"].append("the Windows Firewall rule 'Legacy Player server' (remove it in Windows Defender Firewall)")
        self._close_router_mapping()
        self.catalog.save = lambda: None      # never write the settings file back after it was removed
        return report

    def _overlay_prefs(self) -> dict:
        cur = self.catalog.data.get("overlay") or {}
        return {**overlaymod.DEFAULTS, **{k: v for k, v in cur.items() if k in overlaymod.DEFAULTS}}

    def api_overlay(self, body: dict) -> dict:
        """The overlay's settings: on/off, keyboard shortcut, controller combo. Saving applies at once."""
        if any(k in body for k in ("enabled", "hotkey", "pad", "hold")):
            try:
                self.catalog.data["overlay"] = overlaymod.validate_prefs(body, self._overlay_prefs())
            except (ValueError, TypeError) as exc:
                raise AppError(str(exc)) from exc
            self.catalog.save()
            if self.overlay_listeners is not None:
                self.overlay_listeners.start(self._overlay_prefs())
        return {**self._overlay_prefs(), "pad_buttons": [{"id": k, "label": v} for k, v in overlaymod.PAD_LABELS.items()],
                "supported": sys.platform == "win32", "listening": self.overlay_listeners is not None,
                "error": getattr(self.overlay_listeners, "error", "") or ""}

    def api_overlay_open(self, body: dict) -> dict:
        """Open the overlay, or close it if it is already open (so the same shortcut works both ways).
        It only exists while a game started from Legacy Player is running."""
        native = self.overlay_native
        if native is not None and native.is_open():
            native.close()
            return {"open": False}
        if winplace.close_titled(overlaymod.TITLE):
            return {"open": False}
        if not self._running_now():
            raise AppError("The overlay is for while a game is running. Start a game from Legacy Player first.")
        if time.time() - self._overlay_launched < 1.0:
            return {"open": True}                      # a second press while it is still starting must not undo it
        if native is not None:
            try:
                opened = native.toggle()
                self._overlay_launched = time.time()
                return {"open": opened}
            except RuntimeError:
                pass                                   # no Tk on this machine: use the browser-window version below
        opener = self.overlay_opener
        if opener is None:
            raise AppError("The overlay opens from the Windows app.")
        if opener() is False:
            raise AppError("I could not open the overlay window (Edge or Chrome is needed).")
        self._overlay_launched = time.time()
        prefs = self._display_prefs()
        winplace.pin_titled(overlaymod.TITLE, self._monitor_for(prefs["monitor"]) or next((m for m in winplace.list_monitors() if m.get("primary")), None))
        return {"open": True}

    def _overlay_view(self) -> dict:
        """What the overlay panel shows, read fresh every second."""
        running = self._running_now()
        room = self.room
        members = [n for n in ((room.get("session") or {}).get("participants") or {})] if room else []
        return {"game": ({"title": running["title"], "emulator": running["emulator"], "since": running.get("since")} if running else None),
                "room": ({"game": room.get("game"), "role": room.get("role"), "invite_code": room.get("invite_code"), "members": members} if room else None)}

    def _overlay_monitor(self) -> dict | None:
        prefs = self._display_prefs()
        return self._monitor_for(prefs["monitor"]) or next((m for m in winplace.list_monitors() if m.get("primary")), None)

    def _overlay_actions(self) -> dict:
        def window(mode: str):
            def run() -> None:
                r = self._running_now()
                if r:
                    self._bring_forward(r["pid"], r.get("emulator_id") or "", mode, explicit=True)
            return run

        def open_app() -> None:
            if self.overlay_native is not None:
                self.overlay_native.close()
            if self.show_main_window:
                self.show_main_window()
        return {"back": lambda: self.overlay_native.close(), "fullscreen": window("fullscreen"), "windowed": window("windowed"),
                "force_quit": lambda: self.api_force_quit({}), "open_app": open_app}

    def api_overlay_state(self, body: dict) -> dict:
        room = self.room
        running = self._running_now()
        return {"game": ({"title": running["title"], "emulator": running["emulator"]} if running else None),
                "room": ({"game": room.get("game"), "role": room.get("role"), "invite_code": room.get("invite_code")} if room else None),
                "hotkey": self._overlay_prefs()["hotkey"], "pad": self._overlay_prefs()["pad"]}

    def api_overlay_capture_pad(self, body: dict) -> dict:
        """Which controller buttons are held right now (the page asks a few times while you hold your combo)."""
        masks = overlaymod.read_pads()
        return {"pressed": overlaymod.names_of(max(masks, key=lambda m: bin(m).count("1"))) if masks else [], "connected": len(masks)}

    def api_game_window(self, body: dict) -> dict:
        r = self._running_now()
        if not r:
            raise AppError("No game is running from Legacy Player.")
        mode = body.get("mode")
        if mode not in ("fullscreen", "windowed"):
            raise AppError("Pick full screen or windowed.")
        self._bring_forward(r["pid"], r.get("emulator_id") or "", mode, explicit=True)
        return {"mode": mode}

    def api_force_quit(self, body: dict) -> dict:
        """Stop the running game now, even if the emulator is showing its own "are you sure?" box. No saves are written."""
        r = self._running_now()
        if not r:
            raise AppError("No game is running from Legacy Player.")
        emulators.stop_pid(r["pid"])
        self.running = None
        return {"stopped": r["title"]}

    def api_quit(self, body: dict) -> dict:
        """Full close: leave rooms politely, then stop the app."""
        self.quit_at = time.time()                       # first: the watcher must never see "quit" without the time
        self.quit_requested = True
        self.shutdown()
        return {"ok": True}

    def api_bye(self, body: dict) -> dict:
        self.bye_at = time.time() + 5  # a reload pings again within seconds and cancels this
        return {"ok": True}

    def window_closed(self, now: float, grace: float = 180.0, started: float = 0.0) -> bool:
        if self.bye_at and now > self.bye_at:
            return True
        if self.last_ping:
            return now - self.last_ping > 120.0
        return bool(started) and now - started > grace

    def should_exit(self, now: float, grace: float = 180.0, started: float = 0.0) -> bool:
        if self.quit_requested:
            return True
        if self.tray_mode:
            return False
        return self.window_closed(now, grace, started)

    # the multiplayer server this computer can run for friends ----------------------------------
    def _server_args(self, share: bool) -> argparse.Namespace:
        """The in-app server: loopback and plain for solo use; TLS with a self-signed certificate
        (fingerprint shown to the owner) whenever it is opened to other machines. Never plaintext."""
        from server.selfsigned import ensure_certificate
        state = self.data_dir / "server"
        s = self.catalog.settings()
        cert = key = None
        if share:
            cert, key, _ = ensure_certificate(state / "tls")   # instant if the startup thread already made it
        return argparse.Namespace(host="0.0.0.0" if share else "127.0.0.1", port=s["server_port"], state_dir=state,
                                  replay_dir=state / "replays", tls_cert=cert, tls_key=key,
                                  allow_insecure_remote=False, detach=True,
                                  max_players=s["server_max_players"], max_rooms=s["server_max_rooms"],
                                  max_waiting=s["server_max_waiting"])

    def _prepare_certificate(self) -> None:
        """Make the shared-server certificate once, in the background, so sharing is instant later."""
        import threading
        from server.selfsigned import ensure_certificate
        folder = self.data_dir / "server" / "tls"
        if (folder / "cert.pem").exists() or os.environ.get("LEGACY_PLAYER_NO_BACKGROUND"):
            return
        threading.Thread(target=lambda: ensure_certificate(folder), daemon=True).start()

    def server_fingerprint(self) -> str | None:
        from server.selfsigned import fingerprint_of, pretty_fingerprint
        cert = self.data_dir / "server" / "tls" / "cert.pem"
        return pretty_fingerprint(fingerprint_of(cert)) if cert.exists() else None

    def api_server_control(self, body: dict) -> dict:
        from server import cli
        action = body.get("action")
        if action not in {"start", "stop", "restart", "status"}:
            raise AppError("Unknown server action.")
        args = self._server_args(bool(body.get("share")) and action != "status")
        out = io.StringIO()
        try:
            # slow (it waits for the server): holds only its own lock, so the rest of the app keeps answering
            with self._server_op_lock, contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = {"start": cli.start, "stop": cli.stop, "restart": cli.restart, "status": cli.status}[action](args)
        except (OSError, ConnectionError, ValueError) as exc:
            raise AppError(f"The server did not respond: {exc}") from exc
        message = " ".join(out.getvalue().split()) or ("Done." if code == 0 else "That did not work.")
        if code != 0 and action != "status":
            self.reports.capture("server-control-failed", None, message, {"action": action, "shared": bool(body.get("share"))})
            raise AppError(message)
        with self.api_lock:        # settings are shared state, so only this short part takes the big lock
            # first, before the (slow) router step: the moment the server answers in TLS the app must talk TLS to it,
            # or every call in between is cut off ("connection aborted")
            if args.tls_cert and body.get("share") and action in {"start", "restart"} and code == 0:
                self.catalog.set_setting("server_tls", True)
                self.catalog.set_setting("server_fingerprint", self.server_fingerprint() or "-")
            elif action in {"start", "restart"} and code == 0 and not body.get("share"):
                self.catalog.set_setting("server_tls", False)
        if code == 0:
            if action == "stop":
                self._user_stopped = True                  # no auto-start behind the player's back
                self.catalog.data["server_share_wanted"] = False
                self.catalog.set_setting("server_tls", False)
            elif action in {"start", "restart"}:
                self._user_stopped = False
                self.catalog.data["server_share_wanted"] = bool(body.get("share"))
                self.catalog.save()
        reach = self._manage_router(action, code, bool(body.get("share")), args.port)
        return {"message": message, "running": cli._is_running(args.state_dir), "shared": bool(body.get("share")),
                "log": str(args.state_dir / "server.log"), "fingerprint": self.server_fingerprint(),
                "limits": {"players": args.max_players, "rooms": args.max_rooms, "waiting": args.max_waiting}, "reach": reach}

    def _fallback_code(self) -> str:
        s = self.catalog.settings()
        if not s.get("server_use_fallback", True):
            return ""
        return (s.get("fallback_server_code") or PUBLIC_SERVER_CODE or "").strip()

    def _manage_router(self, action: str, code: int, share: bool, port: int) -> dict | None:
        """Open the server port on the home router when sharing starts (and close it when the server stops). When the
        router cannot be opened, meet friends on the shared server instead, if one is set."""
        old = self.port_map
        if action in {"stop", "restart"} and code == 0:
            self._renew_stop.set()
            if old.get("state") == "mapped":
                portmap.close_port(old.get("port", port), old.get("location", ""))
            self._forget_router_mapping()
            was_fallback = self.fallback_active
            self.port_map, self.fallback_active = {}, False
            if was_fallback:
                with self.api_lock:
                    self.api_server_connect({"local": True})
        if action in {"start", "restart"} and code == 0 and share and self.catalog.settings().get("server_auto_open", True):
            self._close_router_mapping()                      # a mapping left by a crashed run goes first
            self.port_map = portmap.open_port(port)
            if self.port_map["state"] == "mapped":
                self.catalog.data["router_mapped"] = {"port": self.port_map.get("port", port), "location": self.port_map.get("location", ""),
                                                      "local_ip": self.port_map.get("local_ip", ""), "external_ip": self.port_map.get("external_ip", "")}
                self.catalog.save()
                self._start_router_renewal(self.port_map)
                self.fallback_active = False
                return self.port_map
            self.reports.capture("router-not-opened", None, self.port_map["message"],
                                 {"state": self.port_map["state"], "kind": self.port_map.get("kind", "")})
            fallback = self._fallback_code()
            if fallback:
                try:
                    with self.api_lock:
                        joined = self.api_server_connect({"code": fallback})
                except AppError as exc:
                    joined = {"connected": False, "message": str(exc)}
                self.fallback_active = bool(joined.get("connected"))
                self.port_map = {**self.port_map, "fallback": self.fallback_active,
                                 "message": ("Your connection can't be reached from outside, so Legacy Player moved you to the shared server. "
                                             "Give friends the code shown under Invite friends; room invite codes work as usual.")
                                 if self.fallback_active else self.port_map["message"] + " The shared server did not answer either."}
            return self.port_map
        return self.port_map or None

    _renew_stop = threading.Event()

    def _start_router_renewal(self, mapping: dict) -> None:
        """Keep the timed router mapping alive while the server runs; if the app dies the router drops it by itself."""
        self._renew_stop.set()
        stop = self._renew_stop = threading.Event()

        def loop() -> None:
            from urllib.parse import urlparse
            while not stop.wait(portmap.RENEW_SECONDS):
                location = str(mapping.get("location", ""))
                try:
                    mine = portmap._local_address_towards(urlparse(location).hostname or "") or str(mapping.get("local_ip", ""))
                except OSError:
                    mine = str(mapping.get("local_ip", ""))
                ok = portmap.renew_port(int(mapping.get("port", 0)), location, mine)
                if not ok:
                    self.port_map = {**self.port_map, "renew_failed": True,
                                     "message": "Your router stopped keeping the port open (it may have restarted). Press Test my router, or restart the server."}
                elif self.port_map.get("renew_failed"):
                    self.port_map = {k: v for k, v in self.port_map.items() if k != "renew_failed"}
        threading.Thread(target=loop, daemon=True, name="router-renew").start()

    def _tidy_old_router_mapping(self) -> None:
        """A port opened by an earlier run that crashed: close it, unless the server it was for is still running."""
        try:
            from server import cli
            if not cli._is_running(self.data_dir / "server"):
                self._close_router_mapping()
                return
            rec = self.catalog.data.get("router_mapped") or {}
            if rec.get("location") and rec.get("port"):       # the server outlived the app: keep its port open again
                self.port_map = {"state": "mapped", "port": int(rec["port"]), "location": rec["location"], "local_ip": rec.get("local_ip", ""),
                                 "external_ip": rec.get("external_ip", ""), "kind": "public", "message": "Port still open on your router."}
                self._start_router_renewal(self.port_map)
        except Exception:
            pass

    def _forget_router_mapping(self) -> None:
        if self.catalog.data.get("router_mapped"):
            self.catalog.data["router_mapped"] = {}
            self.catalog.save()

    def _close_router_mapping(self) -> None:
        """Close any port this app opened on the router and has not closed (after a crash, or when uninstalling)."""
        rec = self.catalog.data.get("router_mapped") or {}
        if rec.get("location") and rec.get("port"):
            try:
                portmap.close_port(int(rec["port"]), str(rec["location"]))
            except (OSError, ValueError):
                pass
        self._forget_router_mapping()

    def api_router_test(self, body: dict) -> dict:
        """Does this router let the app open a port? Opens the server port and closes it again straight away."""
        port = self.catalog.settings()["server_port"]
        result = portmap.open_port(port)
        if result["state"] == "mapped" and not (self.port_map.get("state") == "mapped"):
            portmap.close_port(port, result["location"])
        return {**result, "fallback_available": bool(self._fallback_code())}

    def api_firewall_status(self, body: dict) -> dict:
        return firewall.status(self.catalog.settings()["server_port"])

    def api_firewall_allow(self, body: dict) -> dict:
        if not body.get("consent"):
            raise AppError("Windows will ask you to approve this change. Press the button again to continue.")
        return firewall.allow(self.catalog.settings()["server_port"])

    def api_server_code(self, body: dict) -> dict:
        """The short code a friend types to reach the server this app shares. `refresh` makes a fresh one: the old
        code stops working for new people, while everyone already connected stays connected."""
        from . import servercode
        from server import cli
        from server.selfsigned import fingerprint_of
        cert = self.data_dir / "server" / "tls" / "cert.pem"
        if not cert.exists():
            raise AppError("Start the server with 'Let friends connect' on first; that makes its certificate.")
        state = self.data_dir / "server"
        s = self.catalog.settings()
        if self.fallback_active and self._fallback_code():
            return {"code": self._fallback_code(), "address": s["server_host"], "port": s["server_remote_port"], "fingerprint": s.get("server_fingerprint"),
                    "rotated": False, "reach": "Your own connection can't be reached from outside, so you and your friends meet on the shared server. This is its code.",
                    "reach_state": "fallback"}
        rotated = False
        if body.get("refresh"):
            try:
                cli._admin_call(state, "admin_rotate_key")
                rotated = True
            except (OSError, ConnectionError, ValueError) as exc:
                raise AppError("The server has to be running to make a fresh code. Start it first.") from exc
        key = self._own_server_key()
        s = self.catalog.settings()
        mapped = self.port_map.get("external_ip") if self.port_map.get("state") == "mapped" else ""
        address = str(body.get("address") or s["server_public_address"] or mapped or detect_lan_address()).strip()
        try:
            code = servercode.encode(address, s["server_port"], fingerprint_of(cert), key)
        except servercode.CodeError as exc:
            return {"code": None, "address": address, "port": s["server_port"], "error": str(exc),
                    "fingerprint": self.server_fingerprint()}
        return {"code": code, "address": address, "port": s["server_port"], "fingerprint": self.server_fingerprint(), "rotated": rotated,
                "reach": self.port_map.get("message") or "Friends on your home network or VPN can use this code. Start the server with 'Let friends connect' and the app will try to open your router for friends on the internet.",
                "reach_state": self.port_map.get("state", "")}

    def api_server_connect(self, body: dict) -> dict:
        """Point this app at a friend's server using their short code (or leave it at this computer)."""
        from . import servercode
        if body.get("local"):
            for key, value in (("server_host", "127.0.0.1"), ("server_tls", False), ("server_fingerprint", "-"), ("server_access_key", "")):
                self.catalog.set_setting(key, value)
            return {"connected": self.api_server_status({}).get("online", False), "host": "this computer"}
        try:
            found = servercode.decode(str(body.get("code", "")))
        except servercode.CodeError as exc:
            raise AppError(str(exc)) from exc
        keys = ("server_host", "server_remote_port", "server_tls", "server_fingerprint", "server_access_key")
        before = {k: self.catalog.settings()[k] for k in keys}
        for key, value in (("server_host", found["host"]), ("server_remote_port", found["port"]),
                           ("server_tls", True), ("server_fingerprint", found["fingerprint"]), ("server_access_key", found.get("key", ""))):
            self.catalog.set_setting(key, value)

        def undo(message: str) -> dict:                   # a wrong code must not leave the app pointed at a dead server
            for k, v in before.items():
                self.catalog.set_setting(k, v)
            return {"connected": False, "host": found["host"], "message": message + " Nothing was changed: you are still on your previous server."}
        status = self.api_server_status({})
        if status.get("online"):      # the key is only checked on browse/create/join, so ask for something it guards
            try:
                self._client().call({"operation": "browse"})
            except LobbyClientError as exc:
                return undo(str(exc))
        if not status.get("online"):
            return undo(status.get("message") or "That server did not answer. Check the code, and that the host has started it with 'Let friends connect'.")
        return {"connected": True, "host": found["host"]}

    def api_server_status(self, body: dict) -> dict:
        try:
            self._client().call({"operation": "status", "session_id": "probe", "participant_id": "probe", "credential": "probe"})
        except LobbyClientError as exc:
            if "unknown session" in str(exc):
                return {"online": True}
            return {"online": False, "message": str(exc)}
        return {"online": True}
