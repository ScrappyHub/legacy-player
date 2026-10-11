"""The app's life: one instance per data folder, waking it, quitting with the answer delivered, closing down for sure."""
import http.client
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from launcher import childenv, web, winplace
from launcher.app import AppError, LauncherApp


def post(port, path, body=None, headers=None, timeout=10):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("POST", path, body=json.dumps(body or {}).encode(),
                     headers={"Content-Type": "application/json", **(headers or {})})
        r = conn.getresponse()
        return r.status, json.loads(r.read() or b"{}")
    finally:
        conn.close()


class Quiet(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"LEGACY_PLAYER_NO_BACKGROUND": "1"})
        p.start()
        self.addCleanup(p.stop)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))


class WakeTests(Quiet):
    def setUp(self):
        super().setUp()
        self.app = LauncherApp(self.tmp / "data")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        self.port = self.httpd.server_address[1]
        self.launch = web.Launch()
        self.woke = threading.Event()
        self.launch.on_wake = self.woke.set
        self.httpd.RequestHandlerClass = web.make_handler(self.app, "tok", lambda: self.port, self.launch)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.instance = self.app.data_dir / "instance.json"

    def record(self, port=None, wake=None):
        self.instance.write_text(json.dumps({"port": port or self.port, "wake": wake or self.launch.wake_secret}), encoding="utf-8")

    def test_a_closing_app_answers_409_and_the_new_launch_starts_itself(self):
        self.app.quit_requested = True
        status, _ = post(self.port, "/__wake", headers={"X-LP-Wake": self.launch.wake_secret})
        self.assertEqual(409, status)
        self.record()

        def gone_soon():
            time.sleep(0.4)
            self.instance.unlink()                       # what the closing app does at the very end
        threading.Thread(target=gone_soon).start()
        started = time.time()
        self.assertFalse(web.wake_existing(self.app.data_dir, wait=5))
        self.assertLess(time.time() - started, 4)        # it waited for the file to go, not the whole time
        self.assertFalse(self.woke.is_set())

    def test_waking_without_showing(self):
        self.record()
        self.assertTrue(web.wake_existing(self.app.data_dir, show=False))
        time.sleep(0.2)
        self.assertFalse(self.woke.is_set())
        self.assertTrue(web.wake_existing(self.app.data_dir))
        self.assertTrue(self.woke.wait(2))

    def test_a_leftover_file_pointing_at_nothing_is_removed(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        dead = s.getsockname()[1]
        s.close()
        self.record(port=dead)
        self.assertFalse(web.wake_existing(self.app.data_dir))
        self.assertFalse(self.instance.exists())

    def test_a_port_that_does_not_speak_http_never_crashes_the_start(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        self.addCleanup(srv.close)

        def garbage():
            c, _ = srv.accept()
            c.recv(1024)
            c.sendall(b"\x00\x01 not http at all\r\n\r\n")
            c.close()
        threading.Thread(target=garbage, daemon=True).start()
        self.record(port=srv.getsockname()[1])
        self.assertFalse(web.wake_existing(self.app.data_dir))         # was http.client.BadStatusLine
        self.assertFalse(self.instance.exists())

    def test_a_damaged_file_is_removed(self):
        self.instance.write_text("{not json", encoding="utf-8")
        self.assertFalse(web.wake_existing(self.app.data_dir))
        self.assertFalse(self.instance.exists())
        self.instance.write_text(json.dumps({"port": "x"}), encoding="utf-8")
        self.assertFalse(web.wake_existing(self.app.data_dir))

    def test_a_wrong_secret_is_refused_but_the_file_stays(self):
        self.record(wake="wrong")
        self.assertFalse(web.wake_existing(self.app.data_dir))
        self.assertTrue(self.instance.exists())


class InstanceLockTests(Quiet):
    def test_only_one_process_per_data_folder(self):
        first = web.acquire_instance_lock(self.tmp)
        self.assertIsNotNone(first)
        self.addCleanup(first.release)
        self.assertIsNone(web.acquire_instance_lock(self.tmp))
        first.release()
        again = web.acquire_instance_lock(self.tmp)
        self.assertIsNotNone(again)
        again.release()

    def test_a_second_launch_wakes_the_first_or_gives_up(self):
        from launcher.__main__ import claim_data_folder
        held = web.acquire_instance_lock(self.tmp)
        self.addCleanup(held.release)
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            lock, code = claim_data_folder(self.tmp, show=True, wait=0.3)      # nobody answers
        self.assertIsNone(lock)
        self.assertEqual(1, code)
        with mock.patch("launcher.__main__.wake_existing", return_value=True), redirect_stdout(io.StringIO()):
            self.assertEqual((None, 0), claim_data_folder(self.tmp, show=True, wait=0.3))
        held.release()
        (self.tmp / "instance.json").write_text("{}", encoding="utf-8")
        lock, code = claim_data_folder(self.tmp, show=True, wait=0.3)
        self.assertIsNotNone(lock)
        self.assertFalse((self.tmp / "instance.json").exists())                # a leftover from a crash
        lock.release()


class PortTests(unittest.TestCase):
    def test_a_taken_port_falls_back_to_a_free_one(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        self.addCleanup(busy.close)
        port = busy.getsockname()[1]
        with self.assertRaises(OSError):
            web.make_server(port, port_fallback=False)
        srv = web.make_server(port, port_fallback=True)
        self.addCleanup(srv.server_close)
        self.assertNotEqual(port, srv.server_address[1])

    def test_windows_never_shares_the_port(self):
        self.assertEqual(sys.platform != "win32", web._Server.allow_reuse_address)
        calls = []

        class FakeSock:
            def setsockopt(self, *a):
                calls.append(a)

        srv = web._Server.__new__(web._Server)
        srv.socket = FakeSock()
        with mock.patch.object(web.sys, "platform", "win32"), mock.patch.object(web.socket, "SO_EXCLUSIVEADDRUSE", -5, create=True), \
             mock.patch.object(web.ThreadingHTTPServer, "server_bind", lambda self: None):
            srv.server_bind()
        self.assertIn((socket.SOL_SOCKET, -5, 1), calls)


class FakeApp:
    UNLOCKED = frozenset()

    def __init__(self):
        self.api_lock = threading.RLock()
        self.reports = mock.Mock()
        self.quit_requested = False

    def api_typed(self, body):
        return {"n": int(body["n"]) + 1}

    def api_file(self, body):
        raise FileNotFoundError(2, "No such file or directory")

    def api_boom(self, body):
        raise RuntimeError("bug")

    def api_said(self, body):
        raise AppError("Plain words.")


class BadRequestTests(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        self.port = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = web.make_handler(self.app, "tok", lambda: self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def call(self, name, body):
        return post(self.port, "/api/" + name, body, {"X-LP-Token": "tok"})

    def test_badly_typed_requests_are_400_not_crashes(self):
        self.assertEqual((200, {"n": 2}), self.call("typed", {"n": 1}))
        for body in ({"n": "abc"}, {"n": [1]}, {}):                       # ValueError, TypeError, KeyError
            status, out = self.call("typed", body)
            self.assertEqual(400, status, body)
            self.assertTrue(out["error"])
        self.assertEqual(400, self.call("file", {})[0])
        self.assertEqual((400, {"error": "Plain words."}), self.call("said", {}))
        self.app.reports.capture.assert_not_called()
        self.assertEqual(500, self.call("boom", {})[0])                   # a real bug is still a 500 and a report
        self.app.reports.capture.assert_called_once()


class QuitTests(Quiet):
    """Quit: the answer reaches the page before the server stops, and serve() ends."""

    def test_the_quit_answer_is_delivered_before_the_server_stops(self):
        app = LauncherApp(self.tmp / "data")
        real_shutdown = app.shutdown

        def slow_shutdown():
            time.sleep(1.0)                              # leaving a room over the network takes a moment
            real_shutdown()
        app.shutdown = slow_shutdown
        out = io.StringIO()
        ended = {}
        opened = []

        def run():
            with redirect_stdout(out):
                web.serve(app, 0, opener=opened.append, port_fallback=True)       # a window opener: no secret in the log
            ended["at"] = time.time()
        with mock.patch.object(web.secrets, "token_urlsafe", return_value="tok"), \
             mock.patch.object(web, "QUIT_FAREWELL_SECONDS", 0.1), \
             mock.patch("launcher.reports.install_hooks", lambda center: None):
            t = threading.Thread(target=run, daemon=True)
            t.start()
            instance = app.data_dir / "instance.json"
            for _ in range(100):
                if instance.exists():
                    break
                time.sleep(0.05)
            port = json.loads(instance.read_text(encoding="utf-8"))["port"]
            status, body = post(port, "/api/quit", {}, {"X-LP-Token": "tok"})
            answered = time.time()
            self.assertEqual((200, {"ok": True}), (status, body))
            t.join(10)
        self.assertFalse(t.is_alive())
        self.assertGreaterEqual(ended["at"], answered)
        self.assertTrue(app.quit_requested)
        self.assertFalse(instance.exists())                                  # it was ours, so it went
        self.assertNotIn("?k=", out.getvalue())                              # no one-time secret in the log
        self.assertIn(f"http://127.0.0.1:{port}/", out.getvalue())
        self.assertEqual(1, len(opened))
        self.assertIn("?k=", opened[0])                                      # the window got its secret directly

    def test_shutdown_runs_once_and_never_raises(self):
        app = LauncherApp(self.tmp / "data")
        tunnel = mock.Mock()
        tunnel.stop.side_effect = lambda: time.sleep(0.2)
        app.tunnel = tunnel
        app.room = {"session_id": "s"}
        app.api_mp_leave = mock.Mock(side_effect=RuntimeError("network gone"))
        threads = [threading.Thread(target=app.shutdown) for _ in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(5)
        tunnel.stop.assert_called_once()
        app.api_mp_leave.assert_called_once()
        app.shutdown()                                                        # later calls do nothing
        tunnel.stop.assert_called_once()

    def test_quit_says_quitting_only_after_closing(self):
        app = LauncherApp(self.tmp / "data")
        seen = []
        app.shutdown = lambda: seen.append(app.quit_requested)
        app.api_quit({})
        self.assertEqual([False], seen)
        self.assertTrue(app.quit_requested)
        self.assertGreater(app.quit_at, 0)

    def test_the_exit_watchdog_can_be_called_off(self):
        with mock.patch.object(web.os, "_exit") as hard_exit:
            done = web.arm_exit_watchdog(0.2)
            done.set()
            time.sleep(0.4)
            hard_exit.assert_not_called()
            web.arm_exit_watchdog(0.1)
            time.sleep(0.4)
            hard_exit.assert_called_once_with(0)


class AppStatusTests(Quiet):
    def test_ping_tells_about_a_settings_file_that_could_not_be_read(self):
        app = LauncherApp(self.tmp / "data")
        self.assertEqual("", app.api_ping({})["settings_problem"])
        app.catalog.read_only = "Could not read your settings file."
        self.assertEqual("Could not read your settings file.", app.api_ping({})["settings_problem"])

    def test_one_game_is_one_game(self):
        app = LauncherApp(self.tmp / "data")
        app.games = {"g1": {"id": "g1", "console": "n64", "title": "Mario Kart 64", "path": str(self.tmp / "mk.z64")}}
        with mock.patch.object(app, "_emulators", return_value={}):
            texts = [i["text"] for i in app.api_doctor({})["issues"]]
        self.assertTrue(any(t.startswith("1 Nintendo 64 game still needs an emulator") for t in texts), texts)

    def test_a_router_without_upnp_is_not_reported_as_a_crash(self):
        app = LauncherApp(self.tmp / "data")
        app.catalog.set_setting("server_use_fallback", False)
        app.reports.capture = mock.Mock()
        with mock.patch("launcher.app.portmap.open_port", return_value={"state": "failed", "message": "No UPnP here."}), \
             mock.patch.object(app, "_close_router_mapping"):
            out = app._manage_router("start", 0, True, 41234)
        self.assertEqual("failed", out["state"])
        app.reports.capture.assert_not_called()


class WindowTitleTests(unittest.TestCase):
    def test_the_app_window_is_found_by_its_title(self):
        for title in ("Legacy Player", "Legacy Player — Home", "Legacy Player — restarting", "Legacy Player — closed",
                      "Legacy Player – Home", "Legacy Player - Google Chrome", "Legacy Player — Home - Microsoft​ Edge"):
            self.assertTrue(winplace.is_app_title(title), title)
        for title in ("Legacy Player overlay", "Legacy Players", "My Legacy Player", "", "Legacy Player: notes.txt - Notepad"):
            self.assertFalse(winplace.is_app_title(title), title)

    def test_titled_uses_it_and_only_browser_windows(self):
        wins = [{"hwnd": 1, "title": "Legacy Player"}, {"hwnd": 2, "title": "Legacy Player overlay"},
                {"hwnd": 3, "title": "Legacy Player — Home"}, {"hwnd": 4, "title": "Legacy Player — notes"}]
        classes = {1: "Chrome_WidgetWin_1", 2: "Chrome_WidgetWin_1", 3: "Chrome_WidgetWin_1", 4: "Notepad"}
        with mock.patch.object(winplace.sys, "platform", "win32"), mock.patch.object(winplace, "_windows_of", return_value=wins), \
             mock.patch.object(winplace, "_class_of", side_effect=lambda h: classes[h]):
            self.assertEqual([1, 3], [w["hwnd"] for w in winplace._titled(winplace.APP_TITLE_MARK)])
            self.assertEqual([2], [w["hwnd"] for w in winplace._titled("Legacy Player overlay")])
            self.assertTrue(winplace.window_exists(winplace.APP_TITLE_MARK))
        self.assertEqual(winplace.APP_TITLE_MARK, web.WINDOW_TITLE_MARK)

    def test_a_whole_browser_window_is_never_closed(self):
        self.assertTrue(winplace.is_browser_tab_title("Legacy Player — Home - Google Chrome"))
        self.assertTrue(winplace.is_browser_tab_title("Legacy Player — Home and 2 more pages - Personal - Microsoft​ Edge"))
        self.assertFalse(winplace.is_browser_tab_title("Legacy Player — Home"))


class ChildEnvTests(Quiet):
    def test_onefile_state_is_not_handed_on(self):
        env = childenv.clean_env({"PATH": "p", "_PYI_APPLICATION_HOME_DIR": "a", "_PYI_PARENT_PROCESS_LEVEL": "1", "_MEIPASS2": "m"})
        self.assertEqual({"PATH": "p", "PYINSTALLER_RESET_ENVIRONMENT": "1"}, env)

    def test_the_working_folder_is_never_the_temporary_one(self):
        with mock.patch.object(childenv.sys, "frozen", True, create=True), \
             mock.patch.object(childenv.sys, "executable", str(self.tmp / "app" / "LegacyPlayer.exe")):
            self.assertEqual(str(self.tmp / "data"), childenv.child_cwd(self.tmp / "data"))
            self.assertEqual(str((self.tmp / "app").resolve()), childenv.child_cwd())
        self.assertEqual(str(childenv.SOURCE_ROOT), childenv.child_cwd(self.tmp))       # from source: the checkout

    def test_the_friends_service_starts_clean(self):
        from launcher import socialhost
        host = socialhost.SocialHost(self.tmp / "data")
        proc = mock.Mock()
        proc.poll.return_value = 1
        with mock.patch.object(host, "running", return_value=False), \
             mock.patch("server.selfsigned.ensure_certificate"), \
             mock.patch("server.social.__main__.moderator_key"), \
             mock.patch.object(socialhost.subprocess, "Popen", return_value=proc) as popen, \
             mock.patch.dict(os.environ, {"_PYI_APPLICATION_HOME_DIR": "x"}):
            with self.assertRaises(socialhost.HostError):
                host.start(40999, wait=0.3)
        kwargs = popen.call_args.kwargs
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", kwargs["env"])
        self.assertEqual("1", kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"])
        self.assertEqual(childenv.child_cwd(self.tmp / "data"), kwargs["cwd"])


if __name__ == "__main__":
    unittest.main()
