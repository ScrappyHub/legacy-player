"""Legacy Player updating itself, then restarting on the new version.

Two ways Legacy Player runs, two ways to update:
  * the Windows app (LegacyPlayer.exe): the newest GitHub release's zip is downloaded, checked against its published
    SHA-256, unpacked aside and checked again; then a small helper waits for this app to close, copies the new files
    over the folder the app runs from, and starts the new LegacyPlayer.exe. Settings, games and saves live elsewhere and
    are never touched.
  * a git checkout (`lp source`, `python -m launcher`): `git pull --ff-only`, then the app starts itself again.
In both cases files that were already updated on disk (for example someone ran `git pull`) only need the restart.

Nothing here runs without the player pressing a button: checking needs "Allow internet downloads", and installing
needs a confirmation in the app.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .installer import GITHUB_HOSTS, InstallError, _open, extract_zip_safe, latest_release
from .version import REPO, VERSION

ROOT = Path(__file__).resolve().parent.parent          # the checkout (source) or the unpacked bundle (exe)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DETACHED = 0x00000008 | 0x00000200                    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def nums(text: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(text))[:3])


def mode() -> str:
    """'exe' for the Windows app, 'git' for a checkout with git available, '' when this copy cannot update itself."""
    if getattr(sys, "frozen", False):
        return "exe"
    if (ROOT / ".git").exists() and shutil.which("git"):
        return "git"
    return ""


def version_on_disk() -> str:
    """The version written in the files (differs from the running VERSION after a `git pull` the app has not restarted for)."""
    try:
        m = re.search(r'VERSION\s*=\s*"([^"]+)"', (ROOT / "launcher" / "version.py").read_text(encoding="utf-8"))
        return m.group(1) if m else VERSION
    except OSError:
        return VERSION


def _git(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout,
                          creationflags=_NO_WINDOW)


class SelfUpdate:
    """One update at a time. `state` is idle / checking / downloading / ready / restarting / problem."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.lock = threading.Lock()
        self.status: dict = {"state": "idle", "mode": mode(), "current": VERSION, "message": ""}
        self.staged: dict | None = None
        self.mode = mode

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.status)

    def _set(self, **kw) -> None:
        with self.lock:
            self.status.update(kw)

    # --- what is newer --------------------------------------------------------------------------------------
    def check(self) -> dict:
        """{'newer': bool, 'latest': str, 'restart_only': bool, 'message': str, 'mode': ...}. Raises InstallError."""
        m = self.mode()
        if m == "git":
            disk = version_on_disk()
            fetched = _git("fetch", "--quiet", timeout=90)
            behind = 0
            if fetched.returncode == 0:
                count = _git("rev-list", "--count", "HEAD..@{u}")
                behind = int(count.stdout.strip() or 0) if count.returncode == 0 else 0
            if behind:
                return {"mode": m, "newer": True, "restart_only": False, "latest": f"{behind} new change{'s' if behind != 1 else ''}",
                        "message": f"Your copy is {behind} change{'s' if behind != 1 else ''} behind. Updating pulls them and restarts Legacy Player."}
            if nums(disk) != nums(VERSION):
                return {"mode": m, "newer": True, "restart_only": True, "latest": disk,
                        "message": f"Version {disk} is already in your folder; Legacy Player is still running {VERSION}. Restart to use it."}
            note = "" if fetched.returncode == 0 else " (could not reach the git server, so only your folder was checked)"
            return {"mode": m, "newer": False, "restart_only": False, "latest": VERSION, "message": f"You have the latest version ({VERSION}){note}."}
        rel = latest_release(REPO)
        newer = bool(nums(rel["tag"])) and nums(rel["tag"]) > nums(VERSION)
        return {"mode": m or "exe", "newer": newer, "restart_only": False, "latest": rel["tag"], "release": rel,
                "message": (f"Version {rel['tag']} is available (you have {VERSION})." if newer else f"You have the latest version ({VERSION}).")}

    # --- get it ready ---------------------------------------------------------------------------------------
    def prepare(self, info: dict | None = None) -> dict:
        """Download and check (exe) or pull (git). Leaves self.staged set so restart() can finish the job."""
        info = info or self.check()
        if not info.get("newer"):
            self._set(state="idle", message=info["message"])
            return self.snapshot()
        m = info["mode"]
        if m == "git":
            if not info.get("restart_only"):
                self._set(state="downloading", message="Pulling the new version…")
                out = _git("pull", "--ff-only", timeout=180)
                if out.returncode != 0:
                    why = (out.stderr or out.stdout or "").strip().splitlines()
                    msg = ("Your folder has changes of its own, so git would not update it. Commit or put them aside "
                           "(git stash), then try again." if any("local changes" in w or "diverged" in w or "Not possible to fast-forward" in w for w in why)
                           else "git could not update the folder: " + (why[-1] if why else "no reason given"))
                    self._set(state="problem", message=msg)
                    raise InstallError(msg)
            self.staged = {"mode": "git", "version": version_on_disk()}
            self._set(state="ready", latest=self.staged["version"], message=f"Version {self.staged['version']} is ready. Legacy Player restarts to use it.")
            return self.snapshot()
        if sys.platform != "win32":
            raise InstallError("The downloadable app is for Windows. On this system, update with git (lp source).")
        rel = info.get("release") or latest_release(REPO)
        zip_asset = next((a for a in rel["assets"] if re.fullmatch(r"LegacyPlayer-.*-win64\.zip", a["name"])), None)
        sum_asset = next((a for a in rel["assets"] if re.fullmatch(r"LegacyPlayer-.*-win64\.zip\.sha256", a["name"])), None)
        if not zip_asset or not sum_asset:
            raise InstallError(f"Release {rel['tag']} has no Windows package with a checksum, so nothing was installed.")
        folder = self.data_dir / "update"
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
        archive = folder / zip_asset["name"]
        self._set(state="downloading", latest=rel["tag"], message=f"Downloading {rel['tag']}…", done=0, total=zip_asset.get("size") or 0)
        with _open(sum_asset["url"], GITHUB_HOSTS, timeout=60) as response:
            expected = response.read(4096).decode("utf-8", "replace").strip().split()[0].lower()
        digest = hashlib.sha256()
        with _open(zip_asset["url"], GITHUB_HOSTS, timeout=60) as response, open(archive, "wb") as out:
            done = 0
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                self._set(done=done)
        if digest.hexdigest().lower() != expected or (zip_asset.get("sha256") and zip_asset["sha256"].lower() != expected):
            shutil.rmtree(folder, ignore_errors=True)
            msg = "The download is damaged or was changed (checksum mismatch). Nothing was installed."
            self._set(state="problem", message=msg)
            raise InstallError(msg)
        stage = folder / "new"
        extract_zip_safe(archive, stage)
        if not (stage / "LegacyPlayer.exe").exists():
            raise InstallError("The package has no LegacyPlayer.exe, so nothing was installed.")
        archive.unlink(missing_ok=True)
        self.staged = {"mode": "exe", "version": rel["tag"], "stage": str(stage), "dest": str(Path(sys.executable).resolve().parent)}
        self._set(state="ready", message=f"Version {rel['tag']} is downloaded and checked. Legacy Player restarts to use it.")
        return self.snapshot()

    # --- swap and start again -------------------------------------------------------------------------------
    def restart_plan(self) -> list[str]:
        """The command that finishes the update after this process has exited, then starts the new version."""
        if not self.staged:
            raise InstallError("There is no update ready yet.")
        pid = str(os.getpid())
        if self.staged["mode"] == "exe":
            script = Path(self.data_dir) / "update" / "apply.ps1"
            script.write_text(APPLY_PS1, encoding="utf-8")
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script),
                    "-WaitPid", pid, "-Stage", self.staged["stage"], "-Dest", self.staged["dest"], "-Tag", self.staged["version"],
                    "-Log", str(Path(self.data_dir) / "update" / "apply.log")]
        again = [sys.executable, "-m", "launcher", *sys.argv[1:]]
        return [sys.executable, "-c", RELAUNCH_PY, pid, str(ROOT), *again]

    def launch_helper(self) -> None:
        command = self.restart_plan()
        kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "cwd": str(ROOT)}
        if sys.platform == "win32":
            kwargs["creationflags"] = _DETACHED | _NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(command, **kwargs)
        self._set(state="restarting", message=f"Restarting into {self.staged['version']}…")


