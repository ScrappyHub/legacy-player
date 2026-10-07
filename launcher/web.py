"""Local web server for the UI. Loopback only, token-protected, JSON POST API."""
from __future__ import annotations

import json
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .app import AppError, LauncherApp

UI_FILE = Path(__file__).parent / "ui" / "index.html"
MAX_BODY = 1024 * 1024    # room for a shrunk cover picture (the page sends it as base64)


QUIT_FAREWELL_SECONDS = 6.0               # how long the window keeps answering so it can say goodbye
WINDOW_TITLE_MARK = "Legacy Player \u2014"      # every app window's title starts like this (the overlay's does not)


class Launch:
    """Who may open the page. Each window gets a one-time secret in its address; the page then lives on a cookie
    only that window holds. A program that merely finds the port can no longer fetch the page (and its API token)."""

    def __init__(self) -> None:
        self.secrets: set[str] = set()
        self.sessions: set[str] = set()
        self.wake_secret = secrets.token_urlsafe(24)
        self.on_wake = None
        self._lock = threading.Lock()

    def new_secret(self) -> str:
        value = secrets.token_urlsafe(18)
        with self._lock:
            self.secrets = set(list(self.secrets)[-7:]) | {value}     # a few open windows at most
        return value

    def redeem(self, value: str) -> str | None:
        with self._lock:
            if value in self.secrets:
                self.secrets.discard(value)
                session = secrets.token_urlsafe(18)
                self.sessions.add(session)
                return session
        return None

    def valid_session(self, value: str) -> bool:
        with self._lock:
            return value in self.sessions


def make_handler(app: LauncherApp, token: str, port_getter, launch: Launch | None = None):
    api_lock = getattr(app, "api_lock", None) or threading.RLock()   # one API call at a time: the app state is not thread-safe by itself

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
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                extra = {}
                if launch is not None:
                    cookie_name = f"lp_{port_getter()}"
                    jar = {}
                    for part in (self.headers.get("Cookie") or "").split(";"):
                        if "=" in part:
                            k, v = part.strip().split("=", 1)
                            jar[k] = v
                    given = parse_qs(parsed.query).get("k", [""])[0]
                    if given:
                        session = launch.redeem(given)
                        if session is None:
                            return self._json(403, {"error": "That link was already used. Open Legacy Player from its window or tray icon."})
                        self.send_response(302)      # set the cookie, then drop the secret from the address
                        self.send_header("Set-Cookie", f"{cookie_name}={session}; Path=/; HttpOnly; SameSite=Strict")
                        self.send_header("Location", "/#overlay" if "overlay" in parse_qs(parsed.query) else "/")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if not launch.valid_session(jar.get(cookie_name, "")):
                        return self._json(403, {"error": "Open Legacy Player from its own window or its tray icon."})
                page = UI_FILE.read_text(encoding="utf-8").replace("__LP_TOKEN__", token)
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            if self.path.startswith("/cover/"):
                u = parsed
                if not secrets.compare_digest(parse_qs(u.query).get("t", [""])[0], token):
                    return self._json(403, {"error": "missing or wrong token"})
                found = app.cover_file(u.path[len("/cover/"):].removesuffix(".png"))
                if found is None:
                    return self._json(404, {"error": "no cover"})
                body = found[0].read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", found[1])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "private, max-age=86400")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
                return
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if self.path == "/__wake" and launch is not None:
                if not secrets.compare_digest(self.headers.get("X-LP-Wake", ""), launch.wake_secret) or launch.on_wake is None:
                    return self._json(403, {"error": "no"})
                threading.Thread(target=launch.on_wake, daemon=True).start()
                return self._json(200, {"ok": True})
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
            reports = getattr(app, "reports", None)
            try:
                if name in app.UNLOCKED:       # quick read-only calls and slow ones that touch no shared state
                    result = method(body)
                else:
                    with api_lock:
                        result = method(body)
                if reports is not None:
                    reports.crumb(name, 200)
                return self._json(200, result)
            except AppError as exc:
                if reports is not None:
                    reports.crumb(name, 400)
                return self._json(400, {"error": str(exc)})
            except Exception as exc:  # never leak a traceback to the page
                if reports is not None:
                    reports.crumb(name, 500)
                    reports.capture("internal-error", exc, context={"api": name})
                return self._json(500, {"error": f"Something went wrong: {type(exc).__name__}"})

    return Handler


