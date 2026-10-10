"""Steam and Epic Games library entries, and launching them through their own launchers.

Read-only: this looks at the small text files Steam and the Epic Games Launcher keep about installed games
(appmanifest_*.acf and *.item). It never opens a game's own files, never signs in and never sends anything.
A game starts the way the launcher itself would start it: steam://rungameid/<id> or the Epic launch address, so the
client does its own updates, sign-in and anti-cheat."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

NOT_GAMES = ("steamworks common redistributables", "steam linux runtime", "proton ", "steam controller configs", "steamvr")


def _steam_root(env: dict | None = None) -> Path | None:
    env = env if env is not None else os.environ
    candidates: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key, name in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        candidates.append(Path(winreg.QueryValueEx(k, name)[0]))
                except OSError:
                    pass
        except ImportError:
            pass
    for var in ("ProgramFiles(x86)", "ProgramFiles"):
        if env.get(var):
            candidates.append(Path(env[var]) / "Steam")
    if env.get("STEAM_ROOT"):
        candidates.insert(0, Path(env["STEAM_ROOT"]))
    for c in candidates:
        if (c / "steamapps").is_dir():
            return c
    return None


def _acf_value(text: str, key: str) -> str:
    m = re.search(r'"%s"\s+"([^"]*)"' % re.escape(key), text, re.I)
    return m.group(1) if m else ""


def steam_games(env: dict | None = None) -> list[dict]:
    root = _steam_root(env)
    if root is None:
        return []
    libraries = [root]
    try:
        vdf = (root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'"path"\s+"([^"]+)"', vdf):
            path = Path(m.group(1).replace("\\\\", "\\"))
            if path not in libraries:
                libraries.append(path)
    except OSError:
        pass
    games: dict[str, dict] = {}
    for lib in libraries:
        try:
            manifests = sorted((lib / "steamapps").glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            appid, name = _acf_value(text, "appid"), _acf_value(text, "name")
            if not appid.isdigit() or not name or name.lower().startswith(NOT_GAMES):
                continue
            state = _acf_value(text, "StateFlags")
            if state.isdigit() and not int(state) & 4:        # bit 4 = fully installed
                continue
            size = _acf_value(text, "SizeOnDisk")
            games[appid] = {"store": "steam", "key": appid, "title": name, "uri": f"steam://rungameid/{appid}",
                            "size": int(size) if size.isdigit() else 0}
    return list(games.values())


def epic_games(env: dict | None = None) -> list[dict]:
    env = env if env is not None else os.environ
    base = env.get("EPIC_MANIFESTS") or (str(Path(env.get("ProgramData", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"))
    folder = Path(base)
    games: list[dict] = []
    try:
        items = sorted(folder.glob("*.item"))
    except OSError:
        return []
    for item in items:
        try:
            data = json.loads(item.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        name, app = str(data.get("DisplayName") or ""), str(data.get("AppName") or "")
        if not name or not app or data.get("bIsIncompleteInstall"):
            continue
        cats = data.get("AppCategories")
        if isinstance(cats, list) and cats and "games" not in cats:
            continue
        main = data.get("MainGameAppName")
        if main and main != app:                               # add-on content, not a game of its own
            continue
        ns, cid = str(data.get("CatalogNamespace") or ""), str(data.get("CatalogItemId") or "")
        uri = f"com.epicgames.launcher://apps/{ns}%3A{cid}%3A{app}?action=launch&silent=true" if ns and cid else \
              f"com.epicgames.launcher://apps/{app}?action=launch&silent=true"
        games.append({"store": "epic", "key": app, "title": name, "uri": uri, "size": int(data.get("InstallSize") or 0)})
    return games


def installed_games(env: dict | None = None) -> list[dict]:
    return steam_games(env) + epic_games(env)


def library_entries(env: dict | None = None) -> list[dict]:
    """The games in the same shape the library uses for files on disk."""
    out = []
    for g in installed_games(env):
        title = g["title"]
        out.append({
            "id": f"{g['store']}-{re.sub(r'[^A-Za-z0-9]+', '', g['key'])[:40]}", "console": "pc", "title": title,
            "sort_title": re.sub(r"^(the|a|an) ", "", title.lower()), "region": "", "tags": [g["store"].title()],
            "path": g["uri"], "root": g["store"], "size": g["size"], "extension": "." + g["store"], "is_archive": False,
            "compat_id": f"pc:{g['store']}:{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}",
        })
    return out


def launch(uri: str) -> None:
    """Hand the launch address to Windows, which gives it to Steam or the Epic launcher."""
    if not (uri.startswith("steam://rungameid/") or uri.startswith("com.epicgames.launcher://apps/")):
        raise ValueError("Not a Steam or Epic launch address.")
    if sys.platform != "win32":
        raise OSError("Steam and Epic games start from Windows.")
    os.startfile(uri)      # noqa: S606 - the address was checked above


def image_size(data: bytes) -> tuple[int, int] | None:
    """Width and height of a PNG or JPEG from its header, without decoding it (nothing outside the standard library)."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        if data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                length = int.from_bytes(data[i + 2:i + 4], "big")
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
                i += 2 + length
    except (IndexError, ValueError):
        pass
    return None


