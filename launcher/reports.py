"""Opt-in problem reports.

If something fails inside Legacy Player and the player has agreed, a short, scrubbed report is sent to the people who
maintain it so the problem can be fixed without anyone writing a ticket. Nothing is sent unless the player chose to:

  off   (default)  nothing is saved or sent. After the first failure the player is asked once what they want.
  ask              a report is prepared and the player reads it and decides, every time.
  auto             reports are sent as they happen, always scrubbed the same way.

What a report holds: the app version, the kind of computer (Windows version, 64-bit, Python), what failed (the error
type, a cleaned-up message and stack, which action or page), the last few actions' NAMES (never their contents), and
the kind of network (home, shared by the provider...). What it never holds: names, addresses (IP), paths to your
folders, game file locations, server or invite codes, keys, passwords, or anything another player typed. Everything is
cleaned before it is stored, and the player can read the exact text first.
"""
from __future__ import annotations

import collections
import getpass
import hashlib
import json
import os
import platform
import ipaddress
import re
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .version import REPORT_URL, VERSION

MODES = ("off", "ask", "auto")
SCHEMA = "legacy_player.report.v1"
SAME_PROBLEM_WINDOW = 600          # seconds in which the same failure is counted, not reported again
PROMPT_GAP = 1800                  # seconds between asking
MAX_PENDING = 30
MAX_SENDS_PER_HOUR = 10
MAX_TEXT = 4000
NOISY = {"ping", "status", "mp_state", "server_status", "network_last", "setup_status", "pads", "bye", "specs", "keyboard",
         "home", "probe_status", "report_status"}

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?\b")
# Any IPv6 form (::1, fe80::1%eth0, 2001:db8::5, [::1]:8765, ::ffff:1.2.3.4): find candidates, then let `ipaddress` decide.
_IPV6_CANDIDATE = re.compile(r"(?<![\w:.])\[?[0-9A-Fa-f:]*:[0-9A-Fa-f:]*:?[0-9A-Fa-f:.]*(?:%[\w.-]+)?\]?(?::\d{1,5})?(?![\w:])")
_MAC = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
_URL = re.compile(r"\b[a-z][a-z0-9+.-]{1,12}://[^\s'\"<>]+", re.I)
_HOST_PORT = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+(?!(?:py|pyc|js|html?|css|json|txt|log|md|bat|ps1|exe|dll|ya?ml|toml|ini|cfg|lock|spec)\b)[A-Za-z]{2,}:\d{2,5}\b")
_LONG_HEX = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_ASSIGNED_SECRET = re.compile(r"(?i)\b(access[_-]?key|api[_-]?key|token|secret|password|passwd|credential|authorization|bearer|fingerprint|join[_-]?code|invite[_-]?code)\b(\s*[:=]\s*|\s+)(?:\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_SERVER_CODE = re.compile(r"\bLP2?-[A-Z0-9-]{8,}\b", re.I)
_INVITE = re.compile(r"\b[A-Z0-9]{5}-[A-Z0-9]{5}\b")
_INVITE_LOWER = re.compile(r"\b(?=[a-z0-9]{0,4}\d)[a-z0-9]{5}-[a-z0-9]{5}\b|\b[a-z0-9]{5}-(?=[a-z0-9]{0,4}\d)[a-z0-9]{5}\b")
_SECRETISH = re.compile(r"\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{24,}\b")
_URL_QUERY = re.compile(r"(\?[^\s'\"]+)")
_WIN_PATH = re.compile(r"(?<!\w)[A-Za-z]:[\\/](?:[^\\/:*?\"<>|\r\n']+[\\/])*[^\\/:*?\"<>|\r\n'\s]*")
_UNC_PATH = re.compile(r"\\\\[\w.$-]+(?:\\[^\\/:*?\"<>|\r\n'\s]+)*")
_HOSTNAME = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+(?:duckdns\.org|ddns\.net|no-ip\.(?:org|com|biz)|dyndns\.[a-z]+|hopto\.org|zapto\.org|ngrok(?:-free)?\.(?:io|app|dev)|trycloudflare\.com|tailscale\.net|ts\.net|local|lan|home|internal)(?::\d{1,5})?\b", re.I)
_NIX_PATH = re.compile(r"(?<![\w:/])/(?:[\w.@+-]+/)+[\w.@+-]*")
_CODE_DIRS = ("launcher", "server", "adapters", "runtime", "frontend", "tools", "site-packages", "lib", "Lib")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):          # a report goes to the address that was set, never somewhere it points to
        return None


