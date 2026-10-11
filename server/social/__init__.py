"""The friends layer: a small, separate service for finding friends, seeing who is online, inviting them into a room
and sending short messages. It is not part of the lobby server and Legacy Player works fully without it.

No sign-ups. A player's app asks the service for an identity once ("hello" with a display name) and gets back a
player id, a secret that only that app keeps, and a short friend code (like "MK7-4Q2X") to give to friends. Nothing
else is ever asked: no e-mail, no password, no account. The service remembers a player for 60 days after their last
visit, then forgets them.

What it keeps per player: the name they chose, the friend code, their friends, pending requests, the invites and
messages waiting for them (messages for 7 days, 200 per pair), and a presence line their app refreshes while it is
open: online or not, and, if they chose to share it, the room they are in (an invite code and the server code that
reaches it) so a friend can join with one click. It never sees game traffic, addresses, or anything about the computer.

Run it with   python -m server.social --dir social --port 8791   and put HTTPS in front of it (the app only talks to
https:// addresses, or to 127.0.0.1 while testing). The address goes under Settings > Friends in Legacy Player, or next
to the lobby server's code in a shared set-up.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import textfilter

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"            # no 0/O or 1/I: codes are read out loud
FORGET_AFTER = 60 * 86400
ONLINE_WINDOW = 75.0                                       # a heartbeat every 30 s keeps a player online
MESSAGE_KEEP = 7 * 86400
MESSAGES_PER_PAIR = 200
MAX_FRIENDS = 200
MAX_NAME = 24
MAX_TEXT = 500
PER_MINUTE = 120                                           # calls per player per minute
MESSAGES_PER_MINUTE = 20                                   # a friend cannot flood a conversation
REQUESTS_PER_HOUR = 20                                     # nor send friend requests to every code they can guess
REPORTS_PER_DAY = 20
REPORT_CATEGORIES = ("harassment", "hate", "threats", "spam", "scam", "sexual", "name", "cheating", "other")
TIMEOUTS = {"1h": 3600, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}
MAX_PLAYERS = 100_000                                      # the whole service: hello stops making identities beyond this
SAVE_EVERY = 2.0                                           # seconds: ordinary changes are written at most this often
TIDY_EVERY = 60.0                                          # seconds (service clock) between full tidy passes


def _log(line: str) -> None:
    """One line for the service's own log. Never a player's words, ids or any address."""
    try:
        print(f"friends service: {line}", file=sys.stderr, flush=True)
    except Exception:
        pass


def _small_int(value, limit: int = 64) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(limit, number))


def _str_list(value) -> list:
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def _clean_player(p) -> dict | None:
    """A player entry as read from disk, with every field the rules rely on; None when it can't be used."""
    if not isinstance(p, dict) or not all(isinstance(p.get(k), str) and p.get(k) for k in ("code", "secret")):
        return None
    out = dict(p)
    out["name"] = clean_name(p.get("name"))
    for key in ("friends", "requests_in", "requests_out", "blocked"):
        out[key] = _str_list(p.get(key))
    seen = p.get("seen")
    out["seen"] = float(seen) if isinstance(seen, (int, float)) and not isinstance(seen, bool) else 0.0
    out["status"] = p.get("status") if isinstance(p.get("status"), str) else ""
    out["room"] = p.get("room") if isinstance(p.get("room"), dict) else None
    invites = p.get("invites") if isinstance(p.get("invites"), list) else []
    out["invites"] = [i for i in invites if isinstance(i, dict) and isinstance(i.get("at"), (int, float))]
    messages = p.get("messages") if isinstance(p.get("messages"), dict) else {}
    out["messages"] = {str(k): [m for m in v if isinstance(m, dict) and isinstance(m.get("at"), (int, float))
                                and isinstance(m.get("from"), str) and isinstance(m.get("text"), str)]
                       for k, v in messages.items() if isinstance(v, list)}
    out["requests_open"] = bool(p.get("requests_open", True))
    return out


class SocialError(ValueError):
    """A message safe to show the player."""


def make_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(3)) + "-" + "".join(secrets.choice(ALPHABET) for _ in range(4))


def clean_name(name) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", "", str(name or "")).strip()[:MAX_NAME]
    return text or "Player"