def serve(app: LauncherApp, port: int = 8780, open_browser: bool = True, opener=None,
          exit_when_closed: bool = False, port_fallback: bool = False) -> None:
    """Run the UI server. `opener(url)` may open a window itself; with `exit_when_closed` the
    server stops once the page stops sending its heartbeat (window closed)."""
    token = secrets.token_urlsafe(24)
    try:
        from .reports import install_hooks
        install_hooks(app.reports)          # failures nobody caught also reach the (opt-in) reports
    except Exception:
        pass
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
    launch = Launch()
    httpd.RequestHandlerClass = make_handler(app, token, lambda: httpd.server_address[1], launch)
    base = f"http://127.0.0.1:{httpd.server_address[1]}/"
    url_for_window = lambda: base + "?k=" + launch.new_secret()      # every window gets its own one-time address
    print(f"Legacy Player is open at {url_for_window()}  (press Ctrl+C to quit)", flush=True)
    instance_file = Path(app.data_dir) / "instance.json"
    tray = None

    def close_app_windows() -> None:
        try:
            from . import winplace
            winplace.close_titled(WINDOW_TITLE_MARK)
        except Exception:
            pass

    def show_existing() -> bool:
        """The app window is already on screen (maybe minimised or behind others): bring it forward instead of opening another."""
        try:
            from . import winplace
            return winplace.focus_titled(WINDOW_TITLE_MARK)
        except Exception:
            return False
    if exit_when_closed and opener is not None and sys.platform == "win32":
        from .tray import TrayController

        def reopen() -> None:
            if not app.tray_mode and show_existing():                            # already open: bring that one forward
                return
            app.last_ping, app.bye_at, app.tray_mode = time.time(), 0.0, False   # fresh grace while the window loads
            opener(url_for_window())
        tray = TrayController(app, reopen)
        if not tray.start():
            tray = None
        from .overlay import Listeners
        from .shell import make_overlay_opener
        overlay_window = make_overlay_opener(app.data_dir)
        app.overlay_opener = lambda: overlay_window(url_for_window() + "&overlay=1")   # returns False when no browser can open it
        app.overlay_listeners = Listeners(lambda: app.api_overlay_open({}))
        app.overlay_listeners.start(app._overlay_prefs())
    if exit_when_closed:
        started = time.time()

        def watch() -> None:
            while True:
                time.sleep(1.0)
                now = time.time()
                if app.quit_requested:
                    # let the open window see "quitting" and wave goodbye, then close it ourselves and stop
                    if now - getattr(app, "quit_at", 0.0) < QUIT_FAREWELL_SECONDS:
                        continue
                    close_app_windows()
                    httpd.shutdown()
                    return
                if app.tray_mode or not app.window_closed(now, started=started):
                    continue
                running = tray is not None and tray.server_running()
                if tray is not None and (app.catalog.settings().get("close_to_tray", True) or running):
                    app.tray_mode = True
                    tray.native.notify("Legacy Player is still running",
                                       "Your server is still running. Right-click this icon to stop it, open the app or exit." if running
                                       else "It lives in the tray now. Right-click the icon to open it, run your server or exit.")
                else:
                    httpd.shutdown()
                    return
        threading.Thread(target=watch, daemon=True).start()
    def show_window() -> None:
        if not app.tray_mode and show_existing():
            return
        app.last_ping, app.bye_at, app.tray_mode = time.time(), 0.0, False
        (opener or webbrowser.open)(url_for_window())
    launch.on_wake = show_window
    if exit_when_closed:      # a second launch finds this one through this file and asks it to show its window
        try:
            instance_file.write_text(json.dumps({"port": httpd.server_address[1], "wake": launch.wake_secret}), encoding="utf-8")
        except OSError:
            pass
    if opener is not None:
        opener(url_for_window())
    elif open_browser:
        webbrowser.open(url_for_window())
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            instance_file.unlink()
        except OSError:
            pass
        if tray is not None:
            tray.stop()
        if app.overlay_listeners is not None:
            app.overlay_listeners.stop()
        httpd.server_close()
        app.shutdown()


def wake_existing(data_dir: Path) -> bool:
    """If Legacy Player is already running for this data folder, ask it to show its window and return True."""
    import http.client
    try:
        info = json.loads((Path(data_dir) / "instance.json").read_text(encoding="utf-8"))
        conn = http.client.HTTPConnection("127.0.0.1", int(info["port"]), timeout=3)
        conn.request("POST", "/__wake", body=b"{}", headers={"X-LP-Wake": str(info["wake"]), "Content-Type": "application/json"})
        ok = conn.getresponse().status == 200
        conn.close()
        return ok
    except (OSError, ValueError, KeyError, TypeError):
        return False