def _no_redirect_open(request, timeout=10):
    return urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Scrubber:
    """Removes what identifies a person or opens a door. `names` are exact strings to blank (user name, PC name, ...)."""

    def __init__(self, names: dict[str, str] | None = None, folders: dict[str, str] | None = None) -> None:
        self.names = {k: v for k, v in (names or {}).items() if k and len(k) >= 2}
        self.folders = sorted(((k, v) for k, v in (folders or {}).items() if k and len(k) >= 4), key=lambda kv: -len(kv[0]))

    def _path(self, match: re.Match) -> str:
        path = match.group(0)
        parts = re.split(r"[\\/]", path)
        for i, part in enumerate(parts):
            if part in _CODE_DIRS and i > 0:                  # keep where in OUR code it was; drop everything before
                return ".../" + "/".join(parts[i:])
        ext = os.path.splitext(parts[-1])[1][:8] if parts and "." in parts[-1] else ""
        return "<path>" + ext

    @staticmethod
    def _url(match: re.Match) -> str:
        url = match.group(0)
        host = re.sub(r"^[a-z][a-z0-9+.-]*://(?:[^/@]*@)?", "", url, flags=re.I).split("/")[0].split(":")[0].lower()
        if host in ("github.com", "pypi.org", "python.org", "docs.python.org") or host.endswith(".github.com"):
            return url.split("?")[0].split("#")[0] + ("?<removed>" if "?" in url else "")        # our own public places stay readable
        return "<url>"

    @staticmethod
    def _ipv6(match: re.Match) -> str:
        token = match.group(0)
        core = re.sub(r"^\[|\]?(?::\d{1,5})?$", "", token) if token.startswith("[") else token
        core = core.split("%")[0].strip("[]")
        for candidate in (core, token.split("%")[0]):
            try:
                ipaddress.IPv6Address(candidate)
                return "<ip>"
            except ValueError:
                pass
        return token

    def text(self, value, limit: int = MAX_TEXT) -> str:
        s = str(value if value is not None else "")
        for folder, label in self.folders:
            s = re.sub(re.escape(folder), label, s, flags=re.I)
            s = re.sub(re.escape(folder.replace("\\", "/")), label, s, flags=re.I)
        s = _ASSIGNED_SECRET.sub(lambda m: f"{m.group(1)}=<removed>", s)
        s = _URL.sub(self._url, s)
        s = _UNC_PATH.sub(self._path, s)
        s = _WIN_PATH.sub(self._path, s)
        s = _HOSTNAME.sub("<host>", s)
        s = _HOST_PORT.sub("<host>", s)
        s = _NIX_PATH.sub(self._path, s)
        for name, label in self.names.items():
            s = re.sub(re.escape(name), label, s, flags=re.I)
        s = _SERVER_CODE.sub("<server code>", s)
        s = _EMAIL.sub("<email>", s)
        s = _MAC.sub("<mac>", s)
        s = _IPV6_CANDIDATE.sub(self._ipv6, s)
        s = _IPV4.sub(lambda m: m.group(0) if m.group(0).startswith(("127.0.0.1", "0.0.0.0")) else "<ip>", s)
        s = _INVITE.sub("<invite code>", s)
        s = _INVITE_LOWER.sub("<invite code>", s)
        s = _LONG_HEX.sub("<hex>", s)
        s = _SECRETISH.sub("<secret>", s)
        s = _URL_QUERY.sub("?<removed>", s)
        return s[:limit]

    def data(self, value, depth: int = 0):
        if depth > 5:
            return None
        if isinstance(value, dict):
            return {str(k)[:60]: self.data(v, depth + 1) for k, v in list(value.items())[:60]}
        if isinstance(value, (list, tuple)):
            return [self.data(v, depth + 1) for v in list(value)[:60]]
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return self.text(value, 600)


def fingerprint(kind: str, error_type: str, trace: str, context: dict) -> str:
    """The same bug should look the same from every computer, so the maintainers count it once."""
    frames = re.findall(r"(?:\.\.\./)?((?:launcher|server|adapters|runtime|frontend|tools)/[\w/.]+)\", line (\d+), in (\w+)", trace or "")
    where = "|".join(f"{f}:{n}:{fn}" for f, n, fn in frames[-3:]) or str(context.get("api") or context.get("page") or "")
    return hashlib.sha1(f"{kind}|{error_type}|{where}".encode()).hexdigest()[:12]


