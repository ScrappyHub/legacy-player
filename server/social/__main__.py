"""HTTP front of the friends service:   python -m server.social --dir social --port 8791

One endpoint, JSON in and out:  POST /  {"op": "...", "id": "...", "secret": "...", ...}  ->  {"ok": true, ...} or {"ok": false,
"error": "..."}.  GET /health answers "ok".

Most people never run this by hand: Legacy Player runs it for them (Friends > Run a friends service on this computer),
with its own certificate, the router port opened and moderation inside the app.

Moderation: on first start the service makes a moderator key and keeps it in <dir>/moderator.key (or use --admin-token /
LP_SOCIAL_ADMIN_TOKEN to choose one). Legacy Player on the same computer reads it by itself. Anyone else who helps moderate
pastes the key once in Legacy Player (Friends > Moderation), or opens /admin in a browser and pastes it there. With the
key you read reports (with the reported message and the few before it), time players out, ban and unban them, and
turn the service-wide word filter on or off.

HTTPS: --tls-cert/--tls-key serve it directly (Legacy Player uses its self-signed certificate and friends' apps check its
fingerprint, which travels in the friends link); or put a reverse proxy or a tunnel in front. No request log is kept:
who talked to whom is deliberately not recorded."""
from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import SocialError, SocialService

MAX_BODY = 16 * 1024
OPS = {"hello", "heartbeat", "request", "decide", "remove", "invite", "dismiss_invite", "message", "thread", "goodbye",
       "block", "unblock", "clear_thread", "read_all", "report"}


def dispatch(service: SocialService, body: dict) -> dict:
    op = str(body.get("op") or "")
    if op not in OPS:
        raise SocialError("unknown operation")
    pid, secret = body.get("id"), body.get("secret")
    if op == "hello":
        return service.hello(body.get("name"))
    if op == "heartbeat":
        return service.heartbeat(pid, secret, body.get("name"), body.get("status", ""), body.get("room"), body.get("requests_open"))
    if op == "report":
        return service.report(pid, secret, body.get("player"), body.get("category"), body.get("details", ""), body.get("message", ""),
                              bool(body.get("block")))
    if op == "request":
        return service.request(pid, secret, body.get("code"))
    if op == "decide":
        return service.decide(pid, secret, body.get("from"), bool(body.get("accept")))
    if op == "remove":
        return service.remove(pid, secret, body.get("friend"))
    if op == "invite":
        return service.invite(pid, secret, body.get("to"), body.get("invite_code"), body.get("game"), body.get("server_code", ""))
    if op == "dismiss_invite":
        return service.dismiss_invite(pid, secret, body.get("from"))
    if op == "message":
        return service.message(pid, secret, body.get("to"), body.get("text"))
    if op == "thread":
        return service.thread(pid, secret, body.get("friend"))
    if op == "block":
        return service.block(pid, secret, body.get("player"))
    if op == "unblock":
        return service.unblock(pid, secret, body.get("player"))
    if op == "clear_thread":
        return service.clear_thread(pid, secret, body.get("friend"))
    if op == "read_all":
        return service.read_all(pid, secret)
    return service.goodbye(pid, secret)


ADMIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Friends moderation</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#141a33;--line:#2a3155;--text:#eef1ff;--mute:#aab3d6;--accent:#4f8cff;--good:#3be0a8;--warn:#ffb454;--bad:#ff8c98}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 "Segoe UI Variable","Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--text)}
header{display:flex;align-items:center;gap:14px;padding:14px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:2;flex-wrap:wrap}
h1{font-size:1.1rem;margin:0}.grow{flex:1}main{max-width:1240px;margin:0 auto;padding:18px 22px}
.tabs button.on{background:var(--accent);color:#fff;border-color:transparent}
select,input,textarea,button{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:7px 12px}
button{cursor:pointer}button.primary{background:var(--accent);border-color:transparent;color:#fff;font-weight:600}button.bad{border-color:var(--bad);color:var(--bad)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin-bottom:12px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.muted{color:var(--mute)}.small{font-size:.85rem}
.pill{display:inline-block;font-size:.74rem;padding:2px 9px;border-radius:999px;border:1px solid var(--line);color:var(--mute)}
.pill.open{color:var(--warn);border-color:var(--warn)}.pill.resolved{color:var(--good);border-color:var(--good)}.pill.banned{color:var(--bad);border-color:var(--bad)}.pill.muted{color:var(--warn);border-color:var(--warn)}
.quote{border-left:3px solid var(--bad);padding:6px 12px;margin:8px 0;background:#0b1020;border-radius:8px}
.ctx{font-size:.84rem;color:var(--mute);margin:2px 0}.ctx b{color:var(--text);font-weight:600}
table{width:100%;border-collapse:collapse}td,th{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--mute);font-size:.82rem}
.stat{display:inline-flex;gap:6px;padding:6px 12px;border:1px solid var(--line);border-radius:10px}
</style></head><body>
<header><h1>Friends service &middot; moderation</h1><span id="stats" class="row"></span><span class="grow"></span>
 <span class="row tabs"><button data-t="reports" class="on">Reports</button><button data-t="players">Players</button><button data-t="filter">Word filter</button><button data-t="log">Log</button></span><button onclick="load()">Refresh</button></header>
<main id="main"></main>
<script>
let TOKEN=new URLSearchParams(location.search).get("token")||"";try{TOKEN=TOKEN||sessionStorage.getItem("lpmodkey")||""}catch(e){}const $=s=>document.querySelector(s);let tab="reports",D=null,status="open";
async function api(path,body){const r=await fetch(path+(path.includes("?")?"&":"?")+"token="+encodeURIComponent(TOKEN),body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||("HTTP "+r.status));return j}
const esc=t=>String(t==null?"":t).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const when=t=>t?new Date(t*1000).toLocaleString():"";
const state=p=>!p?"":p.banned?'<span class="pill banned">banned</span>':p.muted?'<span class="pill muted">timed out until '+esc(when(p.muted.until))+'</span>':"";
const actions=(pid,rid)=>`<div class="row" style="margin-top:8px"><input placeholder="Reason (the player sees it)" data-reason style="min-width:240px">
 <select data-len><option value="1h">1 hour</option><option value="24h">24 hours</option><option value="7d">7 days</option><option value="30d">30 days</option></select>
 <button data-act="timeout" data-p="${esc(pid)}" data-r="${esc(rid||"")}">Time out</button><button data-act="untimeout" data-p="${esc(pid)}">End time-out</button>
 <button class="bad" data-act="ban" data-p="${esc(pid)}" data-r="${esc(rid||"")}">Ban</button><button data-act="unban" data-p="${esc(pid)}">Unban</button>
 ${rid?`<button data-act="resolve" data-r="${esc(rid)}">Mark handled</button><button data-act="dismiss" data-r="${esc(rid)}">Dismiss</button>`:""}</div>`;
function wire(){document.querySelectorAll("[data-act]").forEach(b=>b.onclick=async()=>{const box=b.closest(".card,tr");const reason=(box.querySelector("[data-reason]")||{}).value||"",len=(box.querySelector("[data-len]")||{}).value||"";
 if(b.dataset.act==="ban"&&!confirm("Ban this player from the friends service?"))return;
 try{await api("/admin/act",{action:b.dataset.act,player:b.dataset.p||"",report:b.dataset.r||"",length:len,reason});load()}catch(e){alert(e.message)}})}
function draw(){const m=$("#main");if(!D){m.innerHTML='<p class="muted">Loading…</p>';return}
 $("#stats").innerHTML=`<span class="stat">${D.open} open reports</span><span class="stat">${D.players} players</span><span class="stat">${D.muted} timed out</span><span class="stat">${D.banned} banned</span><span class="stat">filter ${D.filter.on?"on":"off"}</span>`;
 if(tab==="reports"){const list=D.reports.filter(r=>!status||r.status===status);
  m.innerHTML=`<div class="row" style="margin-bottom:12px"><select id="st"><option value="open">Open</option><option value="resolved">Handled</option><option value="dismissed">Dismissed</option><option value="">All</option></select></div>`+
   (list.map(r=>`<div class="card"><div class="row"><b>${esc(r.target.name)}</b><span class="muted small">${esc(r.target.code)}</span>${state(r.target_state)}<span class="pill ${esc(r.status)}">${esc(r.status)}</span><span class="pill">${esc(r.category)}</span><span class="grow"></span><span class="muted small">${esc(when(r.at))} · reported by ${esc(r.reporter.name)} · ${r.target_state.reports} report(s) about them</span></div>
    ${r.details?`<p style="margin:8px 0 0">${esc(r.details)}</p>`:""}
    ${r.context&&r.context.length?'<div style="margin-top:8px">'+r.context.map(c=>`<div class="ctx"><b>${c.from==="reported"?esc(r.target.name):esc(r.reporter.name)}:</b> ${esc(c.text)}</div>`).join("")+"</div>":""}
    ${r.message?`<div class="quote"><b>${esc(r.target.name)}:</b> ${esc(r.message.text)} <span class="muted small">(${esc(when(r.message.at))})</span></div>`:""}
    ${actions(r.target.id,r.id)}</div>`).join("")||'<p class="muted">Nothing here.</p>');
  $("#st").value=status;$("#st").onchange=e=>{status=e.target.value;draw()}}
 else if(tab==="players"){m.innerHTML=`<div class="row" style="margin-bottom:12px"><input id="q" placeholder="Name, friend code or id" style="min-width:280px"><button id="go" class="primary">Search</button></div><div id="pl"></div>`;
  const run=async()=>{const d=await api("/admin/players?q="+encodeURIComponent($("#q").value));$("#pl").innerHTML=d.players.map(p=>`<div class="card"><div class="row"><b>${esc(p.name)}</b><span class="muted small">${esc(p.code)} · ${esc(p.id)}</span>${state(p)}<span class="grow"></span><span class="muted small">${p.friends} friends · ${p.reports} report(s) · seen ${esc(when(p.seen))}</span></div>${actions(p.id,"")}</div>`).join("")||'<p class="muted">No one found.</p>';wire()};
  $("#go").onclick=run;$("#q").onkeydown=e=>{if(e.key==="Enter")run()};run();return}
 else if(tab==="filter"){m.innerHTML=`<div class="card"><h3 style="margin-top:0">Service-wide word filter</h3><p class="muted small">When on, messages and player names with these words are refused by the service (players also have their own filter that hides words on their screen). The built-in list covers common profanity; add your own words below, one per line or separated by commas. Disguises like l33t letters, s p a c e s and repeated letters are caught.</p>
  <label class="row"><input type="checkbox" id="fon" ${D.filter.on?"checked":""}> Refuse messages and names with filtered words</label>
  <p class="small muted" style="margin:10px 0 4px">Your words (${D.filter.words.length})</p><textarea id="fw" rows="8" style="width:100%">${esc(D.filter.words.join("\\n"))}</textarea>
  <div class="row" style="margin-top:8px"><button class="primary" id="fsave">Save</button></div></div>`;
  $("#fsave").onclick=async()=>{await api("/admin/filter",{on:$("#fon").checked,words:$("#fw").value});load()}}
 else{m.innerHTML='<table><thead><tr><th>When</th><th>Action</th><th>Player</th><th>Length</th><th>Reason</th></tr></thead><tbody>'+D.log.map(l=>`<tr><td class="small">${esc(when(l.at))}</td><td>${esc(l.action)}</td><td>${esc(l.name)} <span class="muted small">${esc(l.player)}</span></td><td>${esc(l.length)}</td><td>${esc(l.reason)}</td></tr>`).join("")+"</tbody></table>"}
 wire()}
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{tab=b.dataset.t;document.querySelectorAll(".tabs button").forEach(x=>x.classList.toggle("on",x===b));draw()});
function askKey(why){$("#main").innerHTML='<div class="card" style="max-width:560px"><h2 style="margin-top:0">Moderator key</h2><p class="muted small">'+esc(why||"Paste the moderator key. Whoever runs this service finds it in Legacy Player (Friends > Your service > Copy moderator key) or in the moderator.key file next to the service's data.")+'</p><div class="row"><input id="key" type="password" style="flex:1" autocomplete="off"><button class="primary" id="go">Open</button></div></div>';
 $("#go").onclick=()=>{TOKEN=$("#key").value.trim();try{sessionStorage.setItem("lpmodkey",TOKEN)}catch(e){}load()}}
async function load(){if(!TOKEN)return askKey();try{D=await api("/admin/reports");draw()}catch(e){if(/401|token/.test(e.message)){try{sessionStorage.removeItem("lpmodkey")}catch(x){}TOKEN="";askKey("That key was not accepted. Paste it again.")}else $("#main").innerHTML='<p>Could not load: '+esc(e.message)+'</p>'}}
load();
</script></body></html>"""


def make_handler(service: SocialService, admin_token: str | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LegacyPlayerFriends"
        timeout = 10

        def log_message(self, *args) -> None:
            pass

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _admin_ok(self) -> bool:
            if not admin_token:
                return False
            from urllib.parse import parse_qs, urlsplit
            given = self.headers.get("X-Admin-Token") or parse_qs(urlsplit(self.path).query).get("token", [""])[0]
            return hmac.compare_digest(given.encode("utf-8", "replace"), admin_token.encode("utf-8"))

        def _page(self, html: str) -> None:
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            from urllib.parse import parse_qs, urlsplit
            u = urlsplit(self.path)
            if u.path in ("/", "/health"):
                return self._json(200, {"ok": True, "service": "legacy-player-friends"})
            if u.path in ("/admin", "/admin/") and admin_token:
                return self._page(ADMIN_PAGE)              # the page asks for the key; every answer it loads needs it
            if u.path.startswith("/admin"):
                if not self._admin_ok():
                    return self._json(401, {"ok": False, "error": "admin token needed"})
                q = parse_qs(u.query)
                if u.path == "/admin":
                    return self._page(ADMIN_PAGE)
                if u.path == "/admin/reports":
                    return self._json(200, {"ok": True, **service.admin_reports(q.get("status", [""])[0])})
                if u.path == "/admin/players":
                    return self._json(200, {"ok": True, **service.admin_players(q.get("q", [""])[0])})
            self._json(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:
            from urllib.parse import urlsplit
            path = urlsplit(self.path).path
            if path.startswith("/admin/"):
                if not self._admin_ok():
                    return self._json(401, {"ok": False, "error": "admin token needed"})
                try:
                    length = int(self.headers.get("Content-Length", "-1"))
                    body = json.loads(self.rfile.read(length)) if 0 < length <= MAX_BODY else {}
                    if path == "/admin/act":
                        out = service.admin_act(str(body.get("action", "")), str(body.get("player", "")), str(body.get("report", "")),
                                                str(body.get("length", "")), str(body.get("reason", "")))
                    elif path == "/admin/filter":
                        out = service.admin_filter(body.get("on"), body.get("words"))
                    elif path == "/admin/stop":
                        if self.client_address[0] not in ("127.0.0.1", "::1"):
                            return self._json(403, {"ok": False, "error": "only from this computer"})
                        threading.Thread(target=self.server.shutdown, daemon=True).start()
                        out = {"stopping": True}
                    else:
                        return self._json(404, {"ok": False, "error": "not found"})
                except SocialError as exc:
                    return self._json(400, {"ok": False, "error": str(exc)})
                except (ValueError, TypeError):
                    return self._json(400, {"ok": False, "error": "bad request"})
                return self._json(200, {"ok": True, **out})
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                return self._json(413, {"ok": False, "error": "bad request size"})
            try:
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._json(400, {"ok": False, "error": "invalid JSON"})
            try:
                out = dispatch(service, body)
            except SocialError as exc:
                return self._json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:                       # never a traceback to a stranger
                return self._json(500, {"ok": False, "error": f"something went wrong ({type(exc).__name__})"})
            self._json(200, {"ok": True, **out})
    return Handler


def moderator_key(folder: Path) -> str:
    """The moderator key, made once and kept next to the service's data (readable only by this user where possible)."""
    import secrets
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "moderator.key"
    try:
        key = path.read_text(encoding="utf-8").strip()
        if len(key) >= 16:
            return key
    except OSError:
        pass
    key = "LPM-" + secrets.token_urlsafe(24)
    path.write_text(key + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default=os.environ.get("LP_SOCIAL_DIR") or "social")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--admin-token", default=os.environ.get("LP_SOCIAL_ADMIN_TOKEN") or None,
                        help="choose the moderator key yourself (otherwise one is made and kept in <dir>/moderator.key)")
    parser.add_argument("--tls-cert", help="serve HTTPS directly with this certificate (PEM)")
    parser.add_argument("--tls-key", help="the certificate's private key (PEM)")
    args = parser.parse_args(argv)
    folder = Path(args.dir)
    key = args.admin_token or moderator_key(folder)
    service = SocialService(folder)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(service, key))
    scheme = "http"
    if args.tls_cert:
        import ssl
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.tls_cert, args.tls_key)
        # the handshake happens in each request thread, so a stranger who never finishes it cannot hold up the others
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True, do_handshake_on_connect=False)
        scheme = "https"

    def tidy() -> None:
        while True:
            time.sleep(600)
            with service.lock:
                service._tidy()
                service.save()
    threading.Thread(target=tidy, daemon=True).start()
    print(f"Friends service on {scheme}://{args.host}:{httpd.server_address[1]}/ keeping its players in {folder}"
          + ("" if scheme == "https" else "  (put HTTPS in front of it)"), flush=True)
    print(f"Moderation: open {scheme}://<this address>/admin and paste the moderator key"
          + (" you chose" if args.admin_token else f" from {folder / 'moderator.key'}")
          + ", or paste it once in Legacy Player (Friends > Moderation).", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with service.lock:
            service.save()


if __name__ == "__main__":
    main()
