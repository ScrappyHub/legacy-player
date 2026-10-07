import re
old=open('old_index.html').read()
css=open('style.css').read(); core=open('core.js').read(); views=open('views.js').read()+open('views2.js').read(); views3=open('views3.js').read()+open('views4.js').read()+open('views5.js').read()
i_script=old.index('<script>')+len('<script>\n'); i_end=old.index('</script>')
js=old[i_script:i_end]
# 1 drop old core (until Library section)
js=js[js.index('/* ---------- Library ---------- */'):]
def cut(js,start,end):
    a=js.index(start); b=js.index(end); return js[:a]+js[b:]
js=cut(js,'/* ---------- First-run setup wizard ---------- */','/* ---------- Credits ---------- */')
js=cut(js,'/* ---------- Help ---------- */','setInterval(()=>{api("ping")')
# quit handler + init
a=js.index('$("#quitbtn")'); b=js.index('window.addEventListener("pagehide"')
js=js[:a]+js[b:]
a=js.index('(async function init()')
js=js[:a]+views3+'\n'+'''(async function init(){try{const s=await api("settings");S.settings=s.values;document.documentElement.dataset.theme=s.values.theme}catch(e){}
 buildMenubar();$("#brand").addEventListener("click",()=>nav("home"));$("#logomartin").append(martin(34));$("#bootmartin").append(martin(96,"hop"));
 try{S.profile=await api("profile")}catch(e){}renderWho();
 const r=await api("mp_state").catch(()=>({room:null}));S.room=r.room;S.waits=r.waits||[];if(S.room||S.waits.length)poll();pingServer();setInterval(pingServer,15000);
 if(S.settings&&!S.settings.setup_done)S.tab="welcome";
 await go();
 setTimeout(()=>{const b=$("#boot");if(b){b.classList.add("gone");setTimeout(()=>b.remove(),800)}},350);
 setTimeout(()=>autoNetTest(300),1200)})();
'''
def rep(js,old_s,new_s,count=1):
    assert old_s in js, old_s[:60]
    return js.replace(old_s,new_s,count)
