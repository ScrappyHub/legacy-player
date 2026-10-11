"""Local web server for the UI. Loopback only, token-protected, JSON POST API."""
from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import winplace
from .app import AppError, LauncherApp

UI_FILE = Path(__file__).parent / "ui" / "index.html"
MAX_BODY = 1024 * 1024    # room for a shrunk cover picture (the page sends it as base64)


def _same(a: str, b: str) -> bool:
    """Constant-time comparison that also copes with non-ASCII text (compare_digest raises on it)."""
    return secrets.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))


QUIT_FAREWELL_SECONDS = 3.0               # how long the window keeps answering so it can say goodbye (less if it is already gone)
ANSWER_GRACE_SECONDS = 0.5                # after the last answer went out: time for it to reach the page before the server stops
CLEANUP_LIMIT_SECONDS = 8.0               # closing down may take this long; after that the process ends regardless
WAKE_WAIT_SECONDS = 10.0                  # a second launch waits this long for a quitting instance to be gone
WINDOW_TITLE_MARK = winplace.APP_TITLE_MARK      # finds the app window by its title (see winplace.is_app_title; never the overlay)


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


class InFlight:
    """How many API answers are still being worked on or written, so the server is never stopped under one."""

    def __init__(self) -> None:
        self._n = 0
        self._lock = threading.Lock()

    def __enter__(self):
        with self._lock:
            self._n += 1
        return self

    def __exit__(self, *exc):
        with self._lock:
            self._n -= 1
        return False

    def count(self) -> int:
        with self._lock:
            return self._n

    def wait_idle(self, timeout: float) -> bool:
        end = time.time() + timeout
        while self.count() > 0:
            if time.time() >= end:
                return False
            time.sleep(0.05)
        return True


def _bad_request_message(exc: Exception) -> str:
    """A short, plain answer for a request the endpoint could not use (wrong kind of value, missing field, file trouble)."""
    if isinstance(exc, KeyError):
        return f"Something the request needs was missing ({str(exc)[:60]})."
    if isinstance(exc, OSError):
        return f"Could not use a file or connection: {exc.strerror or exc}"[:200]
    return f"Some of what was sent was not the right kind of value ({type(exc).__name__})."


def make_handler(app: LauncherApp, token: str, port_getter, launch: Launch | None = None):
    api_lock = getattr(app, "api_lock", None) or threading.RLock()   # one API call at a time: the app state is not thread-safe by itself
    inflight = InFlight()

    class Handler(BaseHTTPRequestHandler):
        server_version = "LegacyPlayerUI"
        busy = inflight                                 # serve() waits for this before it stops the server

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
            try:
                self.wfile.flush()
            except OSError:
                pass

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
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
                if not _same(parse_qs(u.query).get("t", [""])[0], token):
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
            with inflight:
                self._post()

        def _post(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if self.path == "/__wake" and launch is not None:
                if not _same(self.headers.get("X-LP-Wake", ""), launch.wake_secret) or launch.on_wake is None:
                    return self._json(403, {"error": "no"})
                if getattr(app, "quit_requested", False):
                    return self._json(409, {"error": "Legacy Player is closing."})     # the new launch waits, then starts itself
                show = True
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if 0 < length <= 1024:
                        wanted = json.loads(self.rfile.read(length) or b"{}")
                        show = not (isinstance(wanted, dict) and wanted.get("show") is False)
                except (ValueError, OSError):
                    pass
                if show:
                    threading.Thread(target=launch.on_wake, daemon=True).start()
                return self._json(200, {"ok": True})
            if not self.path.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            if not _same(self.headers.get("X-LP-Token", ""), token):
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
            except (TypeError, ValueError, KeyError, OSError) as exc:     # a badly typed request is the page's mistake, not a crash
                if reports is not None:
                    reports.crumb(name, 400)
                return self._json(400, {"error": _bad_request_message(exc)})
            except Exception as exc:  # never leak a traceback to the page
                if reports is not None:
                    reports.crumb(name, 500)
                    reports.capture("internal-error", exc, context={"api": name})
                return self._json(500, {"error": f"Something went wrong: {type(exc).__name__}"})

    return Handler


class _Server(ThreadingHTTPServer):
    request_queue_size = 64   # the page fires several requests at once; never drop one
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second program bind a port that is already listening (requests would be split
    # between the two). There the port is taken exclusively instead; elsewhere SO_REUSEADDR only skips TIME_WAIT.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if sys.platform == "win32" and exclusive is not None:
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            except OSError:
                pass
        super().server_bind()


def make_server(port: int, port_fallback: bool) -> _Server:
    """The UI server on 127.0.0.1:port; on another free port when that one is taken and port_fallback is on."""
    try:
        return _Server(("127.0.0.1", port), None)
    except OSError:
        if not port_fallback:
            raise
        return _Server(("127.0.0.1", 0), None)


def _write_instance(path: Path, port: int, wake: str) -> None:
    """Written whole or not at all, so a second launch never reads half a file."""
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"port": port, "wake": wake, "pid": os.getpid()}), encoding="utf-8")
    os.replace(tmp, path)


