"""Local web server for the UI. Loopback only, token-protected, JSON POST API."""
from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .app import AppError, LauncherApp

UI_FILE = Path(__file__).parent / "ui" / "index.html"
MAX_BODY = 64 * 1024


def make_handler(app: LauncherApp, token: str, port_getter):
    api_lock = threading.RLock()   # one API call at a time: the app state is not thread-safe by itself

    class Handler(BaseHTTPRequestHandler):
        server_version = "LegacyPlayerUI"

        def log_message(self, *args):  # keep the console quiet
            pass

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            port = port_getter()
            return host in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if self.path in {"/", "/index.html"}:
                page = UI_FILE.read_text(encoding="utf-8").replace("__LP_TOKEN__", token)
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if not self.path.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            if not secrets.compare_digest(self.headers.get("X-LP-Token", ""), token):
                return self._json(403, {"error": "missing or wrong token"})
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return self._json(415, {"error": "JSON required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY:
                return self._json(413, {"error": "bad request size"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._json(400, {"error": "invalid JSON"})
            name = self.path[len("/api/"):]
            method = getattr(app, f"api_{name}", None) if name.replace("_", "").isalnum() else None
            if method is None:
                return self._json(404, {"error": "unknown action"})
            try:
                with api_lock:
                    return self._json(200, method(body))
            except AppError as exc:
                return self._json(400, {"error": str(exc)})
            except Exception as exc:  # never leak a traceback to the page
                return self._json(500, {"error": f"Something went wrong: {type(exc).__name__}"})

    return Handler


def serve(app: LauncherApp, port: int = 8780, open_browser: bool = True, opener=None,
          exit_when_closed: bool = False, port_fallback: bool = False) -> None:
    """Run the UI server. `opener(url)` may open a window itself; with `exit_when_closed` the
    server stops once the page stops sending its heartbeat (window closed)."""
    token = secrets.token_urlsafe(24)
    class _Server(ThreadingHTTPServer):
        request_queue_size = 64   # the page fires several requests at once; never drop one
        daemon_threads = True
    try:
        httpd = _Server(("127.0.0.1", port), None)
    except OSError:
        if not port_fallback:
            raise
        httpd = _Server(("127.0.0.1", 0), None)
    httpd.RequestHandlerClass = make_handler(app, token, lambda: httpd.server_address[1])
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"Legacy Player is open at {url}  (press Ctrl+C to quit)", flush=True)
    if exit_when_closed:
        started = time.time()

        def watch() -> None:
            while True:
                time.sleep(1.0)
                if app.should_exit(time.time(), started=started):
                    httpd.shutdown()
                    return
        threading.Thread(target=watch, daemon=True).start()
    if opener is not None:
        opener(url)
    elif open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        app.shutdown()
