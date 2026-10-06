"""Open Legacy Player in its own app-style window (no address bar or tabs) using the Edge or
Chrome already on the computer, so the downloadable app feels like a normal program.
The window is just a viewer: closing it ends the app (the page sends a heartbeat)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path


def find_app_browser() -> str | None:
    candidates: list[str] = []
    if sys.platform == "win32":
        for var in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
            base = os.environ.get(var)
            if base:
                candidates += [
                    str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
                    str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"),
                ]
    elif sys.platform == "darwin":
        candidates += ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                       "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for exe in candidates:
        if Path(exe).is_file():
            return exe
    for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def app_window_command(browser: str, url: str, profile_dir: Path) -> list[str]:
    return [browser, f"--app={url}", f"--user-data-dir={profile_dir}", "--no-first-run",
            "--no-default-browser-check", "--window-size=1280,860"]


def make_opener(data_dir: Path):
    def opener(url: str) -> None:
        browser = find_app_browser()
        if browser:
            try:
                subprocess.Popen(app_window_command(browser, url, Path(data_dir) / "window_profile"),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except OSError:
                pass
        webbrowser.open(url)  # still works; the page's heartbeat ends the app when the tab closes
    return opener