class ReportCenter:
    def __init__(self, data_dir: Path, settings, set_setting, extra=None) -> None:
        """`settings()` returns the current settings dict; `set_setting(key, value)` changes one; `extra()` returns more
        context (network kind, what is running) without addresses."""
        self.dir = Path(data_dir) / "reports"
        self.settings, self.set_setting, self.extra = settings, set_setting, extra or (lambda: {})
        self.data_dir = Path(data_dir)
        self.crumbs: collections.deque = collections.deque(maxlen=25)
        self.lock = threading.RLock()
        self.held: dict | None = None            # one report kept in memory while the mode is "off", for the one-time question
        self.seen: dict[str, float] = {}
        self.sent_at: collections.deque = collections.deque(maxlen=MAX_SENDS_PER_HOUR)
        self.last_prompt = 0.0
        self.t0 = time.time()
        self.opener = _no_redirect_open
        self.last_error = ""

    # --- settings ---------------------------------------------------------------------------------------
    def mode(self) -> str:
        m = self.settings().get("error_reports", "off")
        return m if m in MODES else "off"

    def url(self) -> str:
        return (self.settings().get("report_url") or REPORT_URL or "").strip()

    # --- building ---------------------------------------------------------------------------------------
    def _scrubber(self) -> Scrubber:
        names = {}
        try:
            names[getpass.getuser()] = "<user>"
        except Exception:
            pass
        for key in ("COMPUTERNAME", "USERNAME", "USER"):
            if os.environ.get(key):
                names[os.environ[key]] = "<user>" if key != "COMPUTERNAME" else "<pc>"
        try:
            names[socket.gethostname()] = "<pc>"
        except Exception:
            pass
        try:
            shown = (self.settings().get("display_name") or "").strip()
            if shown and shown.lower() != "player":
                names[shown] = "<name>"
        except Exception:
            pass
        folders = {str(Path.home()): "<home>", str(self.data_dir): "<data>"}
        try:
            for root in self.extra().get("_roots", []):
                folders[str(root)] = "<games>"
        except Exception:
            pass
        return Scrubber(names, folders)

    def crumb(self, name: str, status: int | str) -> None:
        if name in NOISY:
            return
        self.crumbs.append({"t": round(time.time() - self.t0), "what": str(name)[:40], "result": status})

    def build(self, kind: str, exc: BaseException | None = None, message: str = "", context: dict | None = None) -> dict:
        sc = self._scrubber()
        context = dict(context or {})
        trace = ""
        etype = type(exc).__name__ if exc is not None else kind
        text = message or (str(exc) if exc is not None else "")
        if exc is not None:
            trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-12:])
        extra = {k: v for k, v in self.extra().items() if not k.startswith("_")}
        clean_trace = sc.text(trace, 6000)
        return {
            "schema": SCHEMA, "id": uuid.uuid4().hex[:12], "created": _now(), "kind": kind,
            "fingerprint": fingerprint(kind, etype, clean_trace, context), "occurrences": 1,
            "app": {"version": VERSION, "packaged": bool(getattr(sys, "frozen", False))},
            "system": {"os": platform.system(), "release": platform.release(), "version": platform.version()[:40],
                       "machine": platform.machine(), "python": platform.python_version()},
            "error": {"type": etype, "message": sc.text(text, 800), "trace": clean_trace},
            "context": sc.data(context), "network": sc.data(extra.get("network") or {}), "doing": sc.data(extra.get("doing") or {}),
            "recent_actions": list(self.crumbs),
        }

    # --- the front door -------------------------------------------------------------------------------
    def capture(self, kind: str, exc: BaseException | None = None, message: str = "", context: dict | None = None) -> dict | None:
        """Called wherever something fails. Safe to call anywhere: it never raises and never blocks the caller."""
        try:
            return self._capture(kind, exc, message, context)
        except Exception:
            return None

    def _capture(self, kind, exc, message, context):
        mode = self.mode()
        report = self.build(kind, exc, message, context)
        with self.lock:
            last = self.seen.get(report["fingerprint"], 0)
            if time.time() - last < SAME_PROBLEM_WINDOW:
                self._count_again(report["fingerprint"])
                return None
            self.seen[report["fingerprint"]] = time.time()
            if mode == "off":
                self.held = report                       # memory only; nothing touches the disk
                return report
            self._save(report)
        if mode == "auto":
            threading.Thread(target=self.send, args=(report["id"],), daemon=True, name="report-send").start()
        return report

    def _count_again(self, fp: str) -> None:
        if self.held and self.held.get("fingerprint") == fp:
            self.held["occurrences"] += 1
        for r in self.pending():
            if r.get("fingerprint") == fp:
                r["occurrences"] = r.get("occurrences", 1) + 1
                self._write(r)

    # --- storage ----------------------------------------------------------------------------------------
    def _write(self, report: dict) -> None:
        folder = self.dir / "pending"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{report['id']}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    def _save(self, report: dict) -> None:
        self._write(report)
        items = sorted((self.dir / "pending").glob("*.json"), key=lambda p: p.stat().st_mtime)
        for old in items[:-MAX_PENDING]:
            try:
                old.unlink()
            except OSError:
                pass

    def pending(self) -> list[dict]:
        out = []
        for p in sorted((self.dir / "pending").glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out

    def get(self, rid: str) -> dict | None:
        if self.held and self.held["id"] == rid:
            return self.held
        path = self.dir / "pending" / f"{re.sub(r'[^a-f0-9]', '', rid)}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def discard(self, rid: str | None = None) -> int:
        n = 0
        with self.lock:
            if self.held and (rid is None or self.held["id"] == rid):
                self.held, n = None, n + 1
            for p in list((self.dir / "pending").glob("*.json")):
                if rid is None or p.stem == rid:
                    try:
                        p.unlink()
                        n += 1
                    except OSError:
                        pass
        return n

    # --- sending ----------------------------------------------------------------------------------------
    def send(self, rid: str) -> dict:
        """Send one report the player has agreed to send. Returns {"sent": bool, "why": str}."""
        report = self.get(rid)
        if report is None:
            return {"sent": False, "why": "That report is no longer here."}
        url = self.url()
        if not url:
            return {"sent": False, "why": "Sending is not connected in this build yet, so the report stays on this computer. You can copy it."}
        if not (url.startswith("https://") or re.match(r"http://(127\.0\.0\.1|localhost)(:\d+)?/", url + "/")):
            return {"sent": False, "why": "The report address must start with https://."}
        now = time.time()
        with self.lock:
            while self.sent_at and now - self.sent_at[0] > 3600:
                self.sent_at.popleft()
            if len(self.sent_at) >= MAX_SENDS_PER_HOUR:
                return {"sent": False, "why": "Too many reports in the last hour; this one will wait."}
            self.sent_at.append(now)
        body = json.dumps(report).encode("utf-8")
        request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "User-Agent": f"LegacyPlayer/{VERSION}"})
        try:
            with self.opener(request, timeout=10) as response:
                ok = 200 <= getattr(response, "status", 200) < 300
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.last_error = str(exc)[:200]
            return {"sent": False, "why": "Could not reach the report address. It stays here and can be sent later."}
        if not ok:
            return {"sent": False, "why": "The report address did not accept it."}
        self.discard(rid)
        return {"sent": True, "why": ""}

    def send_all(self) -> dict:
        sent = 0
        for r in self.pending():
            if self.send(r["id"])["sent"]:
                sent += 1
        return {"sent": sent, "left": len(self.pending())}

    # --- what the window needs ------------------------------------------------------------------------
    def prompt(self) -> dict | None:
        """A report waiting for the player's decision, or None."""
        mode = self.mode()
        with self.lock:
            if mode == "off":
                if self.held and not self.settings().get("report_prompt_seen") and time.time() - self.last_prompt > PROMPT_GAP:
                    self.last_prompt = time.time()
                    return {"id": self.held["id"], "kind": self.held["kind"], "message": self.held["error"]["message"], "mode": "off"}
                return None
            if mode == "ask" and time.time() - self.last_prompt > PROMPT_GAP:
                waiting = self.pending()
                if waiting:
                    self.last_prompt = time.time()
                    r = waiting[-1]
                    return {"id": r["id"], "kind": r["kind"], "message": r["error"]["message"], "mode": "ask"}
        return None

    def status(self) -> dict:
        return {"mode": self.mode(), "pending": len(self.pending()) + (1 if self.held else 0), "connected": bool(self.url()),
                "address": self.url() or None, "folder": str(self.dir / "pending")}

    def decide(self, rid: str, choice: str) -> dict:
        """The answer to the question in the window."""
        if choice == "send":
            if self.held and self.held["id"] == rid and self.mode() == "off":
                with self.lock:
                    self._save(self.held)
                    self.held = None
            return self.send(rid)
        if choice == "later":
            self.last_prompt = time.time()
            return {"ok": True}
        if choice == "never":
            self.set_setting("report_prompt_seen", True)
            self.set_setting("error_reports", "off")
            self.discard()
            return {"ok": True}
        if choice in ("always_ask", "auto"):
            self.set_setting("report_prompt_seen", True)
            self.set_setting("error_reports", "ask" if choice == "always_ask" else "auto")
            with self.lock:
                if self.held:
                    self._save(self.held)
                    held, self.held = self.held, None
                    if choice == "auto":
                        return self.send(held["id"])
            return {"ok": True}
        if choice == "skip":
            self.discard(rid)
            return {"ok": True}
        raise ValueError("unknown choice")


def install_hooks(center: ReportCenter) -> None:
    """Failures nobody caught: the main program and background threads."""
    previous = sys.excepthook

    def main_hook(etype, evalue, tb):
        center.capture("crash", evalue, context={"where": "main"})
        previous(etype, evalue, tb)
    sys.excepthook = main_hook
    old_thread = threading.excepthook

    def thread_hook(args):
        if args.exc_type is not SystemExit:
            center.capture("thread-error", args.exc_value, context={"thread": (args.thread.name if args.thread else "?")})
        old_thread(args)
    threading.excepthook = thread_hook
