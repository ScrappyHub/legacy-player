"""Fetch emulators from their official GitHub releases, only when the user says so.

Consent model
- Nothing here runs unless the user turned on "Allow internet downloads" in Settings AND
  pressed the Get button for a specific engine (the request carries confirm=true).
- Hosts are allow-listed: api.github.com, github.com, objects.githubusercontent.com and
  release-assets.githubusercontent.com (where GitHub now serves release files from).
  A redirect anywhere else, or to plain http, is refused. Only the exact repositories in
  launcher/engines.py.
- Archives are unpacked with path-escape checks into Legacy Player's own folder. Nothing
  is executed after install. GitHub does not publish checksums for most of these, so
  integrity rests on TLS to GitHub; the UI says so.

Updates
- The release tag is recorded in `<engine>/.lp-version`. When it already equals the latest
  tag the engine is not downloaded again (the job reports it as up to date).
- An update never loses what the player keeps in the engine's folder: everything in the old
  folder that the new package does not contain is carried over (saves, settings, firmware,
  installed games, memory cards...), and the names in ENGINE_KEEP keep the player's copy
  even when the package ships one. If anything fails, the old folder is put back.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .engines import ENGINES
from .setup import SetupError, extract_7z, has_files, replace_folder

GITHUB_HOSTS = {"api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
MAX_UNPACKED_BYTES = 4 * 1024 ** 3
VERSION_FILE = ".lp-version"
# The player's own files: everything the new package does not contain is carried over on an update anyway; for these
# names the player's copy also wins when the new package happens to ship one (a default config, an empty folder...).
PLAYER_DATA = ("User", "user", "saves", "states", "memcards", "portable.txt", "portable.ini", "config", "retroarch.cfg", "sys_config")
ENGINE_KEEP: dict[str, tuple[str, ...]] = {
    "pcsx2": ("bios", "inis", "sstates", "memcards", "snaps", "cheats", "covers", "gamesettings", "inputprofiles", "logs",
              "textures", "videos", "cache", "portable.ini", "portable.txt"),
    "ppsspp": ("memstick", "installed.txt", "portable.txt"),
    "rpcs3": ("dev_hdd0", "dev_hdd1", "dev_flash", "dev_flash2", "dev_flash3", "dev_usb000", "dev_bdvd", "config", "GuiConfigs",
              "savestates", "captures", "patches", "games.yml", "cache", "data", "logs"),
    "melonds": ("melonDS.ini", "melonDS.toml", "bios7.bin", "bios9.bin", "firmware.bin", "dsi_bios7.bin", "dsi_bios9.bin",
                "dsi_firmware.bin", "dsi_nand.bin"),
    "mgba": ("config.ini", "qt.ini", "portable.ini", "cheats", "screenshots"),
    "duckstation": ("portable.txt", "settings.ini", "bios", "memcards", "savestates", "cache", "covers", "gamesettings",
                    "inputprofiles", "screenshots", "textures", "cheats"),
    "azahar": ("user",),
    "xemu": ("xemu.toml", "xemu.ini"),
    "xenia": ("portable.txt", "xenia-canary.config.toml", "xenia.config.toml", "content", "cache", "cache_host"),
    "snes9x": ("snes9x.conf", "Saves", "Cheats", "Screenshots", "SPCs", "BIOS"),
    "bsnes": ("settings.bml", "Saves", "Firmware"),
    "mesen": ("settings.json", "Saves", "SaveStates", "Firmware", "Screenshots", "Settings"),
}
MAX_ASSET_BYTES = 400 * 1024 * 1024


def keep_list(engine_id: str) -> tuple[str, ...]:
    return PLAYER_DATA + ENGINE_KEEP.get(engine_id, ())


def installed_version(folder: Path) -> str:
    """The release tag Legacy Player recorded when it installed this engine, or "" when unknown."""
    try:
        return (Path(folder) / VERSION_FILE).read_text(encoding="utf-8").strip()[:120]
    except (OSError, UnicodeDecodeError):
        return ""


class InstallError(RuntimeError):
    pass


class _AllowedHosts(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts: set[str]) -> None:
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlparse
        if urlparse(newurl).hostname not in self.hosts or urlparse(newurl).scheme != "https":
            raise InstallError("The download was redirected off GitHub, so it was refused.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, hosts: set[str], allow_http: bool = False, timeout: float = 30):
    from urllib.parse import urlparse
    parts = urlparse(url)
    if parts.hostname not in hosts or (parts.scheme != "https" and not allow_http):
        raise InstallError("Only official GitHub release downloads over https are allowed.")
    opener = urllib.request.build_opener(_AllowedHosts(hosts))
    request = urllib.request.Request(url, headers={"User-Agent": "LegacyPlayer", "Accept": "application/vnd.github+json"})
    try:
        return opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise InstallError(f"GitHub answered {exc.code} for {parts.path}.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise InstallError(f"Could not reach GitHub ({getattr(exc, 'reason', exc)}).") from exc


def latest_release(repo: str, api_base: str = "https://api.github.com", hosts: set[str] = GITHUB_HOSTS,
                   allow_http: bool = False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise InstallError("bad repository name")
    with _open(f"{api_base}/repos/{repo}/releases/latest", hosts, allow_http) as response:
        data = json.loads(response.read(2_000_000))
    assets = [{"name": a["name"], "url": a["browser_download_url"], "size": int(a.get("size") or 0),
               "sha256": str(a.get("digest") or "").removeprefix("sha256:")}
              for a in data.get("assets", []) if isinstance(a, dict)]
    return {"tag": data.get("tag_name", ""), "assets": assets, "page": data.get("html_url", ""),
            "name": data.get("name") or "", "published_at": data.get("published_at") or "",
            "prerelease": bool(data.get("prerelease"))}


def pick_asset(assets: list[dict], pattern: str) -> dict | None:
    return next((a for a in assets if re.search(pattern, a["name"])), None)


def extract_zip_safe(archive: Path, dest: Path) -> int:
    count = 0
    with zipfile.ZipFile(archive) as z:
        if sum(m.file_size for m in z.infolist()) > MAX_UNPACKED_BYTES:
            raise InstallError("The archive would unpack to far more than an emulator needs, so it was refused.")
        for member in z.infolist():
            if member.is_dir():
                continue
            target = (dest / member.filename).resolve()
            if dest.resolve() not in target.parents:
                raise InstallError("The archive tried to write outside its folder and was refused.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    return count


class EngineInstaller:
    """Downloads run one at a time. The job snapshot carries, besides the progress fields:
    - "results": engine id -> "installed" | "up_to_date" | "failed" for every engine handled by this job
    - "up_to_date": the engine ids that were already on the latest release, so nothing was downloaded
    - "versions": engine id -> the release tag now installed"""

    def __init__(self, install_root: Path, api_base: str = "https://api.github.com", hosts: set[str] = GITHUB_HOSTS,
                 allow_http: bool = False) -> None:
        self.install_root = Path(install_root)
        self.api_base, self.hosts, self.allow_http = api_base, hosts, allow_http
        self.lock = threading.Lock()
        self.job = self._fresh_job("idle", None, "")
        self.on_done = None          # called (no arguments) each time an engine finishes, so the app looks for programs again

    @staticmethod
    def _fresh_job(state: str, engine: str | None, step: str) -> dict:
        return {"state": state, "engine": engine, "step": step, "percent": 0, "log": [], "error": None, "path": None,
                "page": None, "results": {}, "up_to_date": [], "versions": {}}

    def _finished(self) -> None:
        fn = self.on_done
        if fn is not None:
            try:
                fn()
            except Exception:
                pass

    def snapshot(self) -> dict:
        with self.lock:
            return {**self.job, "log": list(self.job["log"]), "results": dict(self.job["results"]),
                    "up_to_date": list(self.job["up_to_date"]), "versions": dict(self.job["versions"])}

    def _set(self, **kw) -> None:
        with self.lock:
            self.job.update(kw)

    def _log(self, text: str) -> None:
        with self.lock:
            self.job["log"].append(text)
            del self.job["log"][:-40]

    def _result(self, engine_id: str, outcome: str, tag: str = "") -> None:
        with self.lock:
            self.job["results"][engine_id] = outcome
            if outcome == "up_to_date" and engine_id not in self.job["up_to_date"]:
                self.job["up_to_date"].append(engine_id)
            if tag:
                self.job["versions"][engine_id] = tag

    def start(self, engine_id: str, *, consent: bool, run_inline: bool = False, skip_current: bool = False) -> dict:
        """skip_current: do nothing when the recorded version is already the latest (a single Get press reinstalls,
        which also repairs a damaged copy)."""
        spec = ENGINES.get(engine_id)
        if spec is None or spec["source"]["kind"] != "github":
            raise InstallError("That engine has no automatic download; use its official page.")
        if not consent:
            raise InstallError("Downloads are off. Turn on 'Allow internet downloads' in Settings and confirm.")
        with self.lock:
            if self.job["state"] == "running":
                raise InstallError("Another download is running.")
            self.job = self._fresh_job("running", engine_id, "Asking GitHub for the latest release")
        if run_inline:
            self._run(engine_id, spec, True, skip_current)
        else:
            threading.Thread(target=self._run, args=(engine_id, spec, True, skip_current), daemon=True).start()
        return self.snapshot()

    def start_many(self, engine_ids: list[str], *, consent: bool, run_inline: bool = False, skip_current: bool = True) -> dict:
        """Engines already on their latest release are skipped (see "up_to_date" in the snapshot)."""
        if not consent:
            raise InstallError("Downloads are off. Turn on 'Allow internet downloads' in Settings and confirm.")
        todo = [e for e in engine_ids if e in ENGINES and ENGINES[e]["source"]["kind"] == "github"]
        if not todo:
            raise InstallError("Nothing to fetch: every engine with an official download is already here.")
        with self.lock:
            if self.job["state"] == "running":
                raise InstallError("Another download is running.")
            self.job = self._fresh_job("running", todo[0], f"Fetching {len(todo)} engines")

        def run_all() -> None:
            failures = []
            for engine_id in todo:
                self._set(engine=engine_id, percent=0)
                self._run(engine_id, ENGINES[engine_id], final=False, skip_current=skip_current)
                if self.snapshot()["error"]:
                    failures.append(f"{ENGINES[engine_id]['name']}: {self.snapshot()['error']}")
                    self._set(error=None)
            results = self.snapshot()["results"]
            if failures:
                self._set(state="error", step="Finished with problems", error="; ".join(failures)[:600])
            elif all(results.get(e) == "up_to_date" for e in todo):
                self._set(state="done", step="Already up to date", percent=100)
            else:
                self._set(state="done", step="All engines installed", percent=100)
            self._finished()
        if run_inline:
            run_all()
        else:
            threading.Thread(target=run_all, daemon=True).start()
        return self.snapshot()

    def _run(self, engine_id: str, spec: dict, final: bool = True, skip_current: bool = False) -> None:
        tag = ""
        try:
            release = latest_release(spec["source"]["repo"], self.api_base, self.hosts, self.allow_http)
            tag = str(release["tag"] or "")
            dest = self.install_root / engine_id
            have = installed_version(dest) if dest.is_dir() else ""
            if skip_current and tag and have == tag and has_files(dest):
                self._result(engine_id, "up_to_date", tag)
                self._log(f"{spec['name']} {tag} is already installed; nothing was downloaded.")
                self._set(step="Already up to date", percent=100, path=str(dest), **({"state": "done"} if final else {}))
                return
            asset = pick_asset(release["assets"], spec["source"]["asset"])
            if asset is None:
                names = ", ".join(a["name"] for a in release["assets"][:8]) or "no files at all"
                self._set(page=spec["source"].get("page") or release["page"] or f"https://github.com/{spec['source']['repo']}/releases")
                raise InstallError(f"The latest {spec['name']} release ({release['tag']}) has no Windows package this app recognises "
                                   f"(it offers: {names}). Open the release page and download it yourself, then add its folder under Emulators.")
            if asset["size"] > MAX_ASSET_BYTES:
                raise InstallError("That package is larger than expected, so it was refused.")
            self._log(f"{spec['name']} {release['tag']}: {asset['name']} ({asset['size'] // (1024 * 1024)} MB) from {spec['source']['repo']}")
            self._set(step=f"Downloading {asset['name']}")
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / asset["name"]
                digest = hashlib.sha256()
                with _open(asset["url"], self.hosts, self.allow_http, timeout=60) as response, open(archive, "wb") as out:
                    done = 0
                    total = asset["size"] or int(response.headers.get("Content-Length") or 0)
                    while chunk := response.read(256 * 1024):
                        done += len(chunk)
                        if done > MAX_ASSET_BYTES:
                            raise InstallError("The download exceeded its size limit and was stopped.")
                        out.write(chunk)
                        digest.update(chunk)
                        if total:
                            self._set(percent=int(80 * done / total))
                if asset["size"] and done != asset["size"]:
                    raise InstallError("The download is not the size GitHub lists for it (it may have been cut short), so nothing was installed.")
                if asset.get("sha256") and digest.hexdigest() != asset["sha256"].lower():
                    raise InstallError("The download does not match the checksum GitHub lists for it, so nothing was installed.")
                self._set(step="Unpacking", percent=85)
                staging = Path(tmp) / "unpacked"
                try:
                    if archive.suffix.lower() == ".zip":
                        extract_zip_safe(archive, staging)
                    else:
                        extract_7z(archive, staging, spec["name"])
                except SetupError as exc:
                    raise InstallError(str(exc)) from exc
                # What goes in place is worked out and checked before the installed copy is touched.
                inner = list(staging.iterdir()) if staging.is_dir() else []
                root = inner[0] if len(inner) == 1 and inner[0].is_dir() and not inner[0].is_symlink() else staging
                if not has_files(root):
                    raise InstallError(f"The {spec['name']} package unpacked to nothing, so the installed copy was left alone.")
                self._set(step="Installing", percent=92)
                try:
                    replace_folder(root, dest, keep_list(engine_id), spec["name"])
                except SetupError as exc:
                    raise InstallError(str(exc)) from exc
            if tag:
                try:
                    (dest / VERSION_FILE).write_text(tag + "\n", encoding="utf-8")
                except OSError:
                    pass                                       # only means the next "update everything" downloads it again
            self._result(engine_id, "installed", tag)
            self._set(step="Installed", percent=100, path=str(dest), **({"state": "done"} if final else {}))
            self._log(f"Installed {spec['name']} {tag} into {dest}. Nothing was run.".replace("  ", " "))
        except InstallError as exc:
            self._result(engine_id, "failed", "")
            self._set(error=str(exc), step="Stopped", **({"state": "error"} if final else {}))
            self._log(f"Stopped: {exc}")
        except Exception as exc:
            self._result(engine_id, "failed", "")
            self._set(error=f"Unexpected problem: {type(exc).__name__}", step="Stopped", **({"state": "error"} if final else {}))
        finally:
            if final:
                self._finished()
