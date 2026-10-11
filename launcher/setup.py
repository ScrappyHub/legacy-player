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

import os
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
# The player's own files in a RetroArch folder. Everything the fresh package does not ship is carried over anyway;
# for these names the player's copy also wins when the package happens to ship one.
RETROARCH_KEEP = ("retroarch.cfg", "retroarch-core-options.cfg", "config", "saves", "states", "system", "playlists", "remaps",
                  "screenshots", "thumbnails", "cheats", "logs", "downloads", "portable.txt")


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
    def __init__(self, host: str, allow_http: bool = False) -> None:
        self.host = host
        self.allow_http = allow_http

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlparse
        parts = urlparse(newurl)
        if parts.hostname != self.host:
            raise SetupError("The download was redirected to a different site, so it was refused.")
        if parts.scheme != "https" and not (self.allow_http and parts.scheme == "http"):
            raise SetupError("The download was redirected away from https, so it was refused.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url: str, dest: Path, *, max_bytes: int, allowed_host: str = OFFICIAL_HOST,
             allow_http: bool = False, progress=None) -> None:
    from urllib.parse import urlparse
    parts = urlparse(url)
    if parts.hostname != allowed_host or (parts.scheme != "https" and not (allow_http and parts.scheme == "http")):
        raise SetupError("Downloads are only allowed from the official RetroArch build server over https.")
    opener = urllib.request.build_opener(_SameHostOnly(allowed_host, allow_http))
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


def _seven_zip_tools() -> list[tuple[str, str]]:
    """(kind, program) for each unpacker found: kind "7z" (7-Zip and its cousins) or "tar" (bsdtar/GNU tar)."""
    candidates: list[tuple[str, str]] = []
    for name in ("7z", "7za", "7zr"):
        found = shutil.which(name)
        if found and ("7z", found) not in candidates:
            candidates.append(("7z", found))
    for path in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if Path(path).is_file() and ("7z", path) not in candidates:
            candidates.append(("7z", path))
    tar = shutil.which("tar")
    if tar:  # Windows ships bsdtar; recent builds of it read .7z, older Windows 10 ones do not
        candidates.append(("tar", tar))
    return candidates


def _bad_member_name(name: str) -> bool:
    """True for an absolute path, a drive-qualified path, or one that climbs out with '..'."""
    text = name.replace("\\", "/")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        return True
    return any(part == ".." for part in text.split("/"))


def _listing_7z(output: str) -> list[tuple[str, bool]]:
    """(path, is_link) for each entry in `7z l -slt` output. The block before the '----------' line describes the
    archive itself and is skipped."""
    _, sep, body = output.replace("\r\n", "\n").partition("\n----------\n")
    if not sep:
        return []
    entries: list[tuple[str, bool]] = []
    for block in re.split(r"\n\s*\n", body):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, eq, value = line.partition(" = ")
            if eq:
                fields[key.strip()] = value.strip()
        if "Path" not in fields:
            continue
        attrs = fields.get("Attributes", "")
        is_link = bool(fields.get("Symbolic Link") or fields.get("Hard Link") or re.search(r"(^|\s)l[r-][w-][xsStT-]", attrs))
        entries.append((fields["Path"], is_link))
    return entries


def _listing_tar(names: str, verbose: str) -> list[tuple[str, bool]]:
    rows = [n for n in names.splitlines() if n.strip()]
    links = [line[:1] in ("l", "h") for line in verbose.splitlines() if line.strip()]
    if len(links) != len(rows):          # cannot pair them up: any link mark refuses the whole archive
        return [(n, any(links)) for n in rows]
    return list(zip(rows, links))


def _check_listing(entries: list[tuple[str, bool]]) -> None:
    for name, is_link in entries:
        if _bad_member_name(name):
            raise SetupError("The archive tried to write outside its folder and was refused.")
        if is_link:
            raise SetupError("The archive contains a link to somewhere else, so it was refused.")


