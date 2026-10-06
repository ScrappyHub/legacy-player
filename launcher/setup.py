"""First-run setup: check for RetroArch, its cores and Dolphin, and install what can be
installed safely.

Safety model
- Downloads come only from the official libretro build server (https, host allow-list,
  redirects to other hosts refused, size caps). The server publishes no checksums, so
  integrity rests on TLS to that host; this is stated in the UI.
- Archives are extracted with path-escape checks; nothing is run after install.
- Everything lands in the launcher's own data folder (no admin rights needed).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from adapters.retroarch import CORES, NetplayError, find_core

OFFICIAL_HOST = "buildbot.libretro.com"
FALLBACK_STABLE = "1.22.2"
MAX_CORE_BYTES = 60 * 1024 * 1024
MAX_RETROARCH_BYTES = 450 * 1024 * 1024
MAX_INFO_BYTES = 30 * 1024 * 1024


def info_dir_for(exe: str | None, fallback: Path) -> Path:
    return (Path(exe).resolve().parent if exe else fallback) / "info"


def read_info_value(info_file: Path, key: str) -> str | None:
    """Value of `key = "..."` from a libretro .info file, or None."""
    try:
        for line in info_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == key:
                return value.strip().strip('"')
    except OSError:
        pass
    return None


def extract_info_files(archive: Path, dest: Path) -> int:
    """Extract only *.info files (flat, by base name) from libretro's info.zip."""
    count = 0
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            name = Path(member).name
            if member.endswith("/") or not name.endswith(".info") or name != Path(name).name:
                continue
            with z.open(member) as src, open(dest / name, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    return count


class SetupError(RuntimeError):
    pass


def platform_key() -> str:
    return {"win32": "windows", "darwin": "mac"}.get(sys.platform, "linux")


def core_url(stem: str, base: str = f"https://{OFFICIAL_HOST}", plat: str | None = None) -> str:
    plat = plat or platform_key()
    if plat == "windows":
        return f"{base}/nightly/windows/x86_64/latest/{stem}.dll.zip"
    if plat == "linux":
        return f"{base}/nightly/linux/x86_64/latest/{stem}.so.zip"
    raise SetupError("Automatic core download is available on Windows and Linux. On macOS, use RetroArch's own Core Downloader.")


def core_filename(stem: str, plat: str | None = None) -> str:
    return stem + {"windows": ".dll", "mac": ".dylib"}.get(plat or platform_key(), ".so")


class _SameHostOnly(urllib.request.HTTPRedirectHandler):
    def __init__(self, host: str) -> None:
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlparse
        if urlparse(newurl).hostname != self.host:
            raise SetupError("The download was redirected to a different site, so it was refused.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url: str, dest: Path, *, max_bytes: int, allowed_host: str = OFFICIAL_HOST,
             allow_http: bool = False, progress=None) -> None:
    from urllib.parse import urlparse
    parts = urlparse(url)
    if parts.hostname != allowed_host or (parts.scheme != "https" and not (allow_http and parts.scheme == "http")):
        raise SetupError("Downloads are only allowed from the official RetroArch build server over https.")
    opener = urllib.request.build_opener(_SameHostOnly(allowed_host))
    request = urllib.request.Request(url, headers={"User-Agent": "LegacyPlayer-Setup"})
    try:
        with opener.open(request, timeout=30) as response, open(dest, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            if total > max_bytes:
                raise SetupError("The file is larger than expected, so it was refused.")
            done = 0
            while chunk := response.read(256 * 1024):
                done += len(chunk)
                if done > max_bytes:
                    raise SetupError("The download exceeded its size limit and was stopped.")
                out.write(chunk)
                if progress and total:
                    progress(done / total)
    except urllib.error.HTTPError as exc:
        raise SetupError(f"The download server answered {exc.code} for {parts.path.rsplit('/', 1)[-1]}.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise SetupError(f"Could not download ({getattr(exc, 'reason', exc)}). Your internet connection or a firewall may be blocking {allowed_host}.") from exc


def _safe_member(dest: Path, name: str) -> Path:
    target = (dest / name).resolve()
    if dest.resolve() not in target.parents and target != dest.resolve():
        raise SetupError("The archive tried to write outside its folder and was refused.")
    return target


def extract_zip_member(archive: Path, member: str, dest_file: Path) -> None:
    """Extract exactly one expected file from a zip into dest_file."""
    with zipfile.ZipFile(archive) as z:
        names = {Path(n).name: n for n in z.namelist() if not n.endswith("/")}
        if member not in names:
            raise SetupError(f"The download did not contain {member}.")
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        with z.open(names[member]) as src, open(dest_file, "wb") as out:
            shutil.copyfileobj(src, out)


def _seven_zip_tools() -> list[list[str]]:
    candidates = []
    for name in ("7z", "7za", "7zr"):
        if shutil.which(name):
            candidates.append([shutil.which(name), "x", "-y"])
    for path in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if Path(path).is_file():
            candidates.append([path, "x", "-y"])
    tar = shutil.which("tar")
    if tar:  # Windows 10+ ships bsdtar, which reads .7z
        candidates.append([tar, "-xf"])
    return candidates


def extract_7z(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    errors = []
    for tool in _seven_zip_tools():
        command = tool + ([str(archive), f"-o{dest}"] if tool[-1] == "-y" else [str(archive), "-C", str(dest)])
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=600)
            for item in dest.rglob("*"):  # nothing may have landed outside dest
                _safe_member(dest, str(item.relative_to(dest)))
            return
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append(str(exc)[:80])
    raise SetupError("No tool to unpack .7z files was found. Install 7-Zip (7-zip.org), then press Install again.")


def latest_stable(listing_html: str | None) -> str:
    if listing_html:
        versions = re.findall(r'href="(\d+\.\d+\.\d+)/"', listing_html)
        if versions:
            return max(versions, key=lambda v: tuple(int(x) for x in v.split(".")))
    return FALLBACK_STABLE


class Setup:
    """Status checks and background installs, driven by the launcher UI."""

    def __init__(self, data_dir: Path, find_retroarch, set_retroarch_path, base: str = f"https://{OFFICIAL_HOST}",
                 allowed_host: str = OFFICIAL_HOST, allow_http: bool = False) -> None:
        self.install_root = Path(data_dir) / "emulators" / "retroarch"
        self.find_retroarch = find_retroarch
        self.set_retroarch_path = set_retroarch_path
        self.base, self.allowed_host, self.allow_http = base, allowed_host, allow_http
        self.lock = threading.Lock()
        self.job = {"state": "idle", "step": "", "percent": 0, "log": [], "error": None}

    # -- checks -----------------------------------------------------------
    def retroarch_cores_dir(self, exe: str | None) -> Path:
        if exe:
            return Path(exe).resolve().parent / "cores"
        return self.install_root / "cores"

    def check(self, dolphin_path: str | None) -> dict:
        exe = self.find_retroarch()
        cores = []
        for console_id, stems in CORES.items():
            try:
                found = find_core(exe, console_id) if exe else None
            except NetplayError:
                found = None
            info_file = info_dir_for(exe, self.install_root) / (stems[0] + ".info")
            feature = read_info_value(info_file, "savestate_features") if info_file.is_file() else None
            cores.append({"console": console_id, "wanted": stems[0], "installed": bool(found),
                          "info_present": info_file.is_file(),
                          # netplay needs deterministic savestates; None = info file not installed yet
                          "netplay_ready": (feature == "deterministic") if info_file.is_file() else None})
        plat = platform_key()
        wanted = {c["wanted"] for c in cores}
        return {
            "platform": plat,
            "retroarch": {"installed": bool(exe), "path": exe},
            "cores": cores,
            "info_installed": bool(exe) and any(info_dir_for(exe, self.install_root).glob("*.info")),
            "netplay_not_ready": sorted({c["wanted"] for c in cores if c["installed"] and c["netplay_ready"] is False}),
            "cores_missing": sorted({c["wanted"] for c in cores if not c["installed"]}),
            "dolphin": {"installed": bool(dolphin_path), "path": dolphin_path,
                        "download_page": "https://dolphin-emu.org/download/"},
            "can_auto_install_retroarch": plat == "windows",
            "can_auto_install_cores": plat in {"windows", "linux"},
            "manual_retroarch": {
                "linux": "Install RetroArch from your package manager (for example `sudo apt install retroarch`) or Flatpak (`flatpak install flathub org.libretro.RetroArch`), then press Check again.",
                "mac": "Install RetroArch from retroarch.com, then use its Online Updater to get cores.",
                "windows": "",
            }[plat],
            "source": f"{self.allowed_host} (official libretro build server, over https; it publishes no checksums)",
            "install_folder": str(self.install_root),
            "total_cores": len(wanted),
            "job": self.snapshot(),
        }

    # -- job plumbing ------------------------------------------------------
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

    def start(self, what: str, run_inline: bool = False) -> dict:
        if what not in {"all", "cores", "retroarch"}:
            raise SetupError("Unknown install request.")
        with self.lock:
            if self.job["state"] == "running":
                raise SetupError("An install is already running.")
            self.job = {"state": "running", "step": "Starting", "percent": 0, "log": [], "error": None}
        if run_inline:
            self._run(what)
        else:
            threading.Thread(target=self._run, args=(what,), daemon=True).start()
        return self.snapshot()

    def _run(self, what: str) -> None:
        try:
            exe = self.find_retroarch()
            if what in {"all", "retroarch"} and not exe:
                exe = self._install_retroarch()
            if what in {"all", "cores"}:
                if not exe:
                    raise SetupError("RetroArch is not installed yet. " + self.check(None)["manual_retroarch"])
                self._install_cores(exe)
                self._install_info(exe)
            self._set(state="done", step="Finished", percent=100)
            self._log("All done. Press Check again to confirm.")
        except SetupError as exc:
            self._set(state="error", error=str(exc), step="Stopped")
            self._log(f"Stopped: {exc}")
        except Exception as exc:  # unexpected: show the type, not a traceback
            self._set(state="error", error=f"Unexpected problem: {type(exc).__name__}", step="Stopped")

    def _install_retroarch(self) -> str:
        if platform_key() != "windows":
            raise SetupError(self.check(None)["manual_retroarch"])
        self._set(step="Finding the latest stable RetroArch")
        version = FALLBACK_STABLE
        try:
            with tempfile.TemporaryDirectory() as tmp:
                listing = Path(tmp) / "index.html"
                download(f"{self.base}/stable/", listing, max_bytes=2_000_000, allowed_host=self.allowed_host, allow_http=self.allow_http)
                version = latest_stable(listing.read_text(errors="ignore"))
        except SetupError:
            self._log(f"Could not read the version list; using {version}.")
        self._log(f"Downloading RetroArch {version} (about 200 MB)")
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "RetroArch.7z"
            download(f"{self.base}/stable/{version}/windows/x86_64/RetroArch.7z", archive,
                     max_bytes=MAX_RETROARCH_BYTES, allowed_host=self.allowed_host, allow_http=self.allow_http,
                     progress=lambda f: self._set(step="Downloading RetroArch", percent=int(f * 60)))
            self._set(step="Unpacking RetroArch", percent=62)
            staging = Path(tmp) / "unpacked"
            extract_7z(archive, staging)
            found = next(staging.rglob("retroarch.exe"), None)
            if not found:
                raise SetupError("The RetroArch package did not contain retroarch.exe.")
            if self.install_root.exists():
                shutil.rmtree(self.install_root)
            self.install_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(found.parent), str(self.install_root))
        exe = str(self.install_root / "retroarch.exe")
        self.set_retroarch_path(exe)
        self._log(f"RetroArch installed in {self.install_root}")
        return exe

    def _install_cores(self, exe: str) -> None:
        folder = self.retroarch_cores_dir(exe)
        stems = []
        for console_id, options in CORES.items():
            stem = options[0]
            try:
                find_core(exe, console_id)
            except NetplayError:
                if stem not in stems:
                    stems.append(stem)
        if not stems:
            self._log("All cores are already installed.")
            return
        plat = platform_key()
        for index, stem in enumerate(stems):
            self._set(step=f"Downloading core {stem}", percent=65 + int(35 * index / len(stems)))
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / f"{stem}.zip"
                download(core_url(stem, self.base, plat), archive, max_bytes=MAX_CORE_BYTES,
                         allowed_host=self.allowed_host, allow_http=self.allow_http)
                extract_zip_member(archive, core_filename(stem, plat), folder / core_filename(stem, plat))
            self._log(f"Installed core {stem}")

    def _install_info(self, exe: str) -> None:
        folder = info_dir_for(exe, self.install_root)
        if any(folder.glob("*.info")):
            self._log("Core info files are already installed.")
            return
        self._set(step="Downloading core info files", percent=96)
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "info.zip"
            download(f"{self.base}/assets/frontend/info.zip", archive, max_bytes=MAX_INFO_BYTES,
                     allowed_host=self.allowed_host, allow_http=self.allow_http)
            count = extract_info_files(archive, folder)
        if not count:
            raise SetupError("The core info download had no .info files.")
        self._log(f"Installed {count} core info files (RetroArch needs them to allow netplay).")
