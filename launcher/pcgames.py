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
    if sys.platform == "win32" and env is os.environ:
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
