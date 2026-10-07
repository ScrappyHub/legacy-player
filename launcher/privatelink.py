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