def clean_text(text, limit: int = MAX_TEXT) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(text or "")).strip()[:limit]


class SocialService:
    """All the rules, no network. The HTTP layer in server/social/__main__.py is a thin wrapper."""

    def __init__(self, folder: Path | None, clock=time.time) -> None:
        self.folder = Path(folder) if folder else None
        self.clock = clock
        self.lock = threading.RLock()
        self.players: dict[str, dict] = {}     # id -> {name, secret, code, friends: [ids], requests_in: [ids], requests_out: [ids],
        #                                           seen, status, room, invites: [..], messages: {friend_id: [..]}, minute: [window, count]}
        self.codes: dict[str, str] = {}        # friend code -> player id
        # moderation: bans and timeouts by player id, reports from players, and the service-wide word filter
        self.mod: dict = {"bans": {}, "mutes": {}, "reports": [], "filter": {"on": False, "words": []}, "log": []}
        self._dirty = False
        self._last_save = float("-inf")       # time.monotonic() of the last write
        self._timer: threading.Timer | None = None
        self._tidied = float("-inf")          # service clock of the last full tidy
        self._load()

    # --- storage --------------------------------------------------------------------------------------------------
    def _load(self) -> None:
        if self.folder is None:
            return
        path = self.folder / "players.json"
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return
        except OSError as exc:
            # Unreadable right now (locked, permissions): never start empty, or the next save would wipe the bans.
            raise RuntimeError(f"could not read {path.name} ({type(exc).__name__}); not starting so it is not overwritten") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("players", {}), dict) or not isinstance(data.get("mod", {}), dict):
                raise ValueError("not a players file")
        except (ValueError, RecursionError) as exc:
            kept = path.with_name(f"players.json.corrupt-{int(time.time())}")
            try:
                os.replace(path, kept)
                where = f"kept it as {kept.name}"
            except OSError:
                where = "could not move it aside"
            _log(f"players.json could not be read ({type(exc).__name__}); {where} and started with an empty list. "
                 "The bans and reports in it are not active until it is repaired and put back.")
            return
        skipped = 0
        for pid, p in (data.get("players") or {}).items():
            clean = _clean_player(p)
            if clean is None or clean["code"] in self.codes:
                skipped += 1
                continue
            self.players[pid] = clean
            self.codes[clean["code"]] = pid
        mod = data.get("mod") or {}
        for key, kind in (("bans", dict), ("mutes", dict), ("reports", list), ("filter", dict), ("log", list)):
            if isinstance(mod.get(key), kind):
                self.mod[key] = mod[key]
        self.mod["bans"] = {str(k): (v if isinstance(v, dict) else {}) for k, v in self.mod["bans"].items()}
        self.mod["mutes"] = {str(k): v for k, v in self.mod["mutes"].items()
                             if isinstance(v, dict) and isinstance(v.get("until"), (int, float))}
        self.mod["reports"] = [r for r in self.mod["reports"] if isinstance(r, dict) and isinstance(r.get("id"), str)
                               and isinstance(r.get("target"), dict) and isinstance(r["target"].get("id"), str)
                               and isinstance(r.get("status"), str)]
        self.mod["log"] = [entry for entry in self.mod["log"] if isinstance(entry, dict)]
        f = self.mod["filter"]
        self.mod["filter"] = {"on": bool(f.get("on")), "words": _str_list(f.get("words"))}
        if skipped:
            _log(f"skipped {skipped} unreadable player entr{'y' if skipped == 1 else 'ies'} in players.json")

    def save(self) -> None:
        """Write everything now: a whole new file, flushed to disk, then swapped in, so a crash or a power cut leaves
        either the old file or the new one, never half of one."""
        if self.folder is None:
            return
        with self.lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            data = json.dumps({"players": self.players, "mod": self.mod}).encode("utf-8")
            fd, tmp = tempfile.mkstemp(prefix=".players-", suffix=".tmp", dir=self.folder)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                try:
                    os.chmod(tmp, 0o600)
                except OSError:
                    pass
                os.replace(tmp, self.folder / "players.json")
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            if hasattr(os, "O_DIRECTORY"):                 # make the rename itself durable (POSIX)
                try:
                    dfd = os.open(self.folder, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(dfd)
                    finally:
                        os.close(dfd)
                except OSError:
                    pass
            self._dirty = False
            self._last_save = time.monotonic()

    def _changed(self, urgent: bool = False) -> None:
        """Something changed. Moderation and leaving are written at once; everything else at most every SAVE_EVERY
        seconds (the first change after a quiet spell is written at once, later ones are gathered into one write)."""
        if self.folder is None:
            return
        with self.lock:
            self._dirty = True
            wait = SAVE_EVERY - (time.monotonic() - self._last_save)
            if urgent or wait <= 0:
                try:
                    self.save()
                except OSError as exc:
                    _log(f"could not save players.json ({type(exc).__name__}); trying again shortly")
                    self._schedule(SAVE_EVERY)
                return
            self._schedule(wait)

    def _schedule(self, delay: float) -> None:
        if self._timer is not None:
            return
        self._timer = threading.Timer(max(0.05, delay), self._timer_fired)
        self._timer.daemon = True
        self._timer.start()

    def _timer_fired(self) -> None:
        with self.lock:
            self._timer = None
            if self._dirty:
                try:
                    self.save()
                except OSError as exc:
                    _log(f"could not save players.json ({type(exc).__name__}); trying again shortly")
                    self._schedule(SAVE_EVERY)

    def flush(self) -> None:
        """Write anything not written yet (called when the service stops)."""
        with self.lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._dirty:
                self.save()

    # --- helpers ------------------------------------------------------------------------------------------------
    def _maybe_tidy(self) -> None:
        """The full pass is O(players): run it at most once a minute, not on every call."""
        if self.clock() - self._tidied >= TIDY_EVERY:
            self._tidy()

    def _tidy(self) -> None:
        now = self.clock()
        self._tidied = now
        for pid in [p for p, v in self.players.items() if now - v.get("seen", 0) > FORGET_AFTER and p not in self.mod["bans"]]:
            self._forget(pid)
        for pid, m in list(self.mod["mutes"].items()):
            if m.get("until", 0) <= now:
                del self.mod["mutes"][pid]
        for p in self.players.values():
            for fid, msgs in list(p.get("messages", {}).items()):
                keep = [m for m in msgs if now - m["at"] < MESSAGE_KEEP][-MESSAGES_PER_PAIR:]
                if keep:
                    p["messages"][fid] = keep
                else:
                    del p["messages"][fid]
            p["invites"] = [i for i in p.get("invites", []) if now - i["at"] < 3600]

    def _forget(self, pid: str) -> None:
        p = self.players.pop(pid, None)
        if not p:
            return
        self.codes.pop(p["code"], None)
        for other in self.players.values():
            for key in ("friends", "requests_in", "requests_out", "blocked"):
                if pid in other.get(key, []):
                    other[key].remove(pid)
            other.get("messages", {}).pop(pid, None)
            other["invites"] = [i for i in other.get("invites", []) if i.get("from") != pid]

    def _auth(self, pid: str, secret: str) -> dict:
        p = self.players.get(str(pid or ""))
        if p is None or not hmac.compare_digest(str(secret or "").encode("utf-8", "replace"), p["secret"].encode("utf-8", "replace")):
            raise SocialError("This app is not known to the friends service any more. Say hello again under Settings > Friends.")
        ban = self.mod["bans"].get(str(pid))
        if ban:
            raise SocialError("The moderators of this friends service banned this player" + (f": {ban.get('reason')}" if ban.get("reason") else ".")
                              + " You can't use friends, messages or invites here.")
        now = self.clock()
        window, count = p.get("minute") or [0, 0]
        if int(now // 60) != window:
            window, count = int(now // 60), 0
        if count >= PER_MINUTE:
            raise SocialError("Too many requests in a minute; wait a moment.")
        p["minute"] = [window, count + 1]
        p["seen"] = now
        return p

    def _muted(self, pid: str) -> dict | None:
        m = self.mod["mutes"].get(pid)
        return m if m and m.get("until", 0) > self.clock() else None

    def _may_talk(self, pid: str) -> None:
        m = self._muted(pid)
        if m:
            left = int(m["until"] - self.clock())
            when = f"{left // 3600} h {left % 3600 // 60} min" if left >= 3600 else f"{max(1, left // 60)} min"
            raise SocialError(f"A moderator paused your messages, invites and friend requests for another {when}"
                              + (f": {m.get('reason')}" if m.get("reason") else ".") )

    def _bump(self, p: dict, key: str, window: int, limit: int, what: str) -> None:
        now = self.clock()
        stamps = [t for t in p.get(key, []) if now - t < window]
        if len(stamps) >= limit:
            raise SocialError(f"Too many {what} in a short time; wait a little.")
        stamps.append(now)
        p[key] = stamps

    def _filtered(self, text: str) -> bool:
        f = self.mod["filter"]
        return bool(f.get("on")) and textfilter.has_bad(text, f.get("words"))

    def _online(self, p: dict) -> bool:
        return self.clock() - p.get("seen", 0) < ONLINE_WINDOW

    def _mutual(self, a: str, b: str) -> bool:
        """Friends on both sides and neither banned: a one-sided leftover never lets anything through."""
        pa, pb = self.players.get(a), self.players.get(b)
        return (pa is not None and pb is not None and b in pa.get("friends", []) and a in pb.get("friends", [])
                and a not in self.mod["bans"] and b not in self.mod["bans"])

    def _view(self, me: dict, other_id: str) -> dict:
        o = self.players.get(other_id) or {}
        room = o.get("room") if self._online(o) and o.get("room") else None
        return {"id": other_id, "name": o.get("name", "?"), "online": self._online(o), "status": o.get("status", "") if self._online(o) else "",
                "room": room, "unread": sum(1 for m in me.get("messages", {}).get(other_id, []) if not m.get("read") and m["from"] == other_id)}

    def _inbox(self, pid: str) -> dict:
        p = self.players[pid]
        friends = [self._view(p, f) for f in p.get("friends", []) if self._mutual(pid, f)]
        friends.sort(key=lambda f: (not f["online"], f["name"].lower()))
        return {"me": {"id": pid, "name": p["name"], "code": p["code"], "status": p.get("status", ""), "room": p.get("room")},
                "friends": friends,
                "requests": [{"id": r, "name": self.players.get(r, {}).get("name", "?")} for r in p.get("requests_in", []) if r in self.players],
                "sent": [{"id": r, "name": self.players.get(r, {}).get("name", "?")} for r in p.get("requests_out", []) if r in self.players],
                "invites": list(p.get("invites", [])),
                "conversations": self._conversations(pid),
                "blocked": [{"id": b, "name": self.players.get(b, {}).get("name", "?")} for b in p.get("blocked", []) if b in self.players],
                "unread": sum(f["unread"] for f in friends),
                "requests_open": p.get("requests_open", True),
                "moderation": ({"muted_until": self._muted(pid)["until"], "reason": self._muted(pid).get("reason", "")} if self._muted(pid) else None),
                "online": sum(1 for f in friends if f["online"])}

    def _conversations(self, pid: str) -> list[dict]:
        p = self.players[pid]
        out = []
        for other, msgs in p.get("messages", {}).items():
            if not msgs or other not in self.players:
                continue
            last = msgs[-1]
            out.append({"id": other, "name": self.players[other]["name"], "last": last["text"][:120], "at": last["at"], "mine": last["from"] == pid,
                        "unread": sum(1 for m in msgs if not m.get("read") and m["from"] == other), "online": self._online(self.players[other]),
                        "friend": other in p.get("friends", [])})
        out.sort(key=lambda c: -c["at"])
        return out

    def _blocks(self, a: str, b: str) -> bool:
        """True when either player has blocked the other."""
        return b in self.players.get(a, {}).get("blocked", []) or a in self.players.get(b, {}).get("blocked", [])

    # --- operations ---------------------------------------------------------------------------------------------
    def hello(self, name) -> dict:
        """A new identity: id, secret (kept only by that app) and a friend code."""
        with self.lock:
            self._maybe_tidy()
            if len(self.players) >= MAX_PLAYERS:
                self._tidy()
                if len(self.players) >= MAX_PLAYERS:
                    raise SocialError("This friends service is full right now. Try again later.")
            if self._filtered(clean_name(name)):
                raise SocialError("This friends service doesn't allow that name. Pick another under Settings > You.")
            pid = secrets.token_hex(8)
            code = make_code()
            while code in self.codes:
                code = make_code()
            self.players[pid] = {"name": clean_name(name), "secret": secrets.token_urlsafe(24), "code": code, "friends": [], "requests_in": [],
                                 "requests_out": [], "seen": self.clock(), "status": "", "room": None, "invites": [], "messages": {}, "blocked": [],
                                 "requests_open": True}
            self.codes[code] = pid
            self._changed()
            return {"id": pid, "secret": self.players[pid]["secret"], "code": code, "name": self.players[pid]["name"]}

    def heartbeat(self, pid, secret, name=None, status="", room=None, requests_open=None) -> dict:
        """The app says it is open (every 30 s), what the player is doing, and the room to share, then gets its inbox."""
        with self.lock:
            p = self._auth(pid, secret)
            before = (p["name"], p.get("requests_open", True))
            if name is not None and not self._filtered(clean_name(name)):
                p["name"] = clean_name(name)
            if requests_open is not None:
                p["requests_open"] = bool(requests_open)
            if (p["name"], p.get("requests_open", True)) != before:
                self._changed()        # presence itself is not written on every heartbeat (the tidy pass keeps it)
            muted = self._muted(str(pid)) is not None
            status = clean_text(status, 60)
            p["status"] = "" if muted or self._filtered(status) else status          # free text: the same rules as a message
            if isinstance(room, dict) and room.get("invite_code"):
                invite_code, server_code = clean_text(room.get("invite_code"), 14), clean_text(room.get("server_code"), 60)
                game = clean_text(room.get("game"), 80)
                p["room"] = None if self._filtered(invite_code + " " + server_code) else {
                    "invite_code": invite_code, "game": "" if muted or self._filtered(game) else game,
                    "server_code": server_code, "players": _small_int(room.get("players")),
                    "max_players": _small_int(room.get("max_players")), "at": self.clock()}
            else:
                p["room"] = None
            now = self.clock()
            p["invites"] = [i for i in p.get("invites", []) if now - i["at"] < 3600]
            self._maybe_tidy()
            return self._inbox(pid)

    def request(self, pid, secret, code) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            self._bump(p, "code_tries", 3600, 60, "friend code tries")      # codes can't be found by guessing
            code = re.sub(r"[^A-Z0-9]", "", str(code or "").upper())
            code = code[:3] + "-" + code[3:7] if len(code) >= 7 else code
            other_id = self.codes.get(code)
            if other_id is None or other_id not in self.players:
                raise SocialError("No player has that friend code. Check it with your friend (it looks like MK7-4Q2X).")
            if other_id == pid:
                raise SocialError("That is your own code.")
            if other_id in p.get("blocked", []):
                raise SocialError("You blocked this player. Unblock them first (Friends > Blocked).")
            if pid in self.players[other_id].get("blocked", []) or other_id in self.mod["bans"]:
                raise SocialError("No player has that friend code. Check it with your friend (it looks like MK7-4Q2X).")
            other = self.players[other_id]
            if other_id in p["friends"] and pid not in other.get("friends", []):
                p["friends"].remove(other_id)                            # a one-sided leftover is not a friendship
            if other_id not in p["friends"] and other_id not in p["requests_in"]:
                self._may_talk(pid)
                if not other.get("requests_open", True):
                    raise SocialError("That player isn't taking friend requests right now. Ask them to add your code instead.")
                self._bump(p, "req_times", 3600, REQUESTS_PER_HOUR, "friend requests")
            if other_id in p["friends"] and pid in other.get("friends", []):
                return {"ok": True, "already": True, **self._inbox(pid)}
            if len(p["friends"]) >= MAX_FRIENDS:
                raise SocialError("Your friends list is full.")
            if other_id in p["requests_in"]:                              # they asked first: this is a yes
                return self.decide(pid, secret, other_id, True)
            if other_id not in p["requests_out"]:
                p["requests_out"].append(other_id)
            if pid not in other["requests_in"]:
                other["requests_in"].append(pid)
            self._changed()
            return {"ok": True, "already": False, **self._inbox(pid)}

    def decide(self, pid, secret, other_id, accept) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            other_id = str(other_id or "")
            other = self.players.get(other_id)
            asked = other is not None and other_id in p["requests_in"]
            refused = not asked or self._blocks(pid, other_id) or other_id in self.mod["bans"]
            if accept and not refused:
                # checked before anything changes, so a full list leaves the request where it was
                if other_id not in p["friends"] and len(p["friends"]) >= MAX_FRIENDS:
                    raise SocialError("Your friends list is full.")
                if pid not in other["friends"] and len(other["friends"]) >= MAX_FRIENDS:
                    raise SocialError("That player's friends list is full.")
            if other_id in p["requests_in"]:
                p["requests_in"].remove(other_id)
            if other and pid in other.get("requests_out", []):
                other["requests_out"].remove(pid)
            if accept:
                # only a request that is really there, from someone neither side blocked, becomes a friendship
                if refused:
                    self._changed()
                    raise SocialError("That friend request is no longer here.")
                if other_id not in p["friends"]:
                    p["friends"].append(other_id)
                if pid not in other["friends"]:
                    other["friends"].append(pid)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def remove(self, pid, secret, other_id) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            other_id = str(other_id or "")
            for key in ("friends", "requests_out", "requests_in"):
                if other_id in p.get(key, []):
                    p[key].remove(other_id)
            other = self.players.get(other_id)
            if other:
                for key in ("friends", "requests_out", "requests_in"):
                    if pid in other.get(key, []):
                        other[key].remove(pid)
                other.get("messages", {}).pop(pid, None)
            p.get("messages", {}).pop(other_id, None)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def invite(self, pid, secret, to, invite_code, game, server_code="") -> dict:
        """Hand a friend the way into my room. Only friends can be invited, and only with a room invite code."""
        with self.lock:
            p = self._auth(pid, secret)
            to = str(to or "")
            if not self._mutual(str(pid), to) or self._blocks(pid, to):
                raise SocialError("You can only invite someone on your friends list.")
            self._may_talk(pid)
            code = clean_text(invite_code, 14)
            if not code:
                raise SocialError("Host a room first; the invite carries its code.")
            server_code, game = clean_text(server_code, 60), clean_text(game, 80)
            if self._filtered(code + " " + server_code):
                raise SocialError("This friends service doesn't allow some words in that invite, so it wasn't sent.")
            inv = {"from": pid, "name": p["name"], "invite_code": code, "game": "" if self._filtered(game) else game,
                   "server_code": server_code, "at": self.clock()}
            box = self.players[to]["invites"]
            box[:] = [i for i in box if i["from"] != pid]
            box.append(inv)
            del box[:-20]
            self._changed()
            return {"ok": True}

    def dismiss_invite(self, pid, secret, from_id) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            p["invites"] = [i for i in p.get("invites", []) if i["from"] != str(from_id or "")]
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def message(self, pid, secret, to, text) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            to = str(to or "")
            if not self._mutual(str(pid), to) or self._blocks(pid, to):
                raise SocialError("You can only message someone on your friends list.")
            self._may_talk(pid)
            text = clean_text(text)
            if not text:
                raise SocialError("Type something first.")
            if self._filtered(text):
                raise SocialError("This friends service doesn't allow some words in that message, so it wasn't sent.")
            self._bump(p, "msg_times", 60, MESSAGES_PER_MINUTE, "messages")
            m = {"id": secrets.token_hex(6), "from": pid, "to": to, "text": text, "at": self.clock()}
            for owner, other in ((pid, to), (to, pid)):
                box = self.players[owner].setdefault("messages", {}).setdefault(other, [])
                box.append(dict(m, read=(owner == pid)))
                del box[:-MESSAGES_PER_PAIR]
            self._changed()
            return {"ok": True, "messages": self._thread(pid, to)}

    def _thread(self, pid: str, other: str) -> list[dict]:
        msgs = self.players[pid].get("messages", {}).get(other, [])
        for m in msgs:
            m["read"] = True
        return [{"id": m.get("id", ""), "from": m["from"], "text": m["text"], "at": m["at"], "mine": m["from"] == pid} for m in msgs]

    def thread(self, pid, secret, other) -> dict:
        with self.lock:
            self._auth(pid, secret)
            other = str(other or "")
            if other not in self.players:
                return {"messages": []}
            out = {"messages": self._thread(pid, other), "name": self.players[other]["name"]}
            self._changed()
            return out

    def block(self, pid, secret, other) -> dict:
        """Block a player: no friendship, requests, invites or messages either way, and they no longer see you. They are not told."""
        with self.lock:
            p = self._auth(pid, secret)
            other = str(other or "")
            if other == pid or other not in self.players:
                raise SocialError("That player is not known to the friends service.")
            o = self.players[other]
            for a, b in ((p, other), (o, pid)):
                for key in ("friends", "requests_in", "requests_out"):
                    if b in a.get(key, []):
                        a[key].remove(b)
                a.get("messages", {}).pop(b, None)
                a["invites"] = [i for i in a.get("invites", []) if i.get("from") != b]
            p.setdefault("blocked", [])
            if other not in p["blocked"]:
                p["blocked"].append(other)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def unblock(self, pid, secret, other) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            other = str(other or "")
            if other in p.get("blocked", []):
                p["blocked"].remove(other)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def clear_thread(self, pid, secret, other) -> dict:
        """Delete a conversation from my inbox (the other player keeps their own copy)."""
        with self.lock:
            p = self._auth(pid, secret)
            p.get("messages", {}).pop(str(other or ""), None)
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    def read_all(self, pid, secret) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            for msgs in p.get("messages", {}).values():
                for m in msgs:
                    m["read"] = True
            self._changed()
            return {"ok": True, **self._inbox(pid)}

    # --- reports from players ------------------------------------------------------------------------------
    def _met(self, p: dict, pid: str, other: str) -> bool:
        """Only someone you have actually come across can be reported: a friend, a request either way, an invite, a
        conversation, or someone you blocked. Nobody can report a random id they never saw."""
        o = self.players.get(other, {})
        return (other in p.get("friends", []) or other in p.get("requests_in", []) or other in p.get("requests_out", [])
                or other in p.get("blocked", []) or other in p.get("messages", {}) or pid in o.get("requests_in", [])
                or any(i.get("from") == other for i in p.get("invites", [])))

    def report(self, pid, secret, target, category, details="", message_id="", also_block=False) -> dict:
        """Tell the moderators about a player, or one of their messages. The message is taken from the service's own copy
        (with the few before it, for context), so a report can't put words in someone's mouth."""
        with self.lock:
            p = self._auth(pid, secret)
            target = str(target or "")
            if target == pid or target not in self.players or not self._met(p, pid, target):
                raise SocialError("You can only report a player you have come across here.")
            if category not in REPORT_CATEGORIES:
                raise SocialError("Pick what the report is about.")
            self._bump(p, "report_times", 86400, REPORTS_PER_DAY, "reports")
            o = self.players[target]
            msgs = p.get("messages", {}).get(target, [])
            quoted, context = None, []
            if message_id:
                idx = next((i for i, m in enumerate(msgs) if m.get("id") == message_id and m["from"] == target), None)
                if idx is None:
                    raise SocialError("That message is no longer here, so it can't be reported. You can still report the player.")
                quoted = {"id": message_id, "text": msgs[idx]["text"], "at": msgs[idx]["at"]}
                context = [{"from": "reported" if m["from"] == target else "reporter", "text": m["text"], "at": m["at"]} for m in msgs[max(0, idx - 5):idx]]
            rid = secrets.token_hex(6)
            self.mod["reports"].append({"id": rid, "at": self.clock(), "status": "open", "category": category,
                                        "details": clean_text(details, 800), "reporter": {"id": pid, "name": p["name"]},
                                        "target": {"id": target, "name": o["name"], "code": o["code"]}, "message": quoted, "context": context})
            del self.mod["reports"][:-5000]
            self._changed(urgent=True)
        if also_block:
            return {"ok": True, "report": rid, **self.block(pid, secret, target)}
        with self.lock:
            return {"ok": True, "report": rid, **self._inbox(pid)}

    # --- the moderators (the console in server/social/__main__.py; never reachable with a player's secret) -------
    def _player_view(self, pid: str) -> dict:
        p = self.players.get(pid) or {}
        return {"id": pid, "name": p.get("name", "?"), "code": p.get("code", ""), "seen": p.get("seen"), "friends": len(p.get("friends", [])),
                "banned": self.mod["bans"].get(pid), "muted": self._muted(pid),
                "reports": sum(1 for r in self.mod["reports"] if r["target"]["id"] == pid)}

    def admin_reports(self, status: str = "") -> dict:
        with self.lock:
            self._tidy()
            rows = [dict(r, target_state=self._player_view(r["target"]["id"])) for r in reversed(self.mod["reports"]) if not status or r["status"] == status]
            return {"reports": rows[:500], "open": sum(1 for r in self.mod["reports"] if r["status"] == "open"), "players": len(self.players),
                    "banned": len(self.mod["bans"]), "muted": len(self.mod["mutes"]), "filter": self.mod["filter"], "log": self.mod["log"][-100:][::-1]}

    def admin_players(self, query: str = "") -> dict:
        q = str(query or "").strip().lower()
        with self.lock:
            hits = [pid for pid, p in self.players.items() if not q or q in p.get("name", "").lower() or q.replace("-", "") in p.get("code", "").replace("-", "").lower() or q == pid]
            hits.sort(key=lambda pid: -(self.players[pid].get("seen") or 0))
            return {"players": [self._player_view(pid) for pid in hits[:200]]}

    def admin_act(self, action: str, player: str = "", report: str = "", length: str = "", reason: str = "") -> dict:
        """dismiss | resolve (a report) | timeout | untimeout | ban | unban (a player, or the player a report is about)."""
        with self.lock:
            rep = next((r for r in self.mod["reports"] if r["id"] == report), None) if report else None
            pid = str(player or (rep["target"]["id"] if rep else ""))
            reason = clean_text(reason, 200)
            if action in ("dismiss", "resolve"):
                if rep is None:
                    raise SocialError("unknown report")
                rep["status"] = "dismissed" if action == "dismiss" else "resolved"
            elif action in ("timeout", "untimeout", "ban", "unban"):
                if pid not in self.players and not (action == "unban" and pid in self.mod["bans"]):
                    raise SocialError("unknown player")
                if action == "timeout":
                    if length not in TIMEOUTS:
                        raise SocialError("pick a length: " + ", ".join(TIMEOUTS))
                    self.mod["mutes"][pid] = {"until": self.clock() + TIMEOUTS[length], "reason": reason, "length": length}
                elif action == "untimeout":
                    self.mod["mutes"].pop(pid, None)
                elif action == "ban":
                    self.mod["bans"][pid] = {"at": self.clock(), "reason": reason}
                    self.mod["mutes"].pop(pid, None)
                    for o in self.players.values():                  # a banned player disappears from everyone's lists
                        for key in ("friends", "requests_in", "requests_out"):
                            if pid in o.get(key, []):
                                o[key].remove(pid)
                        o["invites"] = [i for i in o.get("invites", []) if i.get("from") != pid]
                    p = self.players.get(pid)
                    if p:                                            # and their own lists go too, so an unban starts afresh
                        for key in ("friends", "requests_in", "requests_out"):
                            p[key] = []
                        p["invites"], p["room"], p["status"] = [], None, ""
                else:
                    self.mod["bans"].pop(pid, None)
                if rep is not None and rep["status"] == "open":
                    rep["status"] = "resolved"
            else:
                raise SocialError("unknown action")
            self.mod["log"].append({"at": self.clock(), "action": action, "player": pid, "name": self.players.get(pid, {}).get("name", ""),
                                    "report": report or "", "length": length or "", "reason": reason})
            del self.mod["log"][:-1000]
            self._changed(urgent=True)
            return {"ok": True, "player": self._player_view(pid) if pid else None}

    def admin_filter(self, on=None, words=None) -> dict:
        with self.lock:
            if on is not None:
                self.mod["filter"]["on"] = bool(on)
            if words is not None:
                self.mod["filter"]["words"] = textfilter.clean_words(words)
            self._changed(urgent=True)
            return {"filter": self.mod["filter"], "base": sorted(textfilter.BASE_WORDS)}

    def goodbye(self, pid, secret) -> dict:
        """The player wants out: everything about them goes."""
        with self.lock:
            self._auth(pid, secret)
            self._forget(pid)
            self._changed(urgent=True)
            return {"ok": True}
