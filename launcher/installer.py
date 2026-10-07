"""Fetch emulators from their official GitHub releases, only when the user says so.

Consent model
- Nothing here runs unless the user turned on "Allow internet downloads" in Settings AND
  pressed the Get button for a specific engine (the request carries confirm=true).
- Hosts are allow-listed: api.github.com, github.com and objects.githubusercontent.com.
  A redirect anywhere else is refused. Only the exact repositories in launcher/engines.py.
- Archives are unpacked with path-escape checks into Legacy Player's own folder. Nothing
  is executed after install. GitHub does not publish checksums for most of these, so
  integrity rests on TLS to GitHub; the UI says so.
"""
from __future__ import annotations

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
from .setup import SetupError, extract_7z

GITHUB_HOSTS = {"api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
PLAYER_DATA = ("User", "saves", "states", "memcards", "portable.txt", "config", "retroarch.cfg", "sys_config")   # kept across an update
MAX_ASSET_BYTES = 400 * 1024 * 1024


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
    def __init__(self, install_root: Path, api_base: str = "https://api.github.com", hosts: set[str] = GITHUB_HOSTS,
                 allow_http: bool = False) -> None:
        self.install_root = Path(install_root)
        self.api_base, self.hosts, self.allow_http = api_base, hosts, allow_http
        self.lock = threading.Lock()
        self.job = {"state": "idle", "engine": None, "step": "", "percent": 0, "log": [], "error": None, "path": None}

    def snapshot(self) -> dict:
        with self.lock:
            return {**self.job, "log": list(self.job["log"])}

    def _set(self, **kw) -> None:
        with self.lock:
            self.job.update(kw)

    def _log(self, text: str) -> None:
        with self.lock:
            self.job["log"].append(text)
            del self.job["log"][:-40]

    def start(self, engine_id: str, *, consent: bool, run_inline: bool = False) -> dict:
        spec = ENGINES.get(engine_id)
        if spec is None or spec["source"]["kind"] != "github":
            raise InstallError("That engine has no automatic download; use its official page.")
        if not consent:
            raise InstallError("Downloads are off. Turn on 'Allow internet downloads' in Settings and confirm.")
        with self.lock:
            if self.job["state"] == "running":
                raise InstallError("Another download is running.")
            self.job = {"state": "running", "engine": engine_id, "step": "Asking GitHub for the latest release",
                        "percent": 0, "log": [], "error": None, "path": None}
        if run_inline:
            self._run(engine_id, spec)
        else:
            threading.Thread(target=self._run, args=(engine_id, spec), daemon=True).start()
        return self.snapshot()

    def start_many(self, engine_ids: list[str], *, consent: bool, run_inline: bool = False) -> dict:
        if not consent:
            raise InstallError("Downloads are off. Turn on 'Allow internet downloads' in Settings and confirm.")
        todo = [e for e in engine_ids if e in ENGINES and ENGINES[e]["source"]["kind"] == "github"]
        if not todo:
            raise InstallError("Nothing to fetch: every engine with an official download is already here.")
        with self.lock:
            if self.job["state"] == "running":
                raise InstallError("Another download is running.")
            self.job = {"state": "running", "engine": todo[0], "step": f"Fetching {len(todo)} engines", "percent": 0,
                        "log": [], "error": None, "path": None}

        def run_all() -> None:
            failures = []
            for engine_id in todo:
                self._set(engine=engine_id, percent=0)
                self._run(engine_id, ENGINES[engine_id], final=False)
                if self.snapshot()["error"]:
                    failures.append(f"{ENGINES[engine_id]['name']}: {self.snapshot()['error']}")
                    self._set(error=None)
            if failures:
                self._set(state="error", step="Finished with problems", error="; ".join(failures)[:600])
            else:
                self._set(state="done", step="All engines installed", percent=100)
        if run_inline:
            run_all()
        else:
            threading.Thread(target=run_all, daemon=True).start()
        return self.snapshot()

    def _run(self, engine_id: str, spec: dict, final: bool = True) -> None:
        try:
            release = latest_release(spec["source"]["repo"], self.api_base, self.hosts, self.allow_http)
            asset = pick_asset(release["assets"], spec["source"]["asset"])
            if asset is None:
                raise InstallError(f"The latest {spec['name']} release ({release['tag']}) has no Windows package this app recognises. "
                                   f"Get it from {spec['source'].get('page') or release['page']}.")
            if asset["size"] > MAX_ASSET_BYTES:
                raise InstallError("That package is larger than expected, so it was refused.")
            self._log(f"{spec['name']} {release['tag']}: {asset['name']} ({asset['size'] // (1024 * 1024)} MB) from {spec['source']['repo']}")
            self._set(step=f"Downloading {asset['name']}")
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / asset["name"]
                with _open(asset["url"], self.hosts, self.allow_http, timeout=60) as response, open(archive, "wb") as out:
                    done = 0
                    total = asset["size"] or int(response.headers.get("Content-Length") or 0)
                    while chunk := response.read(256 * 1024):
                        done += len(chunk)
                        if done > MAX_ASSET_BYTES:
                            raise InstallError("The download exceeded its size limit and was stopped.")
                        out.write(chunk)
                        if total:
                            self._set(percent=int(80 * done / total))
                self._set(step="Unpacking", percent=85)
                staging = Path(tmp) / "unpacked"
                if archive.suffix.lower() == ".zip":
                    extract_zip_safe(archive, staging)
                else:
                    try:
                        extract_7z(archive, staging)
                    except SetupError as exc:
                        raise InstallError(str(exc)) from exc
                dest = self.install_root / engine_id
                dest.parent.mkdir(parents=True, exist_ok=True)
                aside = dest.with_name(dest.name + ".old")
                if aside.exists():
                    shutil.rmtree(aside, ignore_errors=True)
                had_old = dest.exists()
                if had_old:
                    dest.rename(aside)                         # the old install is kept until the new one is in place
                inner = [p for p in staging.iterdir()]
                try:
                    shutil.move(str(inner[0] if len(inner) == 1 and inner[0].is_dir() else staging), str(dest))
                except Exception:
                    if had_old and not dest.exists():
                        aside.rename(dest)                     # put the old one back; an update must never leave nothing
                    raise
                if had_old:
                    for name in PLAYER_DATA:                   # a portable emulator's saves and settings come along
                        keep = aside / name
                        if keep.exists():
                            target = dest / name
                            if target.is_dir() and not target.is_symlink():
                                shutil.rmtree(target, ignore_errors=True)
                            elif target.exists():
                                target.unlink()
                            shutil.move(str(keep), str(target))
                    shutil.rmtree(aside, ignore_errors=True)
            self._set(step="Installed", percent=100, path=str(dest), **({"state": "done"} if final else {}))
            self._log(f"Installed {spec['name']} into {dest}. Nothing was run.")
        except InstallError as exc:
            self._set(error=str(exc), step="Stopped", **({"state": "error"} if final else {}))
            self._log(f"Stopped: {exc}")
        except Exception as exc:
            self._set(error=f"Unexpected problem: {type(exc).__name__}", step="Stopped", **({"state": "error"} if final else {}))
