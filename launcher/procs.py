"""Small process helpers that need no extra packages: is a process still running, when did it start (so a reused
process number is never mistaken for the game), and which processes did it start. Windows uses the system API;
elsewhere it falls back to what the platform offers. Never raises."""
from __future__ import annotations

import os
import sys


def start_time(pid: int) -> int | None:
    """A number that is different for every process that ever had this id (Windows creation time), or None if unknown."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            k.OpenProcess.restype = wintypes.HANDLE
            h = k.OpenProcess(0x1000, False, int(pid))          # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return None
            try:
                c, e, kt, ut = (wintypes.FILETIME() for _ in range(4))
                if not k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut)):
                    return None
                return (c.dwHighDateTime << 32) | c.dwLowDateTime
            finally:
                k.CloseHandle(h)
        except Exception:
            return None
    try:
        with open(f"/proc/{int(pid)}/stat", "rb") as f:
            return int(f.read().rsplit(b")", 1)[1].split()[19])
    except Exception:
        return None


def is_alive(pid: int, started: int | None = None) -> bool:
    """True only if that process is running and (when `started` is given) is the same one that started then."""
    try:
        pid = int(pid)
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            k.OpenProcess.restype = wintypes.HANDLE
            h = k.OpenProcess(0x1000, False, pid)
            if not h:
                return False
            try:
                code = wintypes.DWORD()
                if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:     # STILL_ACTIVE
                    return False
            finally:
                k.CloseHandle(h)
        else:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                pass
            try:                                              # a zombie that nobody collected is not running
                with open(f"/proc/{pid}/stat", "rb") as f:
                    if f.read().rsplit(b")", 1)[1].split()[0] == b"Z":
                        return False
            except OSError:
                pass
        return started is None or start_time(pid) in (None, started)
    except Exception:
        return False


def children(pid: int) -> set[int]:
    """The process and everything it started (Windows: a snapshot of the process table)."""
    found = {int(pid)}
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class ENTRY(ctypes.Structure):
                _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                            ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                            ("szExeFile", ctypes.c_wchar * 260)]
            k = ctypes.windll.kernel32
            k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
            snap = k.CreateToolhelp32Snapshot(0x2, 0)                 # TH32CS_SNAPPROCESS
            pairs = []
            try:
                e = ENTRY()
                e.dwSize = ctypes.sizeof(ENTRY)
                ok = k.Process32FirstW(snap, ctypes.byref(e))
                while ok:
                    pairs.append((e.th32ProcessID, e.th32ParentProcessID))
                    ok = k.Process32NextW(snap, ctypes.byref(e))
            finally:
                k.CloseHandle(snap)
            grew = True
            while grew:
                grew = False
                for child, parent in pairs:
                    if parent in found and child not in found:
                        found.add(child)
                        grew = True
        except Exception:
            pass
        return found
    try:
        for name in os.listdir("/proc"):
            if name.isdigit():
                with open(f"/proc/{name}/stat", "rb") as f:
                    ppid = int(f.read().rsplit(b")", 1)[1].split()[1])
                if ppid in found:
                    found.add(int(name))
    except Exception:
        pass
    return found
