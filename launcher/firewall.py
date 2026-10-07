"""Let friends through the Windows Firewall for the server port, once, on every kind of network.

Without a rule Windows asks the first time and usually offers only "private networks", which silently blocks a computer
that Windows has labelled "public" (hotspots, hotels). Adding the rule needs administrator rights, so when the app is not
elevated it asks Windows for the usual approval box (the player sees one prompt and presses Yes). Windows only; on other
systems everything here says "not needed".
"""
from __future__ import annotations

import subprocess
import sys

RULE = "Legacy Player server"
_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def supported() -> bool:
    return sys.platform == "win32"


def _run(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=_FLAGS)


def rule_args(port: int) -> list[str]:
    return ["advfirewall", "firewall", "add", "rule", f"name={RULE}", "dir=in", "action=allow", "protocol=TCP",
            f"localport={int(port)}", "profile=any"]


def status(port: int, run=_run) -> dict:
    if not supported():
        return {"supported": False, "allowed": True, "message": "Not needed on this system."}
    try:
        out = run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE}"])
    except (OSError, subprocess.SubprocessError):
        return {"supported": True, "allowed": False, "message": "Could not read the Windows Firewall."}
    text = out.stdout or ""
    allowed = out.returncode == 0 and f"{int(port)}" in text and "Allow" in text
    return {"supported": True, "allowed": allowed,
            "message": "Windows Firewall already lets friends in." if allowed else "Windows Firewall has no rule for your server yet."}


def allow(port: int, run=_run) -> dict:
    """Add the rule, asking Windows for approval when not already an administrator."""
    if not supported():
        return {"supported": False, "allowed": True, "message": "Not needed on this system."}
    try:
        direct = run(["netsh"] + rule_args(port))
        if direct.returncode != 0:
            quoted = " ".join(f'"{a}"' if " " in a else a for a in rule_args(port)).replace('"', '""')
            run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                 f"Start-Process netsh -ArgumentList '{quoted}' -Verb RunAs -Wait -WindowStyle Hidden"], timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"supported": True, "allowed": False, "message": f"Windows did not allow the change ({exc})."}
    now = status(port, run)
    if not now["allowed"]:
        now["message"] = "The rule was not added (the approval box was closed or refused). Friends on other networks may be blocked."
    return now
