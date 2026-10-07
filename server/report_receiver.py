"""Receives Legacy Player's opt-in problem reports and files them on disk so they can be read and fixed.

Run it somewhere reachable over HTTPS (put a reverse proxy or a tunnel such as Cloudflare Tunnel or Caddy in front; the
app only sends to https:// addresses):

    python -m server.report_receiver --dir reports --port 8790 --token SOMETHING-LONG

Then put that public address in launcher/version.py (REPORT_URL) before building, or tell testers to set it in
Settings > Privacy. Reports land in  <dir>/<date>/<fingerprint>/<id>.json  and a one-line summary is appended to
<dir>/index.jsonl. Read them with  python tools/read_reports.py <dir> .

It never records who sent a report: no address, no headers, no log of requests. It only accepts small JSON reports with
the expected shape, limits how many it takes, and answers 202. The optional --token is a shared secret the app does not
know; use it only to keep the endpoint from being filled by strangers when you also check it at your proxy.
"""
from __future__ import annotations

import argparse
import hmac
import json
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 64 * 1024
PER_MINUTE = 120
PER_PROBLEM_PER_DAY = 200
MAX_PROBLEMS_PER_DAY = 500                 # different problems in one day
MAX_TOTAL_BYTES = 512 * 1024 * 1024        # all reports together
SCHEMA = "legacy_player.report.v1"
STRING_LIMIT = 6000


def clean(value, depth: int = 0):
    """Keep only plain, bounded JSON so a report can never be used to store something else."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        return {str(k)[:60]: clean(v, depth + 1) for k, v in list(value.items())[:80]}
    if isinstance(value, list):
        return [clean(v, depth + 1) for v in value[:80]]
    if isinstance(value, str):
        return value[:STRING_LIMIT]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:200]


def valid(report) -> bool:
    return (isinstance(report, dict) and report.get("schema") == SCHEMA and isinstance(report.get("error"), dict)
            and re.fullmatch(r"[a-f0-9]{12}", str(report.get("id", ""))) is not None
            and re.fullmatch(r"[a-f0-9]{12}", str(report.get("fingerprint", ""))) is not None)


class Store:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.minute = (0, 0)
        self.daily: dict[tuple[str, str], int] = {}
        self.bytes_written = sum(p.stat().st_size for p in self.folder.rglob('*.json')) if self.folder.is_dir() else 0

    def accept(self, report: dict) -> str:
        """Returns "ok", "limit" or "bad"."""
        if not valid(report):
            return "bad"
        report = clean(report)
        now = time.time()
        day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        with self.lock:
            window, count = self.minute
            if int(now // 60) != window:
                window, count = int(now // 60), 0
            if count >= PER_MINUTE:
                return "limit"
            self.minute = (window, count + 1)
            key = (day, report["fingerprint"])
            if self.daily.get(key, 0) >= PER_PROBLEM_PER_DAY:
                return "limit"
            if key not in self.daily and sum(1 for k in self.daily if k[0] == day) >= MAX_PROBLEMS_PER_DAY:
                return "limit"                         # a sender inventing fingerprints can not fill the disk with new folders
            text = json.dumps(report, indent=2) + "\n"
            if self.bytes_written + len(text) > MAX_TOTAL_BYTES:
                return "limit"
            self.daily[key] = self.daily.get(key, 0) + 1
            target = self.folder / day / report["fingerprint"]
            target.mkdir(parents=True, exist_ok=True)
            try:
                with (target / f"{report['id']}.json").open("x", encoding="utf-8", newline="\n") as f:    # never overwrite an earlier report
                    f.write(text)
            except FileExistsError:
                return "ok"
            self.bytes_written += len(text)
            line = {"day": day, "fingerprint": report["fingerprint"], "id": report["id"], "kind": report.get("kind"),
                    "version": (report.get("app") or {}).get("version"), "error": (report.get("error") or {}).get("type"),
                    "message": str((report.get("error") or {}).get("message", ""))[:160]}
            with (self.folder / "index.jsonl").open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(line) + "\n")
        return "ok"


def make_handler(store: Store, token: str | None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LegacyPlayerReports"
        timeout = 10                                 # a sender that stalls does not hold a thread open

        def log_message(self, *args) -> None:       # no request log: who sent what is deliberately not kept
            pass

        def _answer(self, code: int, text: str = "") -> None:
            body = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self._answer(200, "Legacy Player report receiver\n") if self.path in ("/", "/health") else self._answer(404)

        def do_POST(self) -> None:
            if token and not hmac.compare_digest((self.headers.get("X-Report-Token") or "").encode("utf-8", "replace"), token.encode("utf-8")):
                return self._answer(401)
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                return self._answer(413)
            try:
                report = json.loads(self.rfile.read(length))
            except ValueError:
                return self._answer(400)
            result = store.accept(report)
            self._answer({"ok": 202, "limit": 429, "bad": 400}[result])
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default="reports")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--token", default=None)
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(Store(Path(args.dir)), args.token))
    print(f"Receiving reports on http://{args.host}:{args.port}/ into {args.dir}  (put HTTPS in front of it)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
