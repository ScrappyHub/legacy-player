"""One button: bring everything Legacy Player installed or connected up to date, then say what is still needed.

Steps, in order (each one reports done / nothing to do / problem, and one failure never stops the rest):
  1 Legacy Player itself      asks GitHub for the newest release (installing it is a separate, confirmed button)
  2 Engines                   re-fetches the emulators Legacy Player installed, from their official GitHub releases
  3 Tailscale                 only if you already have it: Windows' package manager (winget) upgrades it
  4 Your games                reads the games folders again, finds Steam and Epic games, makes the save folders
  5 Checkup                   compiles the list of what is still missing, plus what is already fine
Downloads happen only after the player turned on "Allow internet downloads" and pressed the button.
"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from . import engines as engine_catalog
from . import firewall, privatelink
from .installer import InstallError, latest_release
from .version import REPO, VERSION

STEPS = [("app", "Legacy Player"), ("engines", "Emulators and engines"), ("tailscale", "Tailscale"),
         ("games", "Your games"), ("checkup", "Checkup")]


def _nums(text: str) -> tuple:
    import re
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


class UpdateAll:
    def __init__(self, app) -> None:
        self.app = app
        self.lock = threading.Lock()
        self.state = self._fresh()

    @staticmethod
    def _fresh() -> dict:
        return {"state": "idle", "steps": [{"id": i, "title": t, "state": "waiting", "detail": ""} for i, t in STEPS],
                "report": None, "started_at": None, "finished_at": None}

    def snapshot(self) -> dict:
        with self.lock:
            return {**self.state, "steps": [dict(s) for s in self.state["steps"]]}

    def _step(self, sid: str, state: str, detail: str = "") -> None:
        with self.lock:
            for s in self.state["steps"]:
                if s["id"] == sid:
                    s["state"], s["detail"] = state, detail

    def start(self) -> dict:
        with self.lock:
            if self.state["state"] == "running":
                return self.snapshot()
            self.state = self._fresh()
            self.state.update(state="running", started_at=time.time())
        threading.Thread(target=self._run, daemon=True, name="update-all").start()
        return self.snapshot()

    def _run(self) -> None:
        newer = None
        for sid, fn in (("app", self._app), ("engines", self._engines), ("tailscale", self._tailscale), ("games", self._games)):
            self._step(sid, "running")
            try:
                result = fn()
                if sid == "app":
                    newer = result[2]
                self._step(sid, *result[:2])
            except Exception as exc:                       # one failing step never stops the others
                self._step(sid, "problem", f"{type(exc).__name__}: {exc}"[:200])
        self._step("checkup", "running")
        try:
            report = self.compile(newer)
            self._step("checkup", "done", f"{len(report['needs'])} thing{'s' if len(report['needs']) != 1 else ''} still to do")
        except Exception as exc:
            report = {"needs": [], "ready": [], "text": ""}
            self._step("checkup", "problem", str(exc)[:200])
        with self.lock:
            self.state.update(state="done", report=report, finished_at=time.time())

    # --- the steps -------------------------------------------------------------------------------------------
    def _app(self):
        try:
            rel = latest_release(REPO)
        except InstallError as exc:
            return "problem", f"Could not check: {exc}", None
        if _nums(rel["tag"]) > _nums(VERSION):
            return "done", f"Version {rel['tag']} is available (you have {VERSION}).", rel["tag"]
        return "done", f"You have the latest version ({VERSION}).", None

    def _ours(self) -> list[str]:
        """Engines Legacy Player installed itself (they live under its own folder), so it may update them."""
        root = Path(self.app.installer.install_root).resolve()
        found = self.app._emulators()
        out = []
        for eid, spec in engine_catalog.ENGINES.items():
            path = (found.get(eid) or {}).get("path")
            if not path or spec["source"]["kind"] != "github" or eid in engine_catalog.NOT_REDISTRIBUTABLE:
                continue
            try:
                Path(path).resolve().relative_to(root)
            except (ValueError, OSError):
                continue
            out.append(eid)
        return out

    def _engines(self):
        ids = self._ours()
        if not ids:
            return "skipped", "Nothing here was installed by Legacy Player, so there is nothing to refresh."
        job = self.app.installer.start_many(ids, consent=True, run_inline=True)
        self.app._forget_emulators()
        names = ", ".join(engine_catalog.ENGINES[i]["name"] for i in ids)
        if job["state"] == "error":
            return "problem", (job.get("error") or "Some downloads failed.")[:200]
        return "done", f"Updated {names}."

    def _tailscale(self):
        if not privatelink.find_tailscale():
            return "skipped", "Not installed (it is optional)."
        winget = privatelink.winget_path()
        if not winget:
            return "skipped", "Tailscale is installed; Windows' package manager is not available to update it."
        out = subprocess.run([winget, "upgrade", "--id", "Tailscale.Tailscale", "--silent", "--accept-source-agreements",
                              "--accept-package-agreements"], capture_output=True, text=True, timeout=600,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        text = (out.stdout or "") + (out.stderr or "")
        if "No applicable update" in text or "No installed package" in text or "no newer" in text.lower():
            return "done", "Already up to date."
        return ("done", "Updated.") if out.returncode == 0 else ("problem", "winget could not update it. Try Tailscale's own updater.")

    def _games(self):
        out = self.app.api_scan_everything({})
        games = (out.get("rescan") or {}).get("games")
        return "done", (f"{games} games found." if games is not None else "Games folders read again.")

    # --- what is still needed ----------------------------------------------------------------------------------
    def compile(self, newer: str | None) -> dict:
        app = self.app
        needs: list[dict] = []
        ready: list[str] = []
        if newer:
            needs.append({"text": f"Install Legacy Player {newer}.", "action": "app_update", "label": "Update Legacy Player"})
        else:
            ready.append(f"Legacy Player {VERSION} is current.")
        doc = app.api_doctor({})
        for issue in doc.get("issues", []):
            if issue.get("dismissed"):
                continue
            action = {"emulator": "engines", "core": "setup", "bios": "setup"}.get(issue.get("kind"), "setup")
            needs.append({"text": issue["text"], "action": action, "label": {"engines": "Open Engines"}.get(action, "Open the Doctor")})
        s = app.catalog.settings()
        games = len(getattr(app, "games", {}) or {})
        if games:
            ready.append(f"{games} games in your library.")
        else:
            needs.append({"text": "No games yet. Point Legacy Player at your games folder.", "action": "library", "label": "Open Library"})
        running = app.api_server_activity({}).get("online")
        ready.append("Your server is running." if running else "Your server is off (start it in Servers when you want to host).")
        fw = firewall.status(s["server_port"])
        if fw.get("supported") and not fw.get("allowed"):
            needs.append({"text": "Windows Firewall has no rule for your server, so friends elsewhere may not reach it.",
                          "action": "servers", "label": "Open Servers"})
        elif fw.get("supported"):
            ready.append("Windows Firewall lets friends reach your server.")
        if s["server_host"] in ("127.0.0.1", "localhost", "::1") and not s.get("server_public_address") and not s.get("allow_direct_connections"):
            needs.append({"text": "To play with a friend: share your server code (Servers > Start server for friends), "
                                  "or paste theirs. 'How friends reach me' shows which routes work here.", "action": "servers",
                          "label": "Open Servers"})
        lines = ["Legacy Player checkup", ""]
        lines += ["Ready:"] + [f"  - {r}" for r in ready]
        lines += ["", "Still to do:" if needs else "Nothing else is needed."] + [f"  {i}. {n['text']}" for i, n in enumerate(needs, 1)]
        return {"needs": needs, "ready": ready, "text": "\n".join(lines)}