def _remove_instance_if_ours(path: Path, wake: str) -> None:
    """Remove instance.json only if it still describes this process (a newer instance may have written its own)."""
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(info, dict) and _same(str(info.get("wake", "")), wake):
            path.unlink()
    except (OSError, ValueError):
        pass


def arm_exit_watchdog(seconds: float = CLEANUP_LIMIT_SECONDS) -> threading.Event:
    """End the process after `seconds` unless the returned event is set first. Closing down must never hang: a stuck
    thread would otherwise keep an invisible Legacy Player alive, holding the port and the data folder."""
    done = threading.Event()

    def run() -> None:
        if not done.wait(seconds):
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass
            os._exit(0)
    threading.Thread(target=run, daemon=True, name="exit-watchdog").start()
    return done


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
    httpd = make_server(port, port_fallback)
    launch = Launch()
    httpd.RequestHandlerClass = make_handler(app, token, lambda: httpd.server_address[1], launch)
    busy: InFlight = httpd.RequestHandlerClass.busy
    api_lock = getattr(app, "api_lock", None)
    base = f"http://127.0.0.1:{httpd.server_address[1]}/"
    url_for_window = lambda: base + "?k=" + launch.new_secret()      # every window gets its own one-time address
    if opener is None and not open_browser and not getattr(sys, "frozen", False):
        # --no-browser from source: nobody else will open a window, so this console line is the only way in (one use)
        print(f"Legacy Player is open at {url_for_window()}  (press Ctrl+C to quit)", flush=True)
    else:
        # the address without its one-time secret: in the app this line ends up in app.log, and the secret would open it
        print(f"Legacy Player is running at {base}  (press Ctrl+C to quit; start Legacy Player again to open another window)", flush=True)
    instance_file = Path(app.data_dir) / "instance.json"
    tray = None

    def close_app_windows() -> None:
        try:
            winplace.close_titled(WINDOW_TITLE_MARK)
        except Exception:
            pass

    def winplace_window_open() -> bool:
        """Is an app window on screen at all? (Off Windows there is no way to tell, so assume yes.)"""
        try:
            return sys.platform != "win32" or winplace.window_exists(WINDOW_TITLE_MARK)
        except Exception:
            return True

    def show_existing() -> bool:
        """The app window is already on screen (maybe minimised or behind others): bring it forward instead of opening another."""
        try:
            return winplace.focus_titled(WINDOW_TITLE_MARK)
        except Exception:
            return False

    def stop_after_last_answer() -> None:
        """Quit or a restart was asked for: let that call finish and its answer reach the page, then stop the server.
        (The app sets quit_requested only after its own closing work, as the last thing before answering.)"""
        if api_lock is not None and api_lock.acquire(timeout=30):     # the quit/restart call (and any other) has finished
            api_lock.release()
        busy.wait_idle(5.0)                                            # its answer has been written
        time.sleep(ANSWER_GRACE_SECONDS)                               # and has had a moment to travel
        httpd.shutdown()

    if exit_when_closed and opener is not None and sys.platform == "win32":
        from .tray import TrayController

        reopen_lock = threading.Lock()
        reopened = [0.0]

        def reopen() -> None:
            with reopen_lock:                                                    # a double-click is two clicks: one window only
                if time.time() - reopened[0] < 2.0:
                    return
                if not app.tray_mode and show_existing():                        # already open: bring that one forward
                    reopened[0] = time.time()
                    return
                reopened[0] = time.time()
                app.last_ping, app.bye_at, app.tray_mode = time.time(), 0.0, False   # fresh grace while the window loads
                opener(url_for_window())
        tray = TrayController(app, reopen)
        if not tray.start():
            tray = None
        from .overlay import Listeners
        from .shell import make_overlay_opener
        browser_overlay = make_overlay_opener(app.data_dir)
        app.overlay_opener = lambda: browser_overlay(url_for_window() + "&overlay=1")   # returns False when no browser can open it
        from . import overlay_window
        if overlay_window.available():                 # the real overlay panel (frameless, always on top); the browser window is the fallback
            from . import overlay as overlaymod
            app.overlay_native = overlay_window.NativeOverlay(app._overlay_view, app._overlay_actions(), monitor=app._overlay_monitor,
                                                              pad=overlaymod.read_pads)
        app.overlay_listeners = Listeners(lambda: app.api_overlay_open({}))
        app.overlay_listeners.start(app._overlay_prefs())
    if exit_when_closed:
        started = time.time()

        def watch() -> None:
            while True:
                time.sleep(1.0)
                now = time.time()
                if app.quit_requested:
                    # let the open window see "quitting" and wave goodbye, then close it ourselves and stop. When the window
                    # is already gone (tray, or it said bye) there is nobody to wait for: stop once the answer is out.
                    gone = app.tray_mode or bool(app.bye_at) or not winplace_window_open()
                    if not gone and now - getattr(app, "quit_at", 0.0) < QUIT_FAREWELL_SECONDS:
                        continue
                    if api_lock is not None and api_lock.acquire(timeout=30):
                        api_lock.release()
                    busy.wait_idle(5.0)
                    close_app_windows()
                    time.sleep(ANSWER_GRACE_SECONDS)
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
        threading.Thread(target=watch, daemon=True, name="window-watch").start()
    else:
        def watch_quit() -> None:
            """Without a window of its own (python -m launcher in a browser tab), Quit and a restart for an update still
            have to stop this process: give the page a moment to say goodbye, then stop."""
            while not app.quit_requested:
                time.sleep(0.5)
            time.sleep(QUIT_FAREWELL_SECONDS)
            stop_after_last_answer()
        threading.Thread(target=watch_quit, daemon=True, name="quit-watch").start()

    def show_window() -> None:
        if not app.tray_mode and show_existing():
            return
        app.last_ping, app.bye_at, app.tray_mode = time.time(), 0.0, False
        (opener or webbrowser.open)(url_for_window())
    launch.on_wake = show_window
    app.show_main_window = show_window
    try:                                    # a second launch finds this one through this file and asks it to show its window
        _write_instance(instance_file, httpd.server_address[1], launch.wake_secret)
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
        _remove_instance_if_ours(instance_file, launch.wake_secret)
        try:
            app.catalog.save()                                 # settings first: the watchdog below may end the process
        except Exception:
            pass
        done = arm_exit_watchdog(CLEANUP_LIMIT_SECONDS) if (app.quit_requested or exit_when_closed) else None
        for step in (lambda: tray.stop() if tray is not None else None,
                     lambda: app.overlay_listeners.stop() if app.overlay_listeners is not None else None,
                     lambda: app.overlay_native.stop() if app.overlay_native is not None else None,
                     httpd.server_close,
                     app.shutdown):
            try:
                step()
            except Exception:
                pass
        if done is not None:
            done.set()


