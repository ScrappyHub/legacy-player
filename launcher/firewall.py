"""Let friends through the Windows Firewall for the server port, once, on every kind of network.

Without a rule Windows asks the first time and usually offers only "private networks", which silently blocks a computer
that Windows has labelled "public" (hotspots, hotels). Adding the rule needs administrator rights, so when the app is not
elevated it asks Windows for the usual approval box (the player sees one prompt and presses Yes). Windows only; on other
systems everything here says "not needed".
"""
from __future__ import annotations

import re
import subprocess
import sys

RULE = "Legacy Player server"
_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def supported() -> bool:
    return sys.platform == "win32"


def _run(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=_FLAGS)


def rule_args(port: int, program: str | None = None) -> list[str]:
    """Every network profile on purpose (hotspots count as "public"), but when the app is the packaged exe the rule
    only lets that one program accept connections, not whatever else might listen on the port."""
    if program is None and getattr(sys, "frozen", False):
        program = sys.executable
    args = ["advfirewall", "firewall", "add", "rule", f"name={RULE}", "dir=in", "action=allow", "protocol=TCP",
            f"localport={int(port)}", "profile=any"]
    if program:
        args.append(f"program={program}")
    return args


def _elevated(args: list[str], run) -> None:
    """Run netsh as administrator through the Windows approval box. The arguments become one command line in which
    anything with a space is wrapped in double quotes (inside a single-quoted PowerShell string those stay as they are)."""
    line = " ".join(f'"{a}"' if (" " in a or "\\" in a) else a for a in args).replace("'", "''")
    run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
         f"Start-Process netsh -ArgumentList '{line}' -Verb RunAs -Wait -WindowStyle Hidden"], timeout=120)


def status(port: int, run=_run) -> dict:
    if not supported():
        return {"supported": False, "allowed": True, "message": "Not needed on this system."}
    try:
        out = run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE}"])
    except (OSError, subprocess.SubprocessError):
        return {"supported": True, "allowed": False, "message": "Could not read the Windows Firewall."}
    text = out.stdout or ""
    ports = re.findall(r"^\s*LocalPort:\s*(\S+)", text, re.M)          # exact port, not a substring (87 must not match 8765); other Windows languages: bare number
    port_ok = str(int(port)) in [x.strip() for x in ports] or (not ports and re.search(rf"(?<!\d){int(port)}(?!\d)", text) is not None)
    program = rule_args(port)[-1][len("program="):] if rule_args(port)[-1].startswith("program=") else ""
    program_ok = (not program) or (program.lower() in text.lower())      # a rule left by an older install location does not count
    allowed = out.returncode == 0 and port_ok and program_ok
    return {"supported": True, "allowed": allowed,
            "message": "Windows Firewall already lets friends in." if allowed else "Windows Firewall has no rule for your server yet."}


def allow(port: int, run=_run) -> dict:
    """Add the rule, asking Windows for approval when not already an administrator."""
    if not supported():
        return {"supported": False, "allowed": True, "message": "Not needed on this system."}
    already = status(port, run)
    if already["allowed"]:
        return already
    try:
        if exists(run):          # an old rule for another port or program would never match: replace it, do not pile up copies
            remove(run)
        direct = run(["netsh"] + rule_args(port))
        if direct.returncode != 0:
            _elevated(rule_args(port), run)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"supported": True, "allowed": False, "message": f"Windows did not allow the change ({exc})."}
    now = status(port, run)
    if now["allowed"]:
        now["message"] = "Done. Windows Firewall now lets friends connect to your server."
    else:
        now["message"] = "The rule was not added (the approval box was closed or refused). Friends on other networks may be blocked."
    return now


def exists(run=_run) -> bool:
    """Is there a Legacy Player rule in the Windows Firewall at all."""
    if not supported():
        return False
    try:
        out = run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE}"])
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and RULE in (out.stdout or "")


def remove(run=_run) -> dict:
    """Take the rule away again (used by the uninstaller). Asks Windows for approval when not already an administrator."""
    if not supported():
        return {"removed": True}
    args = ["advfirewall", "firewall", "delete", "rule", f"name={RULE}"]
    try:
        if run(["netsh"] + args).returncode != 0 and exists(run):
            _elevated(args, run)
    except (OSError, subprocess.SubprocessError):
        pass
    return {"removed": not exists(run)}
