"""HTTP front of the friends service:   python -m server.social --dir social --port 8791

One endpoint, JSON in and out:  POST /  {"op": "...", "id": "...", "secret": "...", ...}  ->  {"ok": true, ...} or {"ok": false,
"error": "..."}.  GET /health answers "ok". Put HTTPS in front of it (a reverse proxy or a tunnel); the app only talks to
https:// addresses, or 127.0.0.1 for testing. No request log is kept: who talked to whom is deliberately not recorded."""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import SocialError, SocialService

MAX_BODY = 16 * 1024
OPS = {"hello", "heartbeat", "request", "decide", "remove", "invite", "dismiss_invite", "message", "thread", "goodbye"}


def dispatch(service: SocialService, body: dict) -> dict:
    op = str(body.get("op") or "")
    if op not in OPS:
        raise SocialError("unknown operation")
    pid, secret = body.get("id"), body.get("secret")
    if op == "hello":
        return service.hello(body.get("name"))
    if op == "heartbeat":
        return service.heartbeat(pid, secret, body.get("name"), body.get("status", ""), body.get("room"))
    if op == "request":
        return service.request(pid, secret, body.get("code"))
    if op == "decide":
        return service.decide(pid, secret, body.get("from"), bool(body.get("accept")))
    if op == "remove":
        return service.remove(pid, secret, body.get("friend"))
    if op == "invite":
        return service.invite(pid, secret, body.get("to"), body.get("invite_code"), body.get("game"), body.get("server_code", ""))
    if op == "dismiss_invite":
        return service.dismiss_invite(pid, secret, body.get("from"))
    if op == "message":
        return service.message(pid, secret, body.get("to"), body.get("text"))
    if op == "thread":
        return service.thread(pid, secret, body.get("friend"))
    return service.goodbye(pid, secret)


def make_handler(service: SocialService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LegacyPlayerFriends"
        timeout = 10

        def log_message(self, *args) -> None:
            pass

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/health"):
                return self._json(200, {"ok": True, "service": "legacy-player-friends"})
            self._json(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                return self._json(413, {"ok": False, "error": "bad request size"})
            try:
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._json(400, {"ok": False, "error": "invalid JSON"})
            try:
                out = dispatch(service, body)
            except SocialError as exc:
                return self._json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:                       # never a traceback to a stranger
                return self._json(500, {"ok": False, "error": f"something went wrong ({type(exc).__name__})"})
            self._json(200, {"ok": True, **out})
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default=os.environ.get("LP_SOCIAL_DIR") or "social")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    args = parser.parse_args()
    service = SocialService(Path(args.dir))
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(service))

    def tidy() -> None:
        while True:
            time.sleep(600)
            with service.lock:
                service._tidy()
                service.save()
    threading.Thread(target=tidy, daemon=True).start()
    print(f"Friends service on http://{args.host}:{args.port}/ keeping its players in {args.dir}  (put HTTPS in front of it)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
