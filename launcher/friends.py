"""Legacy Player's side of the friends service (server/social): one identity per app, kept in the catalog, and small
JSON calls over https. Everything here is optional: with no address set, the Friends page simply is not there.

A friends link may carry the service's certificate fingerprint:  https://203.0.113.5:8791/#pin=<sha256 hex>. Services run by
Legacy Player use a self-signed certificate, so instead of a certificate authority the app checks that fingerprint
(the same way server codes work). Links without a pin are checked the normal way."""
from __future__ import annotations

import hashlib
import http.client
import json
import re
import ssl
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

from .version import VERSION


class FriendsError(ValueError):
    pass


def split_link(link: str) -> tuple[str, str]:
    """('https://host:port', 'PIN') from a friends link; the pin is '' when the link has none."""
    base, _, frag = str(link or "").strip().partition("#")
    pin = re.sub(r"[^0-9a-fA-F]", "", (parse_qs(frag).get("pin") or [""])[0]).lower()
    return base.rstrip("/"), pin if len(pin) == 64 else ""


def make_link(host: str, port: int, pin: str) -> str:
    host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"https://{host}:{int(port)}/#pin={pin.lower()}"


def pinned_request(url: str, pin: str, body: bytes | None, headers: dict, timeout: float, method: str = "POST",
                   limit: int = 256_000) -> tuple[int, bytes]:
    """One HTTPS request that only goes ahead when the server's certificate has the expected SHA-256 fingerprint."""
    u = urlsplit(url)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE                    # the fingerprint below is the check
    conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=timeout, context=context)
    try:
        conn.connect()
        der = conn.sock.getpeercert(binary_form=True) or b""
        if hashlib.sha256(der).hexdigest() != pin:
            raise FriendsError("That friends service is not the one your link is for (its certificate changed). "
                               "Ask whoever runs it for the link again.")
        conn.request(method, (u.path or "/") + (f"?{u.query}" if u.query else ""), body=body, headers=headers)
        response = conn.getresponse()
        return response.status, response.read(limit)
    finally:
        conn.close()


def address_ok(url: str) -> bool:
    url = split_link(url)[0]
    return bool(url) and (url.startswith("https://") or re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?(/|$)", url) is not None)


class FriendsClient:
    def __init__(self, catalog, opener=urllib.request.urlopen, timeout: float = 8.0) -> None:
        self.catalog, self.opener, self.timeout = catalog, opener, timeout

    # --- where and who ---------------------------------------------------------------------------------------
    def link(self) -> str:
        return str(self.catalog.settings().get("friends_server") or "").strip()

    def server(self) -> str:
        return split_link(self.link())[0]

    def pin(self) -> str:
        return split_link(self.link())[1]

    def enabled(self) -> bool:
        return address_ok(self.server())

    def identity(self) -> dict:
        me = self.catalog.data.get("friends") or {}
        return me if me.get("server") == self.server() and me.get("id") and me.get("secret") else {}

    def _send(self, path: str, data: bytes | None, headers: dict, method: str = "POST") -> tuple[int, bytes]:
        url = self.server() + path
        headers = {"User-Agent": f"LegacyPlayer/{VERSION}", **headers}
        if self.pin():
            try:
                return pinned_request(url, self.pin(), data, headers, self.timeout, method)
            except FriendsError:
                raise
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                raise FriendsError(f"Could not reach the friends service ({exc}).") from exc
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return getattr(response, "status", 200), response.read(256_000)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(64_000)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise FriendsError(f"Could not reach the friends service ({getattr(exc, 'reason', exc)}).") from exc

    def _call(self, body: dict) -> dict:
        if not address_ok(self.server()):
            raise FriendsError("Set the friends service address under Settings > Friends first (it must start with https://).")
        status, raw = self._send("/", json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
        try:
            out = json.loads(raw)
        except ValueError:
            out = {}
        if status >= 400:
            raise FriendsError(out.get("error") or f"The friends service answered {status}.")
        if not out.get("ok"):
            raise FriendsError(out.get("error") or "The friends service refused that.")
        return out

    def admin(self, key: str, path: str, body: dict | None = None) -> dict:
        """The moderation side (needs the moderator key): GET when body is None, otherwise POST."""
        if not address_ok(self.server()):
            raise FriendsError("No friends service is set.")
        headers = {"X-Admin-Token": key}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, raw = self._send(path, data, headers, "GET" if body is None else "POST")
        try:
            out = json.loads(raw)
        except ValueError:
            out = {}
        if status == 401:
            raise FriendsError("That moderator key was not accepted by this friends service.")
        if status >= 400 or not out.get("ok"):
            raise FriendsError(out.get("error") or f"The friends service answered {status}.")
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

    def heartbeat(self, name: str, status: str = "", room: dict | None = None, requests_open: bool | None = None) -> dict:
        return self._call({"op": "heartbeat", **self._auth(), "name": name, "status": status, "room": room, "requests_open": requests_open})

    def report(self, player: str, category: str, details: str = "", message: str = "", block: bool = False) -> dict:
        return self._call({"op": "report", **self._auth(), "player": player, "category": category, "details": details,
                           "message": message, "block": bool(block)})

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
