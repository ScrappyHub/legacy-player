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
import tempfile
from pathlib import Path

RULE = "Legacy Player server"
RULE_FRIENDS = "Legacy Player friends service"
_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def supported() -> bool:
    return sys.platform == "win32"


def _run(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=_FLAGS)


def rule_args(port: int, program: str | None = None, rule: str = RULE) -> list[str]:
    """Every network profile on purpose (hotspots count as "public"), but when the app is the packaged exe the rule
    only lets that one program accept connections, not whatever else might listen on the port."""
    if program is None and getattr(sys, "frozen", False):
        program = sys.executable
    args = ["advfirewall", "firewall", "add", "rule", f"name={rule}", "dir=in", "action=allow", "protocol=TCP",
            f"localport={int(port)}", "profile=any"]
    if program:
        args.append(f"program={program}")
    return args


def _line(args: list[str]) -> str:
    return " ".join(f'"{a}"' if (" " in a or "\\" in a) else a for a in args)


def _elevated(args: list[str], run, before: tuple = ()) -> dict:
    """Run netsh as administrator through the Windows approval box and report what happened. One approval covers everything:
    the commands in `before` (for example deleting an old rule) and then `args`.
    The commands go into a small script file so there is no quoting to get wrong, netsh's own words are written to a log file so a
    failure can say why, and netsh's exit code for the LAST command is recorded (so success does not depend on the language of
    its messages). Returns {"cancelled", "ok", "log", "error"}."""
    folder = Path(tempfile.gettempdir())
    script, log = folder / "lp-firewall.cmd", folder / "lp-firewall.log"
    lines = ["@echo off"] + [f'netsh {_line(a)} >> "{log}" 2>&1' for a in before]
    lines += [f'netsh {_line(args)} >> "{log}" 2>&1', f'echo LP_EXIT=%errorlevel%>> "{log}"']
    try:
        log.unlink(missing_ok=True)
        script.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", errors="replace")
    except OSError as exc:
        return {"cancelled": False, "ok": False, "log": "", "error": f"Could not prepare the command: {exc}"}
    quoted = str(script).replace("'", "''")
    result = run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                  f"Start-Process -FilePath '{quoted}' -Verb RunAs -Wait -WindowStyle Hidden"], timeout=120)
    err = str(getattr(result, "stderr", "") or "").strip()
    text = ""
    try:
        text = log.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        pass
    for f in (script, log):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass
    ok = bool(re.search(r"LP_EXIT=0\b", text))
    shown = "\n".join(l for l in text.splitlines() if not l.startswith("LP_EXIT=")).strip()
    return {"cancelled": ("cancel" in err.lower()) and not text, "ok": ok, "log": shown[:400], "error": err[:300]}


def manual_command(port: int, rule: str = RULE) -> str:
    """What to paste into an administrator PowerShell if the approval box does not work."""
    return (f'netsh advfirewall firewall delete rule name="{rule}"; '
            f'netsh advfirewall firewall add rule name="{rule}" dir=in action=allow protocol=TCP localport={int(port)} profile=any')


def _program_matches(program: str, text: str) -> bool:
    """The rule is fine when it names this program (by file name, so path spelling cannot matter) or names no program at all
    ("Any", in any language), as a rule added by hand does. A rule for a different program does not count."""
    m = re.search(r"^\s*Program:\s*(.+?)\s*$", text, re.M)
    if m is None:
        return True          # Windows prints no Program line at all for a rule that is not tied to a program (as one added by hand)
    if not re.search(r"[\\/]|\.exe", m.group(1), re.I):
        return True          # "Any" in whatever language
    return Path(program).name.lower() in m.group(1).lower()


def status(port: int, run=_run, rule: str = RULE) -> dict:
    if not supported():
        return {"supported": False, "allowed": True, "message": "Not needed on this system."}
    try:
        out = run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule}"])
    except (OSError, subprocess.SubprocessError):
        return {"supported": True, "allowed": False, "message": "Could not read the Windows Firewall."}
    text = out.stdout or ""
    ports = re.findall(r"^\s*LocalPort:\s*(\S+)", text, re.M)          # exact port, not a substring (87 must not match 8765); other Windows languages: bare number
    port_ok = str(int(port)) in [x.strip() for x in ports] or (not ports and re.search(rf"(?<!\d){int(port)}(?!\d)", text) is not None)
    program = rule_args(port, rule=rule)[-1][len("program="):] if rule_args(port, rule=rule)[-1].startswith("program=") else ""
    program_ok = (not program) or _program_matches(program, text)
    allowed = out.returncode == 0 and port_ok and program_ok
    return {"supported": True, "allowed": allowed, "seen": {"found": out.returncode == 0, "port_ok": port_ok, "program_ok": program_ok},
            "message": "Windows Firewall already lets friends in." if allowed else "Windows Firewall has no rule for your server yet."}


def allow(port: int, run=_run, rule: str = RULE) -> dict:
    """Add the rule, asking Windows for approval when not already an administrator."""
    if not supported():
        return {"supported": False, "allowed": True, "message": "Not needed on this system."}
    already = status(port, run, rule)
    if already["allowed"]:
        return already
    detail: dict = {}
    delete_args = ["advfirewall", "firewall", "delete", "rule", f"name={rule}"]
    try:
        old_rule_stays = False
        if exists(run, rule):          # an old rule for another port or program would never match: replace it, do not pile up copies
            old_rule_stays = run(["netsh"] + delete_args).returncode != 0
        direct = None if old_rule_stays else run(["netsh"] + rule_args(port, rule=rule))
        if direct is None or direct.returncode != 0:
            detail = _elevated(rule_args(port, rule=rule), run, before=(delete_args,) if old_rule_stays else ()) or {}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"supported": True, "allowed": False, "message": f"Windows did not allow the change ({exc}).", "manual": manual_command(port, rule)}
    now = status(port, run, rule)
    if now["allowed"] or detail.get("ok"):
        # netsh itself said it worked (exit code 0): believe it even if reading the rule back is picky
        now["allowed"] = True
        now["message"] = "Done. Windows Firewall now lets friends connect to your server."
        return now
    if detail.get("cancelled"):
        why = "You closed or refused the Windows approval box."
    elif detail.get("log"):
        why = f"Windows said: {detail['log']}"
    elif detail.get("error"):
        why = f"Windows said: {detail['error']}"
    else:
        why = "Windows did not report a reason."
    now["message"] = f"The rule was not added. {why} Friends on other networks may be blocked."
    now["manual"] = manual_command(port, rule)
    return now


def exists(run=_run, rule: str = RULE) -> bool:
    """Is there a Legacy Player rule in the Windows Firewall at all."""
    if not supported():
        return False
    try:
        out = run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule}"])
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and rule in (out.stdout or "")


def remove(run=_run) -> dict:
    """Take the rules away again (used by the uninstaller). Asks Windows for approval when not already an administrator."""
    if not supported():
        return {"removed": True}
    for rule in (RULE, RULE_FRIENDS):
        args = ["advfirewall", "firewall", "delete", "rule", f"name={rule}"]
        try:
            if exists(run, rule) and run(["netsh"] + args).returncode != 0 and exists(run, rule):
                _elevated(args, run)
        except (OSError, subprocess.SubprocessError):
            pass
    return {"removed": not exists(run) and not exists(run, RULE_FRIENDS)}