# drawNetCheck
a=js.index('async function drawNetCheck'); b=js.index('async function drawBrowse')
js=js[:a]+'''function drawNetCheck(box){
 const r=S.netcheck&&S.netcheck.at?S.netcheck:null;
 const kinds={private:"home/office network",public:"public",cgnat:"shared by your provider",loopback:"not on a network",unknown:"unknown"};
 box.replaceChildren(h("div",{class:"row"},h("h3",{class:"grow"},whyInline("Is my network ready?","Measures this computer and the server you chose, and tests a pretend room on this computer. It contacts nothing else and sends nothing about you. It runs by itself when Legacy Player opens and when you connect to a server (you can turn that off in Settings > Multiplayer). To test reaching you from outside, someone on another network has to try joining.")),
   S.netBusy?h("span",{class:"small muted"},h("span",{class:"spin"}),"Testing",h("span",{class:"dots"})):(r?h("span",{class:"small muted"},"Last tested "+ago(r.at)):null),
   h("button",{class:"btn primary",disabled:S.netBusy,onclick:runNetTest},r?"Test again":"Test my network")),
  S.netBusy?h("div",{class:"bar live",style:"margin:8px 0"},h("i")):null,
  (!r&&!S.netBusy)?h("p",{class:"small muted"},"Not tested yet. Run a quick test to see if this computer should host, or join someone else."):null,
  r?h("div",{style:S.netBusy?"opacity:.55":""},
    h("div",{class:"panel",style:"margin:8px 0"},h("b",{class:r.advice.verdict==="join"?"warn":"good"},r.advice.headline),h("ul",{class:"small"},...r.advice.reasons.map(t=>h("li",{},t)))),
    h("table",{},h("tbody",{},
     h("tr",{},h("td",{},"This computer's network address"),h("td",{},ipSpan(r.address)," · "+kinds[r.address_kind])),
     h("tr",{},h("td",{},"Ping to "+r.server_name),h("td",{},r.server.ok?r.server.avg_ms+" ms average ("+r.server.min_ms+"–"+r.server.max_ms+"), jitter "+r.server.jitter_ms+" ms, "+r.server.loss_pct+"% lost":"no answer")),
     h("tr",{},h("td",{},"Pretend room on this computer"),h("td",{},r.room_load.players+" players, "+r.room_load.requests_per_s+" requests per second")),
     h("tr",{},h("td",{},"This computer's own speed"),h("td",{},r.mock.rtt_ms+" ms round trip, "+Math.round(r.mock.mbps)+" Mbps")))))
   :null)}
'''+js[b:]
# viewTogether
js=rep(js,'h("span",{class:"badge "+(ok?"good":"")},(ok?"● ":"○ ")+text);','h("span",{class:"badge "+(ok?"good":"")},(ok?"● ":"○ "),text);')
js=rep(js,'pill(st.online,st.online?"Connected to "+(remote?S.settings.server_host:"your own server"):"No server answering")','pill(st.online,st.online?["Connected to ",remote?ipSpan(S.settings.server_host):"your own server"]:"No server answering")')
js=rep(js,'if(!roomNow){const net=h("div",{class:"card",style:"margin-top:12px"});m.append(net);drawNetCheck(net)}','if(!roomNow){const net=h("div",{class:"card",id:"netbox",style:"margin-top:12px"});m.append(net);drawNetCheck(net);if(!(S.netcheck&&S.netcheck.at))api("network_last").then(x=>{if(x.at){S.netcheck=x;redrawNet()}}).catch(()=>{})}')
# viewServers
js=rep(js,'h("b",{},mine?"your own server (this computer)":V.server_host+":"+V.server_port)','h("b",{},mine?"your own server (this computer)":h("span",{},ipSpan(V.server_host),":"+V.server_port))')
js=rep(js,'h("p",{class:"small muted"},"Friends paste this into Connect to a server. It carries "+c.address+":"+c.port+" and the first part of your certificate fingerprint."),','h("p",{class:"small muted"},"Friends paste this into Connect to a server. It carries ",ipSpan(c.address),":"+c.port+" and the first part of your certificate fingerprint."),')
js=rep(js,':h("p",{class:"warn small"},c.error+" Share these instead: address "+c.address+", port "+c.port+", fingerprint "+(c.fingerprint||"-")+"."))};',':h("p",{class:"warn small"},c.error+" Share these instead: address ",ipSpan(c.address),", port "+c.port+", fingerprint "+(c.fingerprint||"-")+"."))};')
js=rep(js,'toast(r.connected?"Connected to "+r.host:r.message,r.connected?"":"warn");go()}},"Connect")','toast(r.connected?"Connected to the server":r.message,r.connected?"":"warn");go();if(r.connected)autoNetTest(0)}},"Connect")')
# pingServer: connection established -> test once
js=rep(js,'$("#srvtxt").textContent=r.online?"multiplayer server online":"multiplayer server offline";return r}','$("#srvtxt").textContent=r.online?"multiplayer server online":"multiplayer server offline";if(r.online&&!S.onlineSeen){S.onlineSeen=true;autoNetTest(S.netcheck&&S.netcheck.server&&S.netcheck.server.ok?1200:0)}return r}')
# runScan packages
js=rep(js,'''const names=Object.keys(v.emulators||{}).map(k=>v.emulators[k].name);''','''const names=Object.keys(v.emulators||{}).map(k=>v.emulators[k].name);const pk=Object.values(v.packages||{}).map(e=>e.name);''')
js=rep(js,'''"Scan finished. No emulator programs found in the usual places; add the folder you keep them in under Emulators.",names.length?"":"warn");''','''"Scan finished. No emulator programs found in the usual places; add the folder you keep them in under Emulators.",names.length?"":"warn");
 if(pk.length)toast("Found downloads that are not unpacked yet: "+pk.join(", ")+". Extract them, then add that folder under Emulators.","warn");''')
# emulators page: packages
js=rep(js,'''   v.state==="error"?h("p",{class:"bad small"},"The scan stopped: "+v.where):null,...rows].filter(Boolean));''','''   v.state==="error"?h("p",{class:"bad small"},"The scan stopped: "+v.where):null,...rows,
   ...Object.entries(v.packages||{}).map(([id,e])=>h("div",{class:"row small warn"},h("b",{style:"min-width:110px"},e.name),h("span",{class:"grow"},"a download that is not unpacked yet: "+e.paths[0]+". Extract it, then add its folder above.")))].filter(Boolean));''')
# engines: consoles strip + BIOS fold
js=rep(js,'''   h("div",{class:"card",style:"margin-top:12px"},h("table",{},h("thead",{},h("tr",{},h("th",{},"Engine")''','''   h("div",{class:"card",style:"margin-top:12px"},h("h3",{style:"margin-top:0"},whyInline("Consoles ready","A console is ready when at least one program that can run it has been found. Each console may use any of several emulators; pick them in Console mode or Emulators.")),
    h("div",{class:"chips"},...d.consoles.map(c=>h("span",{class:"chip"+(c.ready?" on":""),title:c.ready?"Plays with "+c.via:"No emulator found for this console yet"},c.name+(c.ready?" · "+c.via:""))))),
   h("div",{class:"card",style:"margin-top:12px"},h("table",{},h("thead",{},h("tr",{},h("th",{},"Engine")''')
