"""Legacy Player's side of the friends service (server/social): one identity per app, kept in the catalog, and small
JSON calls over https. Everything here is optional: with no address set, the Friends page simply is not there."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .version import VERSION


class FriendsError(ValueError):
    pass


def address_ok(url: str) -> bool:
    url = str(url or "").strip()
    return bool(url) and (url.startswith("https://") or re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?(/|$)", url) is not None)


class FriendsClient:
    def __init__(self, catalog, opener=urllib.request.urlopen, timeout: float = 8.0) -> None:
        self.catalog, self.opener, self.timeout = catalog, opener, timeout

    # --- where and who ---------------------------------------------------------------------------------------
    def server(self) -> str:
        return str(self.catalog.settings().get("friends_server") or "").strip().rstrip("/")

    def enabled(self) -> bool:
        return address_ok(self.server())

    def identity(self) -> dict:
        me = self.catalog.data.get("friends") or {}
        return me if me.get("server") == self.server() and me.get("id") and me.get("secret") else {}

    def _call(self, body: dict) -> dict:
        url = self.server()
        if not address_ok(url):
            raise FriendsError("Set the friends service address under Settings > Friends first (it must start with https://).")
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url + "/", data=data, method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": f"LegacyPlayer/{VERSION}"})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                out = json.loads(response.read(256_000))
        except urllib.error.HTTPError as exc:
            try:
                out = json.loads(exc.read(64_000))
            except ValueError:
                out = {}
            raise FriendsError(out.get("error") or f"The friends service answered {exc.code}.") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise FriendsError(f"Could not reach the friends service ({getattr(exc, 'reason', exc)}).") from exc
        if not out.get("ok"):
            raise FriendsError(out.get("error") or "The friends service refused that.")
        return out

    def _auth(self) -> dict:
        me = self.identity()
        if not me:
            raise FriendsError("Say hello to the friends service first (the Friends page does it with one click).")
        return {"id": me["id"], "secret": me["secret"]}

    # --- operations -------------------------------------------------------------------------------------------
    def hello(self, name: str) -> dict:
        out = self._call({"op": "hello", "name": name})
        self.catalog.data["friends"] = {"server": self.server(), "id": out["id"], "secret": out["secret"], "code": out["code"]}
        self.catalog.save()
        return {"code": out["code"], "name": out["name"]}

    def heartbeat(self, name: str, status: str = "", room: dict | None = None) -> dict:
        return self._call({"op": "heartbeat", **self._auth(), "name": name, "status": status, "room": room})

    def request(self, code: str) -> dict:
        return self._call({"op": "request", **self._auth(), "code": code})

    def decide(self, other: str, accept: bool) -> dict:
        return self._call({"op": "decide", **self._auth(), "from": other, "accept": bool(accept)})

    def remove(self, other: str) -> dict:
        return self._call({"op": "remove", **self._auth(), "friend": other})

    def invite(self, to: str, invite_code: str, game: str, server_code: str = "") -> dict:
        return self._call({"op": "invite", **self._auth(), "to": to, "invite_code": invite_code, "game": game, "server_code": server_code})

    def dismiss_invite(self, other: str) -> dict:
        return self._call({"op": "dismiss_invite", **self._auth(), "from": other})

    def message(self, to: str, text: str) -> dict:
        return self._call({"op": "message", **self._auth(), "to": to, "text": text})

    def thread(self, other: str) -> dict:
        return self._call({"op": "thread", **self._auth(), "friend": other})

    def block(self, other: str) -> dict:
        return self._call({"op": "block", **self._auth(), "player": other})

    def unblock(self, other: str) -> dict:
        return self._call({"op": "unblock", **self._auth(), "player": other})

    def clear_thread(self, other: str) -> dict:
        return self._call({"op": "clear_thread", **self._auth(), "friend": other})

    def read_all(self) -> dict:
        return self._call({"op": "read_all", **self._auth()})

    def goodbye(self) -> dict:
        try:
            return self._call({"op": "goodbye", **self._auth()})
        finally:
            self.catalog.data["friends"] = {}
            self.catalog.save()
