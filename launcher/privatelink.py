"""An encrypted private link between players, using Tailscale (WireGuard) when it is installed.

Dolphin NetPlay connects players straight to each other and is not encrypted. Over a Tailscale network the same
connection runs inside WireGuard, so it is encrypted, needs no router setup, and each player sees only the other's
private 100.x address, not their home address. Legacy Player does not install or run Tailscale: it only reads whether it
is there and what the address is. Nothing here raises.
"""
from __future__ import annotations

import ipaddress
import os
import shutil
import subprocess
import sys
import threading
import time

DOWNLOAD_PAGE = "https://tailscale.com/download"
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def is_private_link_address(text: str) -> bool:
    try:
        return ipaddress.ip_address(str(text).strip()) in _CGNAT
    except ValueError:
        return False


def find_tailscale() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    if sys.platform == "win32":
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if root:
                p = os.path.join(root, "Tailscale", "tailscale.exe")
                if os.path.isfile(p):
                    return p
    return None


_cache: dict = {"at": 0.0, "value": None}


def cached_status(max_age: float = 15.0) -> dict:
    """status() without starting a program on every poll."""
    now = time.monotonic()
    if _cache["value"] is None or now - _cache["at"] > max_age:
        _cache["value"], _cache["at"] = status(), now
    return _cache["value"]


def can_reach(address: str) -> bool:
    """Whether this computer can reach that private address over Tailscale right now (one quick ping)."""
    exe = find_tailscale()
    if not exe or not is_private_link_address(address):
        return False
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run([exe, "ping", "-c", "1", "--timeout", "4s", address], capture_output=True, text=True, timeout=8, creationflags=flags)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def status() -> dict:
    exe = find_tailscale()
    out = {"installed": bool(exe), "running": False, "address": None, "download_page": DOWNLOAD_PAGE}
    if not exe:
        return out
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=4, creationflags=flags)
        for line in r.stdout.split():
            if is_private_link_address(line):
                out["running"], out["address"] = True, line.strip()
                break
    except (OSError, subprocess.SubprocessError):
        pass
    return out


ADMIN_PAGE = "https://login.tailscale.com/admin/machines"
INSTALL = {"state": "idle", "message": ""}        # idle | installing | done | error


def winget_path() -> str | None:
    return shutil.which("winget") if sys.platform == "win32" else None


def install_state() -> dict:
    return dict(INSTALL)


def start_install() -> dict:
    """Install Tailscale with Windows' own package manager (the official Tailscale.Tailscale package). Windows shows its own
    approval box. Runs in the background; poll install_state(). Only called after the person agreed."""
    if INSTALL["state"] == "installing":
        return install_state()
    if find_tailscale():
        INSTALL.update(state="done", message="Tailscale is already installed.")
        return install_state()
    winget = winget_path()
    if not winget:
        INSTALL.update(state="error", message="Windows' package manager (winget) is not available here. Download Tailscale from tailscale.com/download instead.")
        return install_state()
    INSTALL.update(state="installing", message="Installing Tailscale. Approve the Windows prompt if one appears.")

    def work() -> None:
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            r = subprocess.run([winget, "install", "--id", "Tailscale.Tailscale", "-e", "--silent",
                                "--accept-package-agreements", "--accept-source-agreements"],
                               capture_output=True, text=True, timeout=600, creationflags=flags)
            _cache["value"] = None
            if r.returncode == 0 or find_tailscale():
                INSTALL.update(state="done", message="Tailscale is installed. Now sign in.")
            else:
                INSTALL.update(state="error", message="The install did not finish. Download Tailscale from tailscale.com/download instead.")
        except (OSError, subprocess.SubprocessError):
            INSTALL.update(state="error", message="The install did not finish. Download Tailscale from tailscale.com/download instead.")

    threading.Thread(target=work, daemon=True).start()
    return install_state()


def start_login() -> bool:
    """Open Tailscale's sign-in page in the browser (`tailscale login`). Returns whether it could be started."""
    exe = find_tailscale()
    if not exe:
        return False
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([exe, "login"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        _cache["value"] = None
        return True
    except OSError:
        return False