def _run_tool(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=600,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _tool_error(result: subprocess.CompletedProcess) -> str:
    text = (result.stderr or "").strip() or (result.stdout or "").strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return (" ".join(lines[-3:]) or f"exit code {result.returncode}")[:240]


def extract_7z(archive: Path, dest: Path, what: str = "") -> None:
    """Unpack a .7z safely. The archive is listed first and refused if any entry is absolute, climbs out with '..'
    or is a link; only then is it extracted. `what` names the program in messages ("RetroArch", "PCSX2")."""
    what = what or "this program"
    dest.mkdir(parents=True, exist_ok=True)
    tools = _seven_zip_tools()
    if not tools:
        raise SetupError(f"No tool to unpack .7z files was found. Install 7-Zip (7-zip.org), which {what} needs, then press Install again.")
    problems: list[str] = []
    for kind, program in tools:
        label = "7-Zip" if kind == "7z" else "tar"
        try:
            if kind == "7z":
                listed = _run_tool([program, "l", "-slt", str(archive)])
                if listed.returncode != 0:
                    problems.append(f"{label} could not read the {what} package: {_tool_error(listed)}")
                    continue
                entries = _listing_7z(listed.stdout or "")
            else:
                names = _run_tool([program, "-tf", str(archive)])
                if names.returncode != 0:
                    problems.append(f"{label} could not read the {what} package: {_tool_error(names)}")
                    continue
                verbose = _run_tool([program, "-tvf", str(archive)])
                entries = _listing_tar(names.stdout or "", (verbose.stdout or "") if verbose.returncode == 0 else "l")
            if not entries:
                problems.append(f"{label} found nothing inside the {what} package.")
                continue
            _check_listing(entries)                       # before a single byte is written
            command = ([program, "x", "-y", str(archive), f"-o{dest}"] if kind == "7z"
                       else [program, "-xf", str(archive), "-C", str(dest)])
            done = _run_tool(command)
            if done.returncode != 0:
                problems.append(f"{label} could not unpack the {what} package: {_tool_error(done)}")
                continue
            for item in dest.rglob("*"):                  # belt and braces: nothing escaped, nothing is a link
                _safe_member(dest, str(item.relative_to(dest)))
                if item.is_symlink():
                    raise SetupError("The archive contains a link to somewhere else, so it was refused.")
            return
        except subprocess.TimeoutExpired:
            problems.append(f"Unpacking the {what} package with {label} took too long and was stopped.")
        except OSError as exc:
            problems.append(f"Could not run {label}: {exc}"[:200])
    detail = "; ".join(problems)[:400]
    if all(kind == "tar" for kind, _ in tools):
        raise SetupError(f"7-Zip is needed to install {what}: Windows' built-in tar could not unpack its .7z package (older "
                         f"Windows 10 versions cannot read .7z). Install 7-Zip from 7-zip.org, then press Install again. ({detail})")
    raise SetupError(detail or f"The {what} package could not be unpacked.")


# ---- replacing an installed program folder without losing what the player keeps in it ----

def _is_dir(p: Path) -> bool:
    return p.is_dir() and not p.is_symlink()


def _exists(p: Path) -> bool:
    return p.exists() or p.is_symlink()


def locked_message(exc: OSError, name: str) -> str | None:
    """A plain "close it first" message when Windows refused because the program (or a file of it) is open."""
    if isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in (5, 32, 33):
        return f"Close {name} first: its folder cannot be changed while it is running. Nothing was changed."
    return None


def has_files(root: Path) -> bool:
    try:
        return any(p.is_file() for p in Path(root).rglob("*"))
    except OSError:
        return False


def _carry_over(old: Path, new: Path, keep: set[str], journal: list, prefer_old: bool = False, top: bool = True) -> None:
    """Move everything in `old` that `new` lacks into `new`. Where both have a file, the new package's copy stays,
    except under a `keep` name (top level, lower case), where the player's copy wins and the package's is parked
    next to it. Every step goes into `journal` so it can be undone."""
    for entry in sorted(old.iterdir(), key=lambda p: p.name):
        target = new / entry.name
        ours = prefer_old or (top and entry.name.lower() in keep)
        if not _exists(target):
            os.rename(entry, target)
            journal.append(("move", entry, target))
        elif _is_dir(entry) and _is_dir(target):
            _carry_over(entry, target, keep, journal, ours, top=False)
        elif ours and not _is_dir(entry) and not _is_dir(target):
            parked = target.with_name(target.name + ".lp-new")
            os.replace(target, parked)
            journal.append(("park", target, parked))
            os.rename(entry, target)
            journal.append(("move", entry, target))


def _undo(journal: list) -> None:
    for step in reversed(journal):
        if step[0] == "move":
            step[1].parent.mkdir(parents=True, exist_ok=True)
            os.rename(step[2], step[1])
        else:
            os.replace(step[2], step[1])


def _drop_parked(journal: list) -> None:
    for step in journal:
        if step[0] == "park":
            try:
                step[2].unlink()
            except OSError:
                pass


def recover_aside(dest: Path, keep=(), name: str = "the program") -> None:
    """`<dest>.old` is left from an update that was cut short. Put it back (when `dest` is missing) or merge what only it
    has into `dest`; it is removed only after that. Never simply deleted."""
    dest = Path(dest)
    aside = dest.with_name(dest.name + ".old")
    if not _exists(aside):
        return
    try:
        if not _exists(dest):
            os.rename(aside, dest)
            return
        journal: list = []
        _carry_over(aside, dest, {k.lower() for k in keep}, journal)
        _drop_parked(journal)
        shutil.rmtree(aside, ignore_errors=True)
    except OSError as exc:
        raise SetupError(locked_message(exc, name) or f"An earlier update of {name} left {aside} behind and it could not be "
                                                      f"merged back ({exc}). Nothing was changed.") from exc


def replace_folder(new_root: Path, dest: Path, keep=(), name: str = "the program") -> None:
    """Put the freshly unpacked `new_root` where `dest` is and carry over everything from the old `dest` that the new
    package does not contain (saves, settings, firmware, installed games...). Program files come from the package; for
    the top-level names in `keep` the player's copy always wins. If anything fails the old folder is put back as it was."""
    new_root, dest = Path(new_root), Path(dest)
    if not _is_dir(new_root) or not has_files(new_root):
        raise SetupError(f"The {name} package unpacked to nothing, so the installed copy was left alone.")
    recover_aside(dest, keep, name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    aside = dest.with_name(dest.name + ".old")
    had_old = _exists(dest)
    if had_old:
        try:
            os.rename(dest, aside)                         # the old install is kept until the new one is in place
        except OSError as exc:
            raise SetupError(locked_message(exc, name) or f"Could not move the old {name} aside ({exc}). Nothing was changed.") from exc
    journal: list = []
    try:
        shutil.move(str(new_root), str(dest))
        if had_old:
            _carry_over(aside, dest, {k.lower() for k in keep}, journal)
    except BaseException as exc:
        try:                                             # put the old one back exactly: an update never leaves nothing
            _undo(journal)
            if had_old:
                if _exists(dest):
                    shutil.rmtree(dest)
                os.rename(aside, dest)
        except OSError:
            pass                                         # `.old` stays and the next attempt merges it back first
        if isinstance(exc, OSError):
            raise SetupError(locked_message(exc, name) or f"Installing {name} failed ({exc}); the copy you had was kept.") from exc
        raise
    _drop_parked(journal)
    if had_old:
        shutil.rmtree(aside, ignore_errors=True)         # only old program files the package replaced are left in it


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
            extract_7z(archive, staging, "RetroArch")
            found = next(staging.rglob("retroarch.exe"), None)
            if not found:
                raise SetupError("The RetroArch package did not contain retroarch.exe.")
            # A folder already here (retroarch.exe may only have been quarantined) keeps its settings, saves, states,
            # BIOS files and cores: they are carried over into the fresh copy, never deleted.
            replace_folder(found.parent, self.install_root, RETROARCH_KEEP, "RetroArch")
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