def _portrait(data: bytes) -> bool:
    size = image_size(data)
    return bool(size) and size[1] > size[0] * 1.2          # a tall picture (600x900 or 300x450), not the wide header or hero


def steam_art(appid: str, env: dict | None = None, limit: int = 1_500_000) -> bytes | None:
    """Steam's own picture for an installed game, read from the copy Steam already keeps on this computer. Nothing is
    downloaded. Steam has used three layouts over the years, and all three are read:

      appcache/librarycache/<appid>_library_600x900.jpg              (older clients)
      appcache/librarycache/<appid>/<hash>/library_600x900.jpg       (2024 clients: a folder per game, one per version)
      appcache/librarycache/<appid>/<hash>.jpg                        (newest clients: files named by content, so the tall one
                                                                        is told apart from the wide header by its shape)
    A picture the player chose in Steam (userdata/<account>/config/grid/<appid>p.*) wins over all of them."""
    root = _steam_root(env)
    if root is None or not str(appid).isdigit():
        return None
    appid = str(appid)

    def read(path: Path) -> bytes | None:
        try:
            if path.is_file() and 0 < path.stat().st_size <= limit:
                return path.read_bytes()
        except OSError:
            pass
        return None

    try:                                                    # the player's own choice inside Steam
        for grid in sorted((root / "userdata").glob("*/config/grid")):
            for ext in ("png", "jpg", "jpeg", "webp"):
                data = read(grid / f"{appid}p.{ext}")
                if data:
                    return data
    except OSError:
        pass
    cache = root / "appcache" / "librarycache"
    named = ("library_600x900.jpg", "library_600x900_2x.jpg", "library_capsule.jpg", "library_capsule_2x.jpg",
             "library_600x900.png", "library_capsule.png")
    for n in named:                                         # old flat names, then the per-game folders
        data = read(cache / f"{appid}_{n}")
        if data:
            return data
    folder = cache / appid
    if folder.is_dir():
        try:
            for n in named:
                for path in sorted(folder.rglob(n)):
                    data = read(path)
                    if data:
                        return data
            tall: list[tuple[int, bytes]] = []
            for path in sorted(folder.rglob("*")):            # content-named files: keep the tallest, biggest one
                if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                    continue
                data = read(path)
                if data and _portrait(data):
                    tall.append((len(data), data))
            if tall:
                return max(tall, key=lambda t: t[0])[1]
        except OSError:
            pass
    for n in ("header.jpg", "library_header.jpg", "library_hero.jpg"):   # last resort: the wide picture
        data = read(cache / f"{appid}_{n}")
        if data:
            return data
        if folder.is_dir():
            try:
                for path in sorted(folder.rglob(n)):
                    data = read(path)
                    if data:
                        return data
            except OSError:
                pass
    return None


def steam_hidden(env: dict | None = None) -> set[str]:
    """App ids the player marked as hidden inside Steam (Manage > Hide this game). Steam keeps that choice in
    userdata/<account>/7/remote/sharedconfig.vdf; read-only, names only."""
    root = _steam_root(env)
    hidden: set[str] = set()
    if root is None:
        return hidden
    try:
        files = list((root / "userdata").glob("*/7/remote/sharedconfig.vdf")) + list((root / "userdata").glob("*/config/localconfig.vdf"))
    except OSError:
        return hidden
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # "123456" { ... "Hidden" "1" ... }   (each app's block is small; a block is cut at the next app id)
        for m in re.finditer(r'"(\d+)"\s*\{((?:[^{}]|\{[^{}]*\})*)\}', text):
            if re.search(r'"Hidden"\s+"1"', m.group(2), re.I):
                hidden.add(m.group(1))
    return hidden


def steam_diagnostics(env: dict | None = None) -> dict:
    """Why Steam games do or do not show: where Steam is, which libraries it lists and how many games were found."""
    root = _steam_root(env)
    out: dict = {"found": root is not None, "root": str(root) if root else "", "libraries": [], "manifests": 0, "games": 0}
    if root is None:
        return out
    libraries = [root]
    try:
        vdf = (root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'"path"\s+"([^"]+)"', vdf):
            path = Path(m.group(1).replace("\\\\", "\\"))
            if path not in libraries:
                libraries.append(path)
    except OSError:
        pass
    for lib in libraries:
        try:
            n = len(list((lib / "steamapps").glob("appmanifest_*.acf")))
        except OSError:
            n = 0
        out["libraries"].append({"path": str(lib), "manifests": n, "exists": (lib / "steamapps").is_dir()})
        out["manifests"] += n
    out["games"] = len(steam_games(env))
    return out


def match_key(text: str) -> str:
    """"Hades II (2024).png" and "hades ii" meet in the middle."""
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"\s*[\(\[].*?[\)\]]", "", str(text).lower()))
