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

The admin console: open  /admin  in a browser with --admin-token SOMETHING-ELSE (or LP_ADMIN_TOKEN). It lists every report
that came in (crashes, failures and the "See a problem?" reports players write), lets you filter by kind, category and
status, read each one, and mark it new / looking / fixed / won't fix with a note. Status and notes live in
<dir>/triage.json; reports themselves are never changed. The console is a separate door from the one the app uses: the
app's POST never needs the admin token, and the admin token never accepts reports.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from server.http_guard import BoundedHTTPServer

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


STATUSES = ("new", "looking", "fixed", "wontfix")


class Store:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.triage_path = self.folder / "triage.json"
        try:
            self.triage: dict = json.loads(self.triage_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.triage = {}
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
            ctx = report.get("context") if isinstance(report.get("context"), dict) else {}
            line = {"day": day, "fingerprint": report["fingerprint"], "id": report["id"], "kind": report.get("kind"),
                    "version": (report.get("app") or {}).get("version"), "error": (report.get("error") or {}).get("type"),
                    "message": str((report.get("error") or {}).get("message", ""))[:160],
                    "category": str(ctx.get("category") or "")[:30], "at": report.get("created") or ""}
            with (self.folder / "index.jsonl").open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(line) + "\n")
        return "ok"

    # --- the admin console's view ------------------------------------------------------------------------
    def index(self) -> list[dict]:
        rows = []
        try:
            with (self.folder / "index.jsonl").open(encoding="utf-8") as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            return []
        seen: dict[str, dict] = {}
        for r in rows:                                   # one row per problem, with how many times it came in
            key = r["fingerprint"] if r.get("kind") != "user-report" else r["id"]
            row = seen.get(key)
            if row is None:
                row = seen[key] = {**r, "count": 0, "ids": [], "first": r.get("day"), "last": r.get("day")}
            row["count"] += 1
            row["ids"].append(r["id"])
            row["last"] = r.get("day")
            row["id"] = r["id"]
            row["message"] = r.get("message") or row.get("message")
        out = []
        for key, row in seen.items():
            t = self.triage.get(key) or {}
            row["key"] = key
            row["status"] = t.get("status", "new")
            row["note"] = t.get("note", "")
            out.append(row)
        out.sort(key=lambda r: (r["status"] != "new", r.get("last") or "", r.get("at") or ""), reverse=False)
        out.sort(key=lambda r: (r.get("last") or "") + (r.get("at") or ""), reverse=True)
        return out

    def read(self, rid: str) -> dict | None:
        if not re.fullmatch(r"[a-f0-9]{12}", rid or ""):
            return None
        for path in self.folder.rglob(f"{rid}.json"):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        return None

    def set_triage(self, key: str, status: str, note: str) -> dict:
        if status not in STATUSES:
            raise ValueError("unknown status")
        key = re.sub(r"[^a-f0-9]", "", key or "")[:12]
        if not key:
            raise ValueError("bad key")
        with self.lock:
            self.triage[key] = {"status": status, "note": str(note or "")[:2000], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            tmp = self.triage_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.triage, indent=1), encoding="utf-8")
            os.replace(tmp, self.triage_path)
        return self.triage[key]


ADMIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Legacy Player reports</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#141a33;--line:#2a3155;--text:#eef1ff;--mute:#aab3d6;--accent:#4f8cff;--good:#3be0a8;--warn:#ffb454;--bad:#ff8c98}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 "Segoe UI Variable","Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--text)}
header{display:flex;align-items:center;gap:14px;padding:14px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:2}
h1{font-size:1.1rem;margin:0}.grow{flex:1}main{max-width:1240px;margin:0 auto;padding:18px 22px}
.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
select,input,textarea,button{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 12px}
button{cursor:pointer}button.primary{background:var(--accent);border-color:transparent;color:#fff;font-weight:600}
table{width:100%;border-collapse:collapse}td,th{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--mute);font-size:.82rem}
tr.row{cursor:pointer}tr.row:hover{background:#ffffff0a}.pill{display:inline-block;font-size:.74rem;padding:2px 9px;border-radius:999px;border:1px solid var(--line);color:var(--mute)}
.pill.new{color:var(--warn);border-color:var(--warn)}.pill.looking{color:var(--accent);border-color:var(--accent)}.pill.fixed{color:var(--good);border-color:var(--good)}.pill.wontfix{opacity:.6}
.pill.user-report{color:#f472b6;border-color:#f472b6}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(640px,100%);background:var(--panel);border-left:1px solid var(--line);padding:18px;overflow:auto;box-shadow:-10px 0 40px #0008}
.drawer pre{white-space:pre-wrap;word-break:break-word;background:#0b1020;padding:12px;border-radius:10px;font-size:.82rem;max-height:50vh;overflow:auto}
.muted{color:var(--mute)}.small{font-size:.85rem}.stat{display:inline-flex;gap:6px;align-items:center;padding:6px 12px;border:1px solid var(--line);border-radius:10px}
.msg{max-width:520px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:#3a4a8a;border-radius:8px}::-webkit-scrollbar-track{background:transparent}
</style></head><body>
<header><h1>Legacy Player &middot; reports</h1><span class="muted small" id="where"></span><span class="grow"></span><button onclick="load()">Refresh</button></header>
<main>
 <div class="bar" id="stats"></div>
 <div class="bar">
  <select id="fkind"><option value="">Every kind</option><option value="user-report">Written by a player</option><option value="crash">Crashes</option><option value="internal-error">Internal errors</option><option value="launch-failed">Game would not start</option><option value="page-error">Page errors</option><option value="thread-error">Background errors</option></select>
  <select id="fstatus"><option value="">Every status</option><option value="new">New</option><option value="looking">Looking</option><option value="fixed">Fixed</option><option value="wontfix">Won't fix</option></select>
  <input id="fq" placeholder="Search the message, category or version" style="min-width:280px">
 </div>
 <table><thead><tr><th>When</th><th>Kind</th><th>Category</th><th>Message</th><th>Version</th><th>Times</th><th>Status</th></tr></thead><tbody id="rows"></tbody></table>
</main>
<script>
let TOKEN="";try{TOKEN=sessionStorage.getItem("lpadminkey")||""}catch(e){}if(location.search){try{history.replaceState(null,"",location.pathname)}catch(e){}}
const $=s=>document.querySelector(s);let ROWS=[];
async function api(path,body){const h={"X-Admin-Token":TOKEN};if(body)h["Content-Type"]="application/json";const r=await fetch(path,body?{method:"POST",headers:h,body:JSON.stringify(body)}:{headers:h});if(!r.ok)throw new Error("HTTP "+r.status);return r.json()}
function askKey(why){$("#rows").innerHTML='<tr><td colspan="7"><p class="muted small">'+esc(why||"Paste the admin token this receiver was started with (--admin-token).")+'</p><form id="kf" style="display:flex;gap:8px"><input id="key" type="password" autocomplete="off" style="flex:1"><button class="primary">Open</button></form></td></tr>';
 $("#kf").onsubmit=e=>{e.preventDefault();TOKEN=$("#key").value.trim();try{sessionStorage.setItem("lpadminkey",TOKEN)}catch(x){}load()}}
function esc(t){return String(t==null?"":t).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function draw(){const k=$("#fkind").value,st=$("#fstatus").value,q=$("#fq").value.toLowerCase();
 const list=ROWS.filter(r=>(!k||r.kind===k)&&(!st||r.status===st)&&(!q||(r.message+" "+r.category+" "+r.version+" "+r.error).toLowerCase().includes(q)));
 $("#rows").innerHTML=list.map(r=>`<tr class="row" data-key="${esc(r.key)}" data-id="${esc(r.id)}"><td class="small">${esc(r.last||r.day)}</td><td><span class="pill ${esc(r.kind)}">${esc(r.kind)}</span></td><td class="small">${esc(r.category||"")}</td><td class="msg" title="${esc(r.message)}">${esc(r.message)}</td><td class="small">${esc(r.version||"")}</td><td>${r.count}</td><td><span class="pill ${esc(r.status)}">${esc(r.status)}</span>${r.note?' <span class="muted small">'+esc(r.note.slice(0,40))+'</span>':''}</td></tr>`).join("")||'<tr><td colspan="7" class="muted">Nothing here.</td></tr>';
 const n=s=>ROWS.filter(r=>r.status===s).length;$("#stats").innerHTML=`<span class="stat">${ROWS.length} problems</span><span class="stat">${n("new")} new</span><span class="stat">${n("looking")} looking</span><span class="stat">${n("fixed")} fixed</span><span class="stat">${ROWS.filter(r=>r.kind==="user-report").length} written by players</span>`;
 document.querySelectorAll("tr.row").forEach(tr=>tr.onclick=()=>open(tr.dataset.key,tr.dataset.id))}
async function open(key,id){const r=ROWS.find(x=>x.key===key);const rep=await api("/admin/report?id="+encodeURIComponent(id)).catch(()=>null);
 const old=document.querySelector(".drawer");if(old)old.remove();const d=document.createElement("div");d.className="drawer";
 const ctx=(rep&&rep.context)||{};
 d.innerHTML=`<div style="display:flex;gap:10px;align-items:center"><h2 style="margin:0;flex:1;font-size:1.05rem">${esc(r.kind)} &middot; ${esc(r.category||r.error||"")}</h2><button id="close">Close</button></div>
 <p class="small muted">First ${esc(r.first)} &middot; last ${esc(r.last)} &middot; ${r.count} time(s) &middot; version ${esc(r.version||"?")} &middot; id ${esc(r.id)}</p>
 ${ctx.description?`<p><b>What the player wrote:</b><br>${esc(ctx.description)}</p>`:""}
 <p><b>Message:</b> ${esc(r.message)}</p>
 <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0"><select id="st"><option value="new">New</option><option value="looking">Looking</option><option value="fixed">Fixed</option><option value="wontfix">Won't fix</option></select><button class="primary" id="save">Save</button></div>
 <textarea id="note" rows="3" style="width:100%" placeholder="Your note (only you see it)">${esc(r.note||"")}</textarea>
 <h3 class="small muted" style="margin:14px 0 6px">The whole report</h3><pre>${esc(rep?JSON.stringify(rep,null,2):"(could not read the file)")}</pre>`;
 document.body.append(d);d.querySelector("#st").value=r.status;d.querySelector("#close").onclick=()=>d.remove();
 d.querySelector("#save").onclick=async()=>{const t=await api("/admin/triage",{key,status:d.querySelector("#st").value,note:d.querySelector("#note").value});r.status=t.status;r.note=t.note;draw()}}
async function load(){if(!TOKEN)return askKey();try{const d=await api("/admin/list");ROWS=d.reports;$("#where").textContent=d.folder;draw()}catch(e){if(/401/.test(e.message)){try{sessionStorage.removeItem("lpadminkey")}catch(x){}TOKEN="";askKey("That token was not accepted. Paste it again.")}else $("#rows").innerHTML='<tr><td colspan="7">Could not load: '+esc(e.message)+'</td></tr>'}}
["#fkind","#fstatus","#fq"].forEach(s=>$(s).addEventListener("input",draw));load();
</script></body></html>"""


def make_handler(store: Store, token: str | None, admin_token: str | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LegacyPlayerReports"
        timeout = 10                                 # a sender that stalls does not hold a thread open

        def log_message(self, *args) -> None:       # no request log: who sent what is deliberately not kept
            pass

        def _answer(self, code: int, text: str = "", content_type: str = "text/plain; charset=utf-8") -> None:
            body = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _admin_ok(self) -> bool:
            """Only the X-Admin-Token header: a ?token= in the address would be kept in browser history and proxy logs."""
            if not admin_token:
                return False
            given = self.headers.get("X-Admin-Token") or ""
            return hmac.compare_digest(given.encode("utf-8", "replace"), admin_token.encode("utf-8"))

        def do_GET(self) -> None:
            from urllib.parse import parse_qs, urlsplit
            u = urlsplit(self.path)
            if u.path in ("/", "/health"):
                return self._answer(200, "Legacy Player report receiver\n")
            if u.path in ("/admin", "/admin/") and admin_token:
                return self._answer(200, ADMIN_PAGE, "text/html; charset=utf-8")     # the page asks for the token itself
            if u.path.startswith("/admin"):
                if not self._admin_ok():
                    return self._answer(401, "admin token needed")
                if u.path == "/admin/list":
                    return self._answer(200, json.dumps({"reports": store.index(), "folder": str(store.folder)}), "application/json")
                if u.path == "/admin/report":
                    rep = store.read(parse_qs(u.query).get("id", [""])[0])
                    return self._answer(200, json.dumps(rep), "application/json") if rep else self._answer(404, "{}", "application/json")
            self._answer(404)

        def do_POST(self) -> None:
            from urllib.parse import urlsplit
            if urlsplit(self.path).path == "/admin/triage":
                if not self._admin_ok():
                    return self._answer(401)
                try:
                    length = int(self.headers.get("Content-Length", "-1"))
                    body = json.loads(self.rfile.read(length)) if 0 < length <= MAX_BODY else {}
                    out = store.set_triage(str(body.get("key", "")), str(body.get("status", "")), str(body.get("note", "")))
                except (ValueError, TypeError, AttributeError, RecursionError):
                    return self._answer(400)
                return self._answer(200, json.dumps(out), "application/json")
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
            except (ValueError, RecursionError):
                return self._answer(400)
            try:
                result = store.accept(report)
            except (ValueError, TypeError, RecursionError):
                result = "bad"
            self._answer({"ok": 202, "limit": 429, "bad": 400}[result])
    return Handler


class ReceiverHTTPServer(BoundedHTTPServer):
    """At most MAX_CONCURRENT requests at once, each with a total deadline, and never the sender's address in a log
    (the stock error report would print it with a traceback)."""
    label = "report receiver"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default="reports")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--token", default=os.environ.get("LP_REPORT_TOKEN") or None)
    parser.add_argument("--admin-token", default=os.environ.get("LP_ADMIN_TOKEN") or None,
                        help="turns on the admin console at /admin (the page asks for this token; without it the console is off)")
    args = parser.parse_args()
    httpd = ReceiverHTTPServer((args.host, args.port), make_handler(Store(Path(args.dir)), args.token, args.admin_token))
    print(f"Receiving reports on http://{args.host}:{args.port}/ into {args.dir}  (put HTTPS in front of it)", flush=True)
    if args.admin_token:
        print(f"Admin console: http://{args.host}:{args.port}/admin  (paste the --admin-token when it asks)", flush=True)
    else:
        print("Admin console is off: start with --admin-token SOMETHING-LONG to read and triage reports in a browser.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
