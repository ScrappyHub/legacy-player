"""Legacy Player in the Windows notification area (the system tray).

Closing the window can leave the app running here so a server you started keeps being managed,
and right-clicking the icon shows what is going on right now (rebuilt every time you open it):
open the app, start or stop your server, copy a fresh server or room code, or exit.
Windows only, no extra packages. Anywhere else it simply reports itself as unavailable."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path


class NativeTray:
    """A tiny Shell_NotifyIcon wrapper. `menu()` returns [(command, label, enabled)] or None for a separator."""

    WM_TRAY = 0x0401
    ID_BASE = 1000

    def __init__(self, tooltip: str, menu, on_command) -> None:
        self.tooltip, self.menu, self.on_command = tooltip, menu, on_command
        self.ready = threading.Event()
        self.ok = False
        self.hwnd = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if sys.platform != "win32":
            return False
        self._thread = threading.Thread(target=self._run, daemon=True, name="tray")
        self._thread.start()
        self.ready.wait(4.0)
        return self.ok

    # --- Windows plumbing ---------------------------------------------------------------------------------
    def _run(self) -> None:
        try:
            self._loop()
        except Exception as exc:  # the tray is a nicety; never take the app down with it
            print(f"tray stopped: {exc}", flush=True)
        finally:
            self.ok = False
            self.ready.set()

    def _loop(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32, shell32, kernel32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
        LRESULT, WPARAM, LPARAM = ctypes.c_ssize_t, ctypes.c_size_t, ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

        class NOTIFYICONDATA(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                        ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                        ("uTimeout", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                        ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON)]

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                           wintypes.HINSTANCE, wintypes.LPVOID]
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
        user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATA)]
        shell32.ExtractIconW.restype = wintypes.HICON
        shell32.ExtractIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT]
        user32.LoadIconW.restype = wintypes.HICON
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]

        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = LRESULT
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
        user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
        NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 1, 2, 4, 0x10
        WM_DESTROY, WM_CLOSE, WM_NULL = 0x0002, 0x0010, 0x0000
        WM_RBUTTONUP, WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_CONTEXTMENU = 0x0205, 0x0202, 0x0203, 0x007B
        MF_STRING, MF_GRAYED, MF_SEPARATOR, MF_DEFAULT = 0, 1, 0x800, 0x1000
        TPM_RETURNCMD, TPM_RIGHTBUTTON, TPM_BOTTOMALIGN = 0x100, 0x2, 0x20
        taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

        # the same Martin icon as the window and the program file: load it from the bundled .ico at the tray's size
        icon = None
        ico = Path(__file__).parent / "ui" / "legacy-player.ico"
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        if ico.is_file():
            size = user32.GetSystemMetrics(49) or 16          # SM_CXSMICON
            icon = user32.LoadImageW(None, str(ico), 1, size, size, 0x10)     # IMAGE_ICON, LR_LOADFROMFILE
        if not icon and getattr(sys, "frozen", False):
            icon = shell32.ExtractIconW(None, sys.executable, 0)
            if icon in (None, 0, 1):
                icon = None
        if not icon:
            icon = user32.LoadIconW(None, ctypes.cast(ctypes.c_void_p(32512), wintypes.LPCWSTR))   # last resort: IDI_APPLICATION

        def data() -> NOTIFYICONDATA:
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd, nid.uID = self.hwnd, 1
            return nid

        def add_icon() -> bool:
            nid = data()
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage, nid.hIcon, nid.szTip = self.WM_TRAY, icon, self.tooltip[:127]
            return bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))

        def popup() -> None:
            items = self.menu()
            hmenu = user32.CreatePopupMenu()
            lookup = {}
            for n, item in enumerate(items):
                if item is None:
                    user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
                    continue
                command, label, enabled = item[0], item[1], item[2]
                bold = len(item) > 3 and item[3]
                lookup[self.ID_BASE + n] = command
                user32.AppendMenuW(hmenu, MF_STRING | (0 if enabled else MF_GRAYED) | (MF_DEFAULT if bold else 0), self.ID_BASE + n, label)
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            # Windows only gives the menu mouse tracking (hover highlight, closing on an outside click) when our window
            # is really the foreground one, and it refuses that to a background program unless we borrow the current
            # foreground window's input for a moment.
            fg = user32.GetForegroundWindow()
            fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
            me = kernel32.GetCurrentThreadId()
            attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True))
            user32.SetForegroundWindow(self.hwnd)
            chosen = user32.TrackPopupMenu(hmenu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_BOTTOMALIGN, pt.x, pt.y, 0, self.hwnd, None)
            if attached:
                user32.AttachThreadInput(me, fg_thread, False)
            user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
            user32.DestroyMenu(hmenu)
            if chosen in lookup:
                self._dispatch(lookup[chosen])

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                if msg == self.WM_TRAY:
                    if lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                        popup()
                    elif lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                        self._dispatch("open")
                    return 0
                if msg == taskbar_created:
                    add_icon()
                    return 0
                if msg == WM_CLOSE:
                    nid = data()
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                    user32.DestroyWindow(hwnd)
                    return 0
                if msg == WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
            except Exception as exc:
                print(f"tray error: {exc}", flush=True)
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        proc = WNDPROC(wndproc)
        hinst = kernel32.GetModuleHandleW(None)
        cls = WNDCLASS()
        cls.lpfnWndProc, cls.hInstance, cls.lpszClassName = proc, hinst, "LegacyPlayerTray"
        user32.RegisterClassW(ctypes.byref(cls))
        self.hwnd = user32.CreateWindowExW(0, "LegacyPlayerTray", "Legacy Player", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd or not add_icon():
            return
        self._notify = lambda title, text: self._balloon(shell32, ctypes, data, NIM_MODIFY, NIF_INFO, NOTIFYICONDATA, title, text)
        self._close = lambda: user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        self.ok = True
        self.ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    @staticmethod
    def _balloon(shell32, ctypes, data, nim_modify, nif_info, _cls, title: str, text: str) -> None:
        nid = data()
        nid.uFlags = nif_info
        nid.szInfoTitle, nid.szInfo, nid.dwInfoFlags = title[:63], text[:255], 1     # NIIF_INFO
        shell32.Shell_NotifyIconW(nim_modify, ctypes.byref(nid))

    def _dispatch(self, command: str) -> None:
        threading.Thread(target=self.on_command, args=(command,), daemon=True).start()   # never block the message pump

    def notify(self, title: str, text: str) -> None:
        fn = getattr(self, "_notify", None)
        if fn:
            try:
                fn(title, text)
            except Exception:
                pass

    def stop(self) -> None:
        fn = getattr(self, "_close", None)
        if fn:
            try:
                fn()
            except Exception:
                pass


class TrayController:
    """What the tray shows and does. The menu is built from a small picture of the server that a background thread keeps
    fresh, so right-clicking never waits on the network."""

    REFRESH_SECONDS = 4.0

    def __init__(self, app, open_window) -> None:
        self.app, self.open_window = app, open_window
        self.native = NativeTray("Legacy Player", self.menu, self.command)
        self._state = {"running": False, "players": 0, "live": 0, "open_rooms": 0, "cert": False, "known": False}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        ok = self.native.start()
        if ok:
            self.refresh()                      # the first look happens before anyone can right-click
            self._thread = threading.Thread(target=self._watch, daemon=True, name="tray-state")
            self._thread.start()
        return ok

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self.native.stop()

    # --- the picture of the server ------------------------------------------------------------------------
    def refresh(self) -> dict:
        """Ask the server once (slow if it is busy, so never call this from the menu) and remember the answer."""
        state = {"running": False, "players": 0, "live": 0, "open_rooms": 0, "known": True,
                 "cert": (self.app.data_dir / "server" / "tls" / "cert.pem").exists()}
        try:
            from server import cli
            info = cli._admin_call(self.app.data_dir / "server", "admin_status", timeout=2.0)
            state.update(running=True, players=int(info.get("players_in_live_sessions", 0)),
                         live=int(info.get("sessions_live", 0)), open_rooms=int(info.get("open_rooms", 0)))
        except Exception:
            pass
        self._state = state
        return state

    def _watch(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.REFRESH_SECONDS)
            self._wake.clear()
            if self._stop.is_set():
                return
            try:
                self.refresh()
            except Exception:
                pass

    def poke(self) -> None:
        """Look again soon (after a click, or because the menu was just opened)."""
        self._wake.set()

    def server_running(self) -> bool:
        return bool(self._state["running"])

    @staticmethod
    def _plural(n: int, one: str, many: str | None = None) -> str:
        return f"{n} {one if n == 1 else (many or one + 's')}"

    def menu(self):
        app = self.app
        st = self._state
        room = app.room
        self.poke()                                    # so the next right-click is fresher still
        if st["running"]:
            line = "Server running  ·  " + self._plural(st["players"], "player") + "  ·  " + self._plural(st["live"], "room")
        else:
            line = "Server stopped" if st["known"] else "Checking the server..."
        items = [("open", "Open Legacy Player", True, True), ("overlay", "Open the in-game overlay", True), None, ("open", line, True)]
        if room:
            who = room.get("game", "a game")
            items.append(("open", f"In a room: {who}" + (" (you are hosting)" if room.get("role") == "host" else ""), True))
        if st["running"]:
            items += [("server_stop", "Stop server", True), ("server_restart", "Restart server", True),
                      ("server_code", "Copy server code", st["cert"]),
                      ("server_fresh_code", "Make a fresh server code and copy it", st["cert"])]
        else:
            items += [("server_start", "Start server (this computer only)", True),
                      ("server_share", "Start server (let friends connect)", True)]
        if room and room.get("invite_code"):
            items.append(("room_code", "Copy this room's invite code", True))
        items += [None, ("exit", "Exit Legacy Player", True)]
        return items

    def command(self, command: str) -> None:
        app = self.app
        try:
            if command == "open":
                self.open_window()
            elif command == "overlay":
                app.api_overlay_open({})
            elif command in ("server_start", "server_share", "server_stop", "server_restart"):
                action = {"server_start": "start", "server_share": "start", "server_stop": "stop", "server_restart": "restart"}[command]
                share = command == "server_share" or (command == "server_restart" and app.catalog.settings().get("server_tls"))
                out = app.api_server_control({"action": action, "share": bool(share)})
                self.native.notify("Your server", {"start": "Server started.", "stop": "Server stopped.", "restart": "Server restarted."}[action]
                                   + (" Friends can connect." if share and action != "stop" else ""))
            elif command in ("server_code", "server_fresh_code"):
                got = app.api_server_code({"refresh": command == "server_fresh_code"})
                if got.get("code"):
                    self._copy(got["code"])
                    self.native.notify("Server code copied", ("Fresh code made: the old one no longer lets new people in. Players already connected stay connected. " if got.get("rotated") else "") + "Paste it to a friend. They enter it under Servers.")
                else:
                    self.native.notify("No server code", got.get("error") or "Start the server with 'let friends connect' first.")
            elif command == "room_code":
                code = (app.room or {}).get("invite_code")
                if code:
                    self._copy(code)
                    self.native.notify("Invite code copied", "Send it to a friend to let them into your room.")
            elif command == "exit":
                self._exit()
        except Exception as exc:
            self.native.notify("Legacy Player", f"That did not work: {exc}"[:200])
        finally:
            if command.startswith("server_"):
                self.refresh()                # show the new state in the menu straight away

    def _copy(self, text: str) -> None:
        subprocess.run(["clip"], input=text.encode("ascii", "ignore"), check=False,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=5)

    def _exit(self) -> None:
        import ctypes
        stop_server = False
        if self.refresh()["running"]:
            # MB_YESNOCANCEL | MB_ICONQUESTION | MB_TOPMOST
            answer = ctypes.windll.user32.MessageBoxW(
                None, "Your server is running for friends.\n\nYes: stop the server and exit\nNo: exit but leave the server running\nCancel: stay open",
                "Exit Legacy Player", 0x3 | 0x20 | 0x40000)
            if answer == 2:
                return
            stop_server = answer == 6
        if stop_server:
            try:
                self.app.api_server_control({"action": "stop"})
            except Exception:
                pass
        self.app.api_quit({})