a=js.index('   h("h3",{},whyInline("BIOS and firmware"'); b=js.index('   h("p",{class:"small muted"},"Downloads use only api.github.com')
js=js[:a]+'''   h("details",{class:"fold card",style:"margin-top:12px",open:!!S.biosOpen,ontoggle:e=>{S.biosOpen=e.target.open}},
    h("summary",{},h("b",{},whyInline("BIOS and firmware","Some consoles need a copy of their own system software to run. Those files belong to the console makers, so Legacy Player never downloads them: it finds the copies you dumped from hardware you own and tells you which are missing.")),
     h("span",{class:"badge "+(d.bios.some(b=>b.found.length)?"good":"")},d.bios.filter(b=>b.found.length).length+" of "+d.bios.length+" found"),h("span",{class:"small muted"},"click to open")),
    ...d.bios.map(b=>{const shown=b.found.slice(0,4),rest=b.found.slice(4);const line=f=>h("div",{class:"small"},f.path+"  ("+Math.round(f.size/1024)+" KB)");
     return h("div",{style:"margin:12px 0"},h("div",{class:"row"},h("b",{},b.name),h("span",{class:"small muted"},"for "+b.for),b.found.length?h("span",{class:"badge good"},b.found.length+" found"):h("span",{class:"badge"},"not found")),
      ...shown.map(line),rest.length?h("details",{},h("summary",{class:"small muted"},"and "+rest.length+" more…"),...rest.map(line)):null,b.found.length?null:h("div",{class:"small muted"},b.how))})),
'''+js[b:]
# settings
js=rep(js,'Object.entries(s.schema).forEach(([k,sp])=>{(groups[sp.group]=groups[sp.group]||[]).push([k,sp])});','Object.entries(s.schema).forEach(([k,sp])=>{if(sp.hidden)return;(groups[sp.group]=groups[sp.group]||[]).push([k,sp])});')
js=rep(js,'if(r){S.settings=r.values;if(k==="theme")document.documentElement.dataset.theme=val;if(k==="view"||k==="show_region")toast("Saved")}};','if(r){S.settings=r.values;if(k==="theme")document.documentElement.dataset.theme=val;if(k==="view"||k==="show_region")toast("Saved");if(k==="display_name"){S.profile=await api("profile");renderWho()}if(k==="auto_network_test"&&val)autoNetTest(300)}};')
# settings: put group "You" first
js=rep(js,'for(const[g,items]of Object.entries(groups)){','for(const[g,items]of Object.entries(groups).sort((a,b)=>(a[0]==="You"?-1:0)-(b[0]==="You"?-1:0))){')
js=rep(js,'async function runScan(){\n if(!await ask(','async function runScan(noAsk){\n if(!noAsk&&!await ask(')
js=rep(js,'const code=h("input",{type:"text",placeholder:"XXXXX-XXXXX",maxlength:12,','const code=h("input",{type:"text",placeholder:"XXXXX-XXXXX",value:S.joinCode||"",maxlength:12,')
js=rep(js,'''  d.skipped.unrecognized?h("p",{class:"muted small"},d.skipped.unrecognized''','''  h("p",{class:"muted small",style:"margin-top:14px"},(S.console?consoleName(S.console)+": ":"")+d.shown+" game"+(d.shown===1?"":"s")+" · "+fmtBytes(d.games.reduce((n,g)=>n+g.size_mb,0)*1048576)+(d.truncated?" (first 1000 counted)":"")+" · "+d.total+" in your whole library"),
  d.skipped.unrecognized?h("p",{class:"muted small"},d.skipped.unrecognized''')
# --- batch 3 patches ---
js=rep(js,'''h("div",{class:"t"},g.title),h("div",{class:"m"},consoleName(g.console)+(showRegion&&g.region?" · "+g.region:"")+" · "+g.size_mb+" MB"),''','''coverEl(g),h("div",{class:"t"},g.title),h("div",{class:"m"},consoleName(g.console)+(showRegion&&g.region?" · "+g.region:"")+" · "+g.size_mb+" MB"+(g.emulator?" · "+g.emulator:"")),''')
js=rep(js,'''h("div",{class:"tvtitle"},g.title),h("div",{class:"small muted"},[g.region,consoleName(g.console),g.launch&&g.launch.ready?g.launch.emulator:"no emulator"].filter(Boolean).join(" · "))''','''coverEl(g,"tv"),h("div",{class:"tvtitle"},g.title),h("div",{class:"small muted"},[g.region,consoleName(g.console),g.emulator||"no emulator"].filter(Boolean).join(" · "))''')
js=rep(js,'''  h("button",{class:"btn",onclick:rescan},"Rescan")));''','''  coverBtn(),h("button",{class:"btn",onclick:rescan},"Rescan")));''')
js=rep(js,'''const games=(await api("library",{})).games;
  const sel=h("select",{"aria-label":"Game"},...games.map(g=>h("option",{value:g.id,selected:S.joinGame===g.id},g.title+" ("+consoleName(g.console)+")")));''','''const lib2=await api("library",{});S.lib=lib2;const games=lib2.games;
  const picker=gamePicker(games);const sel=picker.sel;''')
