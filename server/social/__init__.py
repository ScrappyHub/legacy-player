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
import threading
import time
from pathlib import Path

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"            # no 0/O or 1/I: codes are read out loud
FORGET_AFTER = 60 * 86400
ONLINE_WINDOW = 75.0                                       # a heartbeat every 30 s keeps a player online
MESSAGE_KEEP = 7 * 86400
MESSAGES_PER_PAIR = 200
MAX_FRIENDS = 200
MAX_NAME = 24
MAX_TEXT = 500
PER_MINUTE = 120                                           # calls per player per minute


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
        self._load()

    # --- storage --------------------------------------------------------------------------------------------------
    def _load(self) -> None:
        if self.folder is None:
            return
        try:
            data = json.loads((self.folder / "players.json").read_text(encoding="utf-8"))
            self.players = data.get("players") or {}
            self.codes = {p["code"]: pid for pid, p in self.players.items()}
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        if self.folder is None:
            return
        with self.lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            tmp = self.folder / "players.tmp"
            tmp.write_text(json.dumps({"players": self.players}), encoding="utf-8")
            os.replace(tmp, self.folder / "players.json")

    # --- helpers ------------------------------------------------------------------------------------------------
    def _tidy(self) -> None:
        now = self.clock()
        for pid in [p for p, v in self.players.items() if now - v.get("seen", 0) > FORGET_AFTER]:
            self._forget(pid)
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
            for key in ("friends", "requests_in", "requests_out"):
                if pid in other.get(key, []):
                    other[key].remove(pid)
            other.get("messages", {}).pop(pid, None)

    def _auth(self, pid: str, secret: str) -> dict:
        p = self.players.get(str(pid or ""))
        if p is None or not hmac.compare_digest(str(secret or ""), p["secret"]):
            raise SocialError("This app is not known to the friends service any more. Say hello again under Settings > Friends.")
        now = self.clock()
        window, count = p.get("minute") or [0, 0]
        if int(now // 60) != window:
            window, count = int(now // 60), 0
        if count >= PER_MINUTE:
            raise SocialError("Too many requests in a minute; wait a moment.")
        p["minute"] = [window, count + 1]
        p["seen"] = now
        return p

    def _online(self, p: dict) -> bool:
        return self.clock() - p.get("seen", 0) < ONLINE_WINDOW

    def _view(self, me: dict, other_id: str) -> dict:
        o = self.players.get(other_id) or {}
        room = o.get("room") if self._online(o) and o.get("room") else None
        return {"id": other_id, "name": o.get("name", "?"), "online": self._online(o), "status": o.get("status", "") if self._online(o) else "",
                "room": room, "unread": sum(1 for m in me.get("messages", {}).get(other_id, []) if not m.get("read") and m["from"] == other_id)}

    def _inbox(self, pid: str) -> dict:
        p = self.players[pid]
        friends = [self._view(p, f) for f in p.get("friends", [])]
        friends.sort(key=lambda f: (not f["online"], f["name"].lower()))
        return {"me": {"id": pid, "name": p["name"], "code": p["code"], "status": p.get("status", ""), "room": p.get("room")},
                "friends": friends,
                "requests": [{"id": r, "name": self.players.get(r, {}).get("name", "?")} for r in p.get("requests_in", []) if r in self.players],
                "sent": [{"id": r, "name": self.players.get(r, {}).get("name", "?")} for r in p.get("requests_out", []) if r in self.players],
                "invites": list(p.get("invites", [])),
                "online": sum(1 for f in friends if f["online"])}

    # --- operations ---------------------------------------------------------------------------------------------
    def hello(self, name) -> dict:
        """A new identity: id, secret (kept only by that app) and a friend code."""
        with self.lock:
            self._tidy()
            pid = secrets.token_hex(8)
            code = make_code()
            while code in self.codes:
                code = make_code()
            self.players[pid] = {"name": clean_name(name), "secret": secrets.token_urlsafe(24), "code": code, "friends": [], "requests_in": [],
                                 "requests_out": [], "seen": self.clock(), "status": "", "room": None, "invites": [], "messages": {}}
            self.codes[code] = pid
            self.save()
            return {"id": pid, "secret": self.players[pid]["secret"], "code": code, "name": self.players[pid]["name"]}

    def heartbeat(self, pid, secret, name=None, status="", room=None) -> dict:
        """The app says it is open (every 30 s), what the player is doing, and the room to share, then gets its inbox."""
        with self.lock:
            p = self._auth(pid, secret)
            if name is not None:
                p["name"] = clean_name(name)
            p["status"] = clean_text(status, 60)
            if isinstance(room, dict) and room.get("invite_code"):
                p["room"] = {"invite_code": clean_text(room.get("invite_code"), 14), "game": clean_text(room.get("game"), 80),
                             "server_code": clean_text(room.get("server_code"), 60), "players": int(room.get("players") or 0),
                             "max_players": int(room.get("max_players") or 0), "at": self.clock()}
            else:
                p["room"] = None
            self._tidy()
            return self._inbox(pid)

    def request(self, pid, secret, code) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            code = re.sub(r"[^A-Z0-9]", "", str(code or "").upper())
            code = code[:3] + "-" + code[3:7] if len(code) >= 7 else code
            other_id = self.codes.get(code)
            if other_id is None or other_id not in self.players:
                raise SocialError("No player has that friend code. Check it with your friend (it looks like MK7-4Q2X).")
            if other_id == pid:
                raise SocialError("That is your own code.")
            other = self.players[other_id]
            if other_id in p["friends"]:
                return {"ok": True, "already": True, **self._inbox(pid)}
            if len(p["friends"]) >= MAX_FRIENDS:
                raise SocialError("Your friends list is full.")
            if pid in p["requests_in"] or other_id in p["requests_in"]:   # they asked first: this is a yes
                return self.decide(pid, secret, other_id, True)
            if other_id not in p["requests_out"]:
                p["requests_out"].append(other_id)
            if pid not in other["requests_in"]:
                other["requests_in"].append(pid)
            self.save()
            return {"ok": True, "already": False, **self._inbox(pid)}

    def decide(self, pid, secret, other_id, accept) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            other_id = str(other_id or "")
            other = self.players.get(other_id)
            if other_id in p["requests_in"]:
                p["requests_in"].remove(other_id)
            if other and pid in other.get("requests_out", []):
                other["requests_out"].remove(pid)
            if accept and other is not None:
                if other_id not in p["friends"]:
                    p["friends"].append(other_id)
                if pid not in other["friends"]:
                    other["friends"].append(pid)
            self.save()
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
            self.save()
            return {"ok": True, **self._inbox(pid)}

    def invite(self, pid, secret, to, invite_code, game, server_code="") -> dict:
        """Hand a friend the way into my room. Only friends can be invited, and only with a room invite code."""
        with self.lock:
            p = self._auth(pid, secret)
            to = str(to or "")
            if to not in p["friends"] or to not in self.players:
                raise SocialError("You can only invite someone on your friends list.")
            code = clean_text(invite_code, 14)
            if not code:
                raise SocialError("Host a room first; the invite carries its code.")
            inv = {"from": pid, "name": p["name"], "invite_code": code, "game": clean_text(game, 80), "server_code": clean_text(server_code, 60),
                   "at": self.clock()}
            box = self.players[to]["invites"]
            box[:] = [i for i in box if i["from"] != pid]
            box.append(inv)
            del box[:-20]
            self.save()
            return {"ok": True}

    def dismiss_invite(self, pid, secret, from_id) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            p["invites"] = [i for i in p.get("invites", []) if i["from"] != str(from_id or "")]
            self.save()
            return {"ok": True, **self._inbox(pid)}

    def message(self, pid, secret, to, text) -> dict:
        with self.lock:
            p = self._auth(pid, secret)
            to = str(to or "")
            if to not in p["friends"] or to not in self.players:
                raise SocialError("You can only message someone on your friends list.")
            text = clean_text(text)
            if not text:
                raise SocialError("Type something first.")
            m = {"from": pid, "to": to, "text": text, "at": self.clock()}
            for owner, other in ((pid, to), (to, pid)):
                box = self.players[owner].setdefault("messages", {}).setdefault(other, [])
                box.append(dict(m, read=(owner == pid)))
                del box[:-MESSAGES_PER_PAIR]
            self.save()
            return {"ok": True, "messages": self._thread(pid, to)}

    def _thread(self, pid: str, other: str) -> list[dict]:
        msgs = self.players[pid].get("messages", {}).get(other, [])
        for m in msgs:
            m["read"] = True
        return [{"from": m["from"], "text": m["text"], "at": m["at"], "mine": m["from"] == pid} for m in msgs]

    def thread(self, pid, secret, other) -> dict:
        with self.lock:
            self._auth(pid, secret)
            other = str(other or "")
            if other not in self.players:
                return {"messages": []}
            out = {"messages": self._thread(pid, other), "name": self.players[other]["name"]}
            self.save()
            return out

    def goodbye(self, pid, secret) -> dict:
        """The player wants out: everything about them goes."""
        with self.lock:
            self._auth(pid, secret)
            self._forget(pid)
            self.save()
            return {"ok": True}