# Waits for the old app to exit, then starts it again (git checkouts). Argument 1 is the old process, 2 the folder.
RELAUNCH_PY = r"""
import os, subprocess, sys, time
pid, root, cmd = int(sys.argv[1]), sys.argv[2], sys.argv[3:]
def alive(p):
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000, False, p)
        if not h:
            return False
        try:
            return k.WaitForSingleObject(h, 0) == 0x102
        finally:
            k.CloseHandle(h)
    try:
        os.kill(p, 0)
        return True
    except OSError:
        return False
end = time.time() + 90
while alive(pid) and time.time() < end:
    time.sleep(0.3)
time.sleep(1.0)
kw = {"cwd": root}
if os.name == "nt":
    kw["creationflags"] = 0x00000010   # CREATE_NEW_CONSOLE: the restarted app gets its own window, like `lp source`
else:
    kw["start_new_session"] = True
subprocess.Popen(cmd, **kw)
"""

# Waits for the old app to exit, swaps in the checked files and starts the new LegacyPlayer.exe (Windows app).
APPLY_PS1 = r"""param([int]$WaitPid, [string]$Stage, [string]$Dest, [string]$Tag, [string]$Log)
$ErrorActionPreference = 'Stop'
function Say($t) { Add-Content -Path $Log -Value ("{0:u}  {1}" -f (Get-Date), $t) }
try {
    Say "Waiting for Legacy Player ($WaitPid) to close"
    try { Wait-Process -Id $WaitPid -Timeout 90 -ErrorAction SilentlyContinue } catch {}
    $exe = Join-Path $Dest 'LegacyPlayer.exe'
    # the multiplayer server and friends service run from the same program; they start again with the new version
    Get-Process -Name LegacyPlayer -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe } | ForEach-Object { Say "Stopping $($_.Id)"; Stop-Process -Id $_.Id -Force }
    Start-Sleep -Milliseconds 800
    for ($i = 0; $i -lt 10; $i++) {
        try { Copy-Item -Path (Join-Path $Stage '*') -Destination $Dest -Recurse -Force; break }
        catch { if ($i -eq 9) { throw }; Start-Sleep 1 }
    }
    Get-ChildItem $Dest -Recurse -File | Unblock-File
    $Tag | Set-Content (Join-Path $Dest 'VERSION.txt') -Encoding ASCII
    Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
    Say "Installed $Tag; starting it"
} catch {
    Say ("The update did not finish: " + $_.Exception.Message)
}
Start-Process (Join-Path $Dest 'LegacyPlayer.exe')
"""