js=rep(js,'''h("h3",{},"Pick the game you will play"),h("div",{class:"row"},sel),''','''h("h3",{},"Pick the game you will play"),picker.el,''')
js=rep(js,'''     h("tr",{},h("td",{},"Ping to "+r.server_name),h("td",{},r.server.ok?r.server.avg_ms+" ms average ("+r.server.min_ms+"–"+r.server.max_ms+"), jitter "+r.server.jitter_ms+" ms, "+r.server.loss_pct+"% lost":"no answer")),''','''     h("tr",{},h("td",{},"Ping to "+r.server_name),h("td",{},r.server.ok?r.server.avg_ms+" ms average ("+r.server.min_ms+"–"+r.server.max_ms+"), jitter "+r.server.jitter_ms+" ms, "+r.server.loss_pct+"% lost"
       :[r.server_is_local?"Your server is not running, so nothing answered. Start it in Servers.":"That server did not answer.",r.last_good?h("div",{class:"small muted"},"Last answer: "+r.last_good.avg_ms+" ms from "+r.last_good.name+", "+ago(r.last_good.at)+"."):h("div",{class:"small muted"},"It has not answered yet, so there is no earlier result to show.")])),''')
js=rep(js,'''async function viewSaves(m){
 const d=await api("save_folders");''','''async function viewSaves(m){
 const d=await api("save_folders");const B=await api("backups");''')
js=rep(js,'''  h("div",{class:"card",style:"margin-top:12px"},h("table",{},h("thead",{},h("tr",{},h("th",{},"Console"),h("th",{},"Save folder")''','''  backupsCard(B),
  h("div",{class:"card",style:"margin-top:12px"},h("table",{},h("thead",{},h("tr",{},h("th",{},"Console"),h("th",{},"Save folder")''')
# menu: scan this computer
core=core.replace('["Scan this computer",async()=>{nav("engines");}]','["Scan this computer",()=>{nav("engines");setTimeout(()=>runScan().then(v=>{if(v)go()}),250)}]')
exec(open('patches4.py').read())
head='''<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Legacy Player</title>
<style>
'''+css+'''</style>
</head>
<body>
<div class="bg" aria-hidden="true"><div class="orb o1"></div><div class="orb o2"></div>
<svg class="w1" viewBox="0 0 1440 320" preserveAspectRatio="none"><defs><linearGradient id="wg" x1="0" x2="1"><stop offset="0" stop-color="#4f8cff"/><stop offset=".55" stop-color="#7a5cff"/><stop offset="1" stop-color="#3be0a8"/></linearGradient></defs><path d="M0,170 C240,270 480,60 720,160 S1200,270 1440,150 L1440,320 L0,320Z"/></svg>
<svg class="w2" viewBox="0 0 1440 320" preserveAspectRatio="none"><path d="M0,120 C300,40 540,250 800,150 S1230,60 1440,170 L1440,320 L0,320Z"/></svg>
<svg class="w3" viewBox="0 0 1440 320" preserveAspectRatio="none"><path d="M0,200 C260,120 600,300 900,190 S1300,120 1440,210 L1440,320 L0,320Z"/></svg></div>
<div id="busybar"></div>
<div class="chrome">
 <div id="menubar" role="menubar"></div>
 <header>
  <div class="brand" id="brand" tabindex="0" role="button" title="Home"><span id="logomartin"></span><span class="wordmark">Legacy <b>Player</b></span></div>
  <nav id="nav" aria-label="Sections"></nav>
  <div class="grow"></div>
  <button type="button" class="inpill off" id="inpill"><span class="dot"></span><span id="intxt">input…</span></button>
  <button type="button" class="srvpill off" id="srv"><span class="dot"></span><span id="srvtxt">server…</span></button>
 </header>
 <div id="livebar" hidden></div>
</div>
<main id="main"></main>
<div id="toasts" aria-live="polite"></div>
<div id="boot"><div id="bootmartin"></div><div class="muted">Waking Martin<span class="dots"></span></div></div>
<script>
'''
out=head+core+'\n'+js[:js.index('/* ---------- Library ---------- */')]+views+'\n'+js[js.index('/* ---------- Library ---------- */'):]+'</script>\n</body>\n</html>\n'
open('index_new.html','w').write(out)
print(len(out))