# --- one Legacy Player per data folder ---------------------------------------------------------------------------

class InstanceLock:
    """An exclusive lock on data_dir/instance.lock, held for as long as this process runs (the system lets go of it
    when the process ends, even after a crash). Two processes never run on one data folder."""

    def __init__(self, fd: int | None, path: Path) -> None:
        self.fd, self.path = fd, path

    def release(self) -> None:
        if self.fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None


_HELD: list[InstanceLock] = []          # keeps the lock (and its file handle) alive for the life of the process


def acquire_instance_lock(data_dir: Path) -> InstanceLock | None:
    """Take the data folder's lock. None when another process holds it. When locking is not possible at all (an odd
    file system), carry on without it rather than refuse to start."""
    path = Path(data_dir) / "instance.lock"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return InstanceLock(None, path)
    try:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, PermissionError):
        os.close(fd)
        return None
    except OSError as exc:
        import errno
        os.close(fd)
        if exc.errno in (errno.EACCES, errno.EAGAIN, getattr(errno, "EDEADLOCK", -1), getattr(errno, "EDEADLK", -1)):
            return None
        return InstanceLock(None, path)
    lock = InstanceLock(fd, path)
    _HELD.append(lock)
    return lock


def wake_existing(data_dir: Path, show: bool = True, wait: float = WAKE_WAIT_SECONDS) -> bool:
    """If Legacy Player is already running for this data folder, ask it to show its window and return True.

    False when there is none (a leftover instance.json is removed), and also when the running one is just closing
    (it answers 409): then this waits up to `wait` seconds for it to be gone, so the new launch can start normally.
    Never raises."""
    import http.client
    path = Path(data_dir) / "instance.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        info = json.loads(raw)
        port, wake = int(info["port"]), str(info["wake"])
        if not 0 < port < 65536:
            raise ValueError("port")
    except Exception:
        _remove_if_unchanged(path, raw)                         # unreadable: nobody can be woken through it
        return False
    status = 0
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            conn.request("POST", "/__wake", body=json.dumps({"show": bool(show)}).encode(),
                         headers={"X-LP-Wake": wake, "Content-Type": "application/json"})
            response = conn.getresponse()
            status = response.status
            response.read()
        finally:
            conn.close()
    except (ConnectionRefusedError, http.client.HTTPException):
        _remove_if_unchanged(path, raw)                         # nothing (or something else) listens there: a leftover file
        return False
    except Exception:
        return False                                            # busy or slow: leave the file alone
    if status == 200:
        return True
    if status == 409:                                          # it is closing: wait for it to be gone, then start afresh
        end = time.time() + max(0.0, wait)
        while time.time() < end:
            try:
                if path.read_text(encoding="utf-8") != raw:
                    break
            except OSError:
                break
            time.sleep(0.2)
    return False


def _remove_if_unchanged(path: Path, raw: str) -> None:
    try:
        if path.read_text(encoding="utf-8") == raw:
            path.unlink()
    except OSError:
        pass
