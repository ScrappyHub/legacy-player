/* ---------- Home ---------- */
async function viewHome(m){
 const d=await api("home");const last=await api("network_last").catch(()=>({at:null}));if(last.at&&!S.netcheck)S.netcheck=last;
 S.profile=S.profile||await api("profile");
 const resume=d.recent[0];
 const cta=[resume?h("button",{class:"btn primary",onclick:()=>openGame(resume.id)},"Continue: "+resume.title):null,
  h("button",{class:"btn "+(resume?"":"primary"),onclick:()=>nav("library")},"Browse my games")];
 const code=h("input",{type:"text",placeholder:"Enter a code to play together","aria-label":"Server or invite code",style:"width:min(250px,100%)",onkeydown:e=>{if(e.key==="Enter")go1.click()}});
 const go1=h("button",{class:"btn good",onclick:()=>getStarted(code.value,joinBox)},"Get started");
 const joinBox=h("div",{class:"joinbox"});
 const dr=await api("doctor");
 m.append(h("div",{class:"hero"},martin(150),h("div",{class:"grow"},
   h("h1",{},"Welcome back, "+d.alias),
   h("p",{},d.games_total?d.games_total+" games, "+d.consoles_ready+" of "+d.consoles_total+" consoles ready to play.":"Point me at your games folder and I'll line everything up."),
   h("div",{class:"row",style:"margin-top:12px"},...cta),h("div",{class:"row",style:"margin-top:8px"},code,go1),
   h("div",{class:"pstat"},
    h("span",{class:"badge "+(S.online||S.room?"good":"")},S.room?"● in a room: "+S.room.game:(S.online?"● server online":"○ server offline")),
    h("span",{class:"badge"},"network tested "+(S.netBusy?"now…":ago(S.netcheck&&S.netcheck.at))),
    h("span",{class:"badge"},"version "+d.version))),doctorDoor(dr)));
 m.append(joinBox);
 const cards=[["One home for every console","NES to PS3 in a single place. Legacy Player opens the right emulator for each game, the way a console picks the right disc.","#3b6bff","#7a5cff",AVATARS.controller],
  ["Your games stay yours","It only reads your folders. Nothing is copied or sent anywhere, no games or BIOS files are included, and a game is only removed when you choose Uninstall and confirm.","#0aa57a","#2bd1b0",AVATARS.gem],
  ["Play together, privately","Run a small server on your own computer, share a short code and play in a room. Other players never see your address.","#d9468f","#ff8a5c",AVATARS.rocket],
  ["Made to feel like a console","Plug in a pad, map it once and drive everything from the couch in Console mode. Your saves are backed up for you.","#7b4dff","#4fc3ff",AVATARS.star]];
 m.append(h("h3",{},"What Legacy Player is"),h("div",{class:"flashes"},...cards.map(([t,x,a,b,av])=>h("div",{class:"flash",style:`--c1:${a};--c2:${b}`},pixels(av.rows,40),h("h3",{},t),h("p",{},x)))));
 const shelf=(title,list,empty)=>h("div",{},h("h3",{},title),list.length?h("div",{class:"shelf"},...list.map(g=>card(g))):h("p",{class:"muted small"},empty));
 S.lib=S.lib||await api("library",{});
 m.append(shelf("Recent games",d.recent,"Play something and it shows up here."));
 if(d.favorites.length)m.append(shelf("Favorites",d.favorites,""));
 m.append(h("div",{class:"card",style:"margin-top:10px"},h("div",{class:"row"},h("h3",{class:"grow",style:"margin:0"},"Your emulators"),
   h("button",{class:"btn",onclick:()=>nav("emulators")},"Manage"),h("button",{class:"btn primary",onclick:()=>{nav("engines")}},"Find more")),
  h("div",{class:"chips"},...(d.emulators.length?d.emulators.map(e=>h("span",{class:"chip",title:e.path,onclick:()=>nav("emulators")},"✓ "+e.name)):[h("span",{class:"muted small"},"None found yet. Open Engines and scan this computer.")]))));
 const f=d.featured;
 m.append(f?h("div",{class:"card featured",style:"margin-top:14px"},h("div",{class:"row"},pixels(AVATARS.rose.rows,36),h("span",{class:"tag"},"Featured"),h("h3",{class:"grow",style:"margin:0"},f.title),f.link?h("a",{class:"btn",href:f.link,target:"_blank",rel:"noopener noreferrer"},"Open"):null),f.text?h("p",{},f.text):null,
   h("p",{class:"small muted"},"Chosen by whoever set up this copy of Legacy Player. It is not an ad and nothing is paid for it."))
  :h("div",{class:"card featured",style:"margin-top:14px"},h("div",{class:"row"},h("span",{class:"tag"},"Featured"),h("b",{class:"grow"},"Your featured spot"),h("button",{class:"btn",onclick:()=>nav("settings")},"Set it up")),
   h("p",{class:"small muted"},"Put a game night, a friend's server or a link here. Set the title, text and link under Settings > Home page.")));
}

/* ---------- Get started: a server code connects, then you see what you would be joining ---------- */
async function getStarted(raw,box){
 const v=(raw||"").trim();
 if(!v){toast("Paste a server code (LP-…) or a room invite code first","warn");return}
 if(/^LP-/i.test(v)){
  const r=await act(()=>api("server_connect",{code:v}));if(!r)return;
  if(!r.connected){toast(r.message,"warn");return}
  toast("Connected to the server");S.onlineSeen=false;pingServer();autoNetTest(0);showJoin(box);return}
 if(/^[A-Za-z0-9]{5}-[A-Za-z0-9]{5}$/.test(v)){S.joinCode=v.toUpperCase();nav("together");return}
 toast("That does not look like a server code (starts with LP-) or an invite code (like ABCDE-FGH12).","warn")}
async function showJoin(box){
 const d=await act(()=>api("mp_browse"));if(!d)return;
 const state=s=>s==="active"?"In a match":s==="completed"||s==="failed"?"Finished":"In the lobby";
 box.replaceChildren(h("div",{class:"card",style:"margin-top:14px"},h("div",{class:"row"},martin(36),h("h3",{class:"grow",style:"margin:0"},"Found the server. Here is what is happening on it."),h("button",{class:"btn",onclick:()=>showJoin(box)},"Refresh")),
  d.rooms.length?h("table",{},h("thead",{},h("tr",{},...["Game","Console","Region","Emulator","Players","Waiting","Status",""].map(t=>h("th",{},t)))),
   h("tbody",{},...d.rooms.map(r=>h("tr",{},h("td",{},h("b",{},r.title),r.label?h("div",{class:"small muted"},r.label):null),h("td",{},r.console_name),h("td",{},r.region||"–"),
    h("td",{class:r.emulator?"":"warn"},r.emulator||(r.you_have_it?"none set":"you do not have this game")),
    h("td",{class:r.full?"warn":"good"},r.players+" / "+r.max_players),h("td",{},String(r.waiting)),h("td",{},state(r.state)),
    h("td",{},r.you_have_it?h("button",{class:"btn good",onclick:async()=>{const x=await act(()=>api("mp_join",{id:r.local_game_id,session_id:r.session_id,background:r.full}),r.full?"You are in line":"");if(x){S.room=x.room;S.waits=x.waits||[];nav("together");poll()}}},r.full?"Wait in line":"Join"):null)))))
  :h("p",{class:"muted"},"No public rooms right now. If your host gave you an invite code, enter it here."),
  h("p",{class:"small muted"},"Rooms show the game and how full they are, never who is inside. Private rooms need the host's invite code.")))}

/* ---------- Doc: checks that everything is in place ---------- */
const DOC_BASE=[".....KKKKKK.....","....KKKKKKKK....","....KSSSSSSK....","....SSSSSSSS....","....SEESSEES....","....SSSSSSSS....","....SDSSSSDS....",".....SDDDDS.....","...WWWWWWWWWW...","..WWGWWWWWWGWW..","..WWGWWWWWWGRW..","..WWWGGGGGWRRR..","..WWWWWWWWWWRW..","..WWWWWWWWWWWW..","...WWWWWWWWWW...","....KK....KK...."];
function doctorRows(mood){const r=DOC_BASE.slice();
 if(mood==="sigh"){r[4]="....SKKSSKKS.C..";r[5]="....SDDSSDDS....";r[6]="....SSDDDDSS....";r[7]=".....SSSSSS.....";}
 if(mood==="eyeroll"){r[3]="....SEESSEES....";r[4]="....SSSSSSSS....";r[5]="....SSSSSSSS....";r[6]="....SSDDDDSS....";r[7]=".....SSSSSS.....";}
 if(mood==="facepalm"){r[3]="...SSSSSSSSSS...";r[4]="...SSDSSSSDSS..";r[5]="...SSSSSSSSSS...";r[6]="....SSDDDDSS....";r[7]=".....SDDDDS.....";}
 if(mood==="rub"){r[3]="..S.SSSSSSSS.S..";r[4]="..S.SKKSSKKS.S..";r[5]="..S.SSSSSSSS.S..";r[6]="....SDSDSDSS....";r[7]=".....SSSSSS.....";}
 if(mood==="yawn"){r[4]="....SKKSSKKS....";r[5]="....SSSSSSSS....";r[6]="....SDEEEEDS....";r[7]=".....DEEEED.....";}
 if(mood==="drum"){r[3]="....SDDSSDDS....";r[4]="....SSESSESS....";r[6]="....SSDDDDSS....";r[7]=".....SSSSSS.....";}
 if(mood==="glare"){r[3]="....DDSSSSDD....";r[4]="....SEESSEES....";r[6]="....SDDDDDDS....";r[7]=".....DSSSSD.....";}
 if(mood==="suspicious"){r[3]="....SDDSSSSS....";r[4]="....SKKSSEES....";r[6]="....SSSSSDDS....";r[7]=".....SSSDDS.....";}
 if(mood==="happy"){r[2]="....KSSSSSSK.Y..";r[3]="....SSSSSSSS....";r[5]="Y...SSSSSSSS....";r[6]="....SDSSSSDS....";r[7]=".....SDDDDS.....";r[6]="....SDDDDDDS....";r[7]=".....SDDDDS.....";}
 if(mood==="worried"){r[3]="....SDDSSDDS.C..";r[6]="....SSDDDDSS....";r[7]=".....SDSSDS.....";r[4]="....SEESSEES.C..";}
 if(mood==="sad"){r[3]="....SSDSSDSS....";r[6]="....SSSDDSSS....";r[7]=".....SSSSSS.....";r[5]="....SSSSSSSS....";}
 return r}
async function scanEverything(refresh){
 if(!await ask("Scan everything? I will read your games folders again, make the save folders, and look through this computer for emulators and BIOS files. It reads names only, changes nothing, sends nothing and uses no internet.","Scan everything"))return;
 docWork(true,"scan");try{await act(()=>api("scan_everything"));await runScan(true)}finally{docWork(false)}refresh()}
function doctorSay(dr){const cheers=["Let's play!","Ready, player one!","Game on!","So many games!","Press start!","Pick something!"];
 return{happy:cheers[Math.floor(Date.now()/60000)%cheers.length],worried:"Almost there! A few things to sort.",sad:dr.games?"Let's find you an emulator!":"Show me your games!"}[dr.mood]}
/* Home shows only the doctor's door; the doctor himself lives in his office on the Setup page */
function doctorDoor(dr){const n=dr.issues.filter(i=>!i.dismissed).length;
 return h("div",{class:"doc door"},h("div",{class:"row",style:"align-items:center;flex-wrap:nowrap;gap:14px"},pixels(doctorRows(dr.mood),104,"doctor "+dr.mood),
  h("div",{style:"flex:1;min-width:0"},h("div",{class:"retro"},h("div",{class:"hd"},doctorSay(dr)),h("div",{class:n?"w":""},"Check-up: "+(n?n+" thing"+(n>1?"s":"")+" to look at":"all clear")),h("div",{},"PC scanned: "+ago(dr.last_scan))),
   h("button",{class:"btn primary",style:"margin:10px 3px 0;width:calc(100% - 6px)",onclick:()=>{S.autoVisit=true;nav("setup")}},"Visit the doctor's office"))))}
function doctorCard(dr,opts){opts=opts||{};
 const box=h("div",{class:"doc"+(opts.office?" inoffice":"")});
 const refresh=async()=>{const x=await api("doctor");S.doc=x;draw(x)};
 const draw=dr=>{
  const active=dr.issues.filter(i=>!i.dismissed),quiet=dr.issues.filter(i=>i.dismissed);
  const L=(a,b,warn)=>h("div",{class:warn?"w":""},a+": "+b);
  const report=h("div",{style:"flex:1;min-width:0"},h("div",{class:"retro"},h("div",{class:"hd"},doctorSay(dr)),
    L("Games",dr.games+" read "+ago(dr.last_rescan),!dr.games),L("Emulators",dr.emulators.length+" found",!dr.emulators.length),L("Consoles",dr.consoles_ready+"/"+dr.consoles_total+" ready"),
    L("Saves",dr.saves_ready?"folders ready":"not made yet",!dr.saves_ready),L("BIOS",dr.bios_needed?dr.bios_have+"/"+dr.bios_needed+" found":"none needed yet"),
    L("PC scanned",ago(dr.last_scan),!dr.last_scan)),
    h("button",{class:"btn primary",style:"margin:10px 3px 0;width:calc(100% - 6px)",onclick:()=>scanEverything(refresh)},"Scan everything"));
  box.replaceChildren(h("div",{class:"row",style:"align-items:center;flex-wrap:nowrap;gap:14px"},opts.office?null:pixels(doctorRows(dr.mood),104,"doctor "+dr.mood),report),
   ...(opts.noWorries?[]:active).map(i=>h("div",{class:"worry"},h("span",{class:"grow"},i.text),
    i.kind==="core"?h("button",{class:"btn",onclick:()=>{const el=$("#supplies");if(el)el.scrollIntoView({behavior:"smooth"})}},"Fix"):(i.kind==="emulator"||i.kind==="bios")?h("button",{class:"btn",onclick:()=>nav("engines")},"Fix"):null,
    h("button",{class:"btn",title:"I do not want to install that. Stop worrying about it.",onclick:async()=>{await act(()=>api("doctor_dismiss",{key:i.key}));refresh()}},"I don't need it"))),
   quiet.length&&!opts.noWorries?h("div",{class:"small muted",style:"margin-top:6px"},quiet.length+" worr"+(quiet.length>1?"ies":"y")+" set aside. ",h("a",{href:"#",onclick:async e=>{e.preventDefault();for(const q of quiet)await api("doctor_dismiss",{key:q.key,undo:true});refresh()}},"Bring back")):null);
  if(opts.onDraw)opts.onDraw(dr)};
 draw(dr);return box}

/* ---------- Storage by console ---------- */
async function viewStorage(m){
 const d=await api("storage");const max=Math.max(1,...d.consoles.map(c=>c.bytes));
 m.append(h("h2",{},"Storage by console"),h("div",{class:"why"},"How much space the games in your library folders take, console by console. Legacy Player only measures the files; it only removes a game if you choose Uninstall."),
  h("div",{class:"card"},h("div",{class:"row"},h("h3",{class:"grow",style:"margin:0"},fmtBytes(d.total_bytes)+" across "+d.total_games+" games"),d.free_bytes!=null?h("span",{class:"badge"},fmtBytes(d.free_bytes)+" free on that drive"):null),
   d.consoles.length?h("table",{style:"margin-top:10px"},h("thead",{},h("tr",{},h("th",{},"Console"),h("th",{},"Games"),h("th",{style:"width:45%"},"Size"),h("th",{},""))),
    h("tbody",{},...d.consoles.map(c=>h("tr",{},h("td",{},c.name),h("td",{},String(c.count)),h("td",{},h("div",{class:"bar"},h("i",{style:"width:"+Math.max(2,Math.round(c.bytes/max*100))+"%"}))),h("td",{},h("b",{},fmtBytes(c.bytes)))))))
   :h("p",{class:"muted"},"No games yet. Add a games folder in Library."))) }

/* ---------- Profile ---------- */
async function viewProfile(m){
 const p=S.profile=await api("profile");let pick=p.avatar;
 const name=h("input",{type:"text",value:p.alias,maxlength:24,"aria-label":"Your name",style:"width:240px"});
 const grid=h("div",{class:"avatars"});
 const draw=()=>grid.replaceChildren(...Object.entries(AVATARS).map(([id,a])=>h("button",{type:"button",class:pick===id?"on":"",title:a.name,onclick:()=>{pick=id;draw()}},avatarEl(id,56))));draw();
 m.append(h("h2",{},"Your profile"),
  h("div",{class:"why"},"This is how other players see you in a room: your name and a four-character tag, like an old console gamertag. The tag is given by the server you connect to, so nobody who is active there shares your name and tag. It says nothing about you or your computer."),
  h("div",{class:"card"},h("div",{class:"row"},avatarEl(pick,72),h("div",{},h("div",{class:"small muted"},"You appear as"),h("b",{style:"font-size:1.3rem"},p.player))),
   h("h3",{},"Name"),h("div",{class:"row"},name),h("h3",{},"Picture"),grid,
   h("div",{class:"row",style:"margin-top:8px"},h("button",{class:"btn primary",onclick:async()=>{const r=await act(()=>api("profile",{alias:name.value.trim(),avatar:pick}),"Saved");if(r){S.profile=r;renderWho();go()}}},"Save"),
    h("button",{class:"btn",onclick:async()=>{const r=await act(()=>api("profile",{claim:true}));if(r){S.profile=r;toast(r.claimed?"Your tag is "+r.player:r.note,r.claimed?"":"warn");renderWho();go()}}},"Ask my server for my tag")),
   p.note?h("p",{class:"small muted"},p.note):null))}

/* ---------- First-run: scan everything once, then you are set ---------- */
function scanPanel(onDone){
 const box=h("div",{});let timer=null;
 const draw=v=>{
  const found=Object.entries(v.emulators||{}),pk=Object.entries(v.packages||{});
  const running=v.state==="running";
  box.replaceChildren(
   running?h("div",{},h("div",{class:"row"},martin(48,"hop"),h("div",{class:"grow"},h("b",{},"Looking around your computer",h("span",{class:"dots"})),h("div",{class:"small muted"},v.visited+" folders checked"+(v.where?" · "+v.where.slice(-60):""))),h("button",{class:"btn",onclick:()=>api("scan_pc",{action:"cancel"})},"Stop")),h("div",{class:"bar live",style:"margin-top:10px"},h("i"))):null,
   (v.state==="done"||v.state==="stopped")?h("div",{},h("p",{class:"good"},"✓ "+(v.state==="stopped"?"Stopped early. ":"Finished. ")+(found.length?found.length+" emulator program"+(found.length>1?"s":"")+" found: "+found.map(([,e])=>e.name).join(", ")+".":"No emulator programs found yet.")),
    pk.length?h("p",{class:"small warn"},"Found downloads that are not unpacked yet: "+pk.map(([,e])=>e.name+" ("+e.paths[0]+")").join("; ")+". Extract them, then add that folder under Emulators."):null):null,
   v.state==="error"?h("p",{class:"bad small"},"The scan stopped: "+v.where):null);
  if(!running&&timer){clearInterval(timer);timer=null;finish(v)}};
 const finish=async v=>{await act(()=>api("scan_apply",{}));onDone&&onDone(v)};
 const start=h("button",{class:"btn primary",onclick:async()=>{
   if(!await ask("Scan this computer? It reads folder and file names only: program names like Dolphin.exe and BIOS files in the usual places. It changes nothing, sends nothing and does not use the internet.","Scan"))return;
   const v=await act(()=>api("scan_pc",{action:"start",consent:true}));if(!v)return;start.disabled=true;draw(v);timer=setInterval(async()=>{draw(await api("scan_pc",{}).catch(()=>({state:"error",where:"lost the app"})))},900)}},"Scan my computer");
 return h("div",{},h("div",{class:"row"},start),box)}
async function viewWelcome(m){
 const st=S.settings||{};let step=S.wizStep||0;const box=h("div",{});
 S.profile=S.profile||await api("profile");let pick=S.profile.avatar||"martin";
 const steps=["Meet Martin","Your games","Scan my computer","Privacy","All set"];
 const fin=async()=>{await api("settings",{key:"setup_done",value:true});S.wizStep=0;S.tab="home";go()};
 const nav2=(back,next,label)=>h("div",{class:"row",style:"margin-top:16px"},back?h("button",{class:"btn",onclick:()=>{S.wizStep=step-1;go()}},"Back"):null,h("button",{class:"btn primary",onclick:next},label||"Next"),step<4?h("button",{class:"btn",onclick:fin},"Skip setup"):null);
 m.append(h("h2",{},"Welcome to Legacy Player"),box);
 const render=async()=>{
  box.replaceChildren(h("div",{class:"wizsteps"},...steps.map((t,i)=>h("span",{class:"chip"+(i===step?" on":"")},(i+1)+". "+t))));
  if(step===0){const name=h("input",{type:"text",value:S.profile.alias==="Player"?"":S.profile.alias,placeholder:"Pick a name",maxlength:24,style:"width:240px"});const grid=h("div",{class:"avatars"});
   const draw=()=>grid.replaceChildren(...Object.entries(AVATARS).map(([id,a])=>h("button",{type:"button",class:pick===id?"on":"",title:a.name,onclick:()=>{pick=id;draw()}},avatarEl(id,48))));draw();
   box.append(h("div",{class:"hero",style:"margin-bottom:14px"},martin(110),h("div",{},h("h1",{},"Hi, I'm Martin."),h("p",{},"I'll get you set up in about a minute: pick who you are, tell me where your games live, and I'll look around for the emulators."))),
    h("div",{class:"card"},h("h3",{},"Who are you?"),h("div",{class:"row"},name),
     h("p",{class:"small muted"},"Other players see your name with a four-character tag, like #4821. The server you connect to gives the tag, and nobody active on it shares your name and tag."),h("h3",{},"Pick a picture"),grid,
     nav2(false,async()=>{const v=name.value.trim();if(!v){toast("Pick a name first","warn");return}const r=await act(()=>api("profile",{alias:v,avatar:pick}));if(!r)return;S.profile=r;renderWho();S.wizStep=1;go()})))}
  else if(step===1){const roots=await api("roots");const inp=h("input",{type:"text",placeholder:"P:\\Vimm",value:(roots.roots||[])[0]||"",style:"min-width:min(480px,100%)"});
   box.append(h("div",{class:"card"},h("h3",{},"Where are your games?"),h("p",{class:"small muted"},"Paste the folder that holds your game files, sorted into folders like NES, SNES, PS2. Legacy Player only reads it; nothing is moved or renamed."),
    h("div",{class:"row"},inp),nav2(true,async()=>{const v=inp.value.trim();if(v){const cur=roots.roots||[];const r=await act(()=>api("roots",{roots:cur.includes(v)?cur:cur.concat([v])}));if(!r)return;const sc=await act(()=>api("rescan"));if(sc)toast("Found "+sc.games+" games")}S.wizStep=2;go()})))}
  else if(step===2){let done=false;
   box.append(h("div",{class:"card"},h("h3",{},"Let me look around"),h("p",{class:"small muted"},"One scan finds your emulators and the BIOS files you already have, so you don't have to point at each one. It only reads names, stays on this computer and uses no internet."),
    scanPanel(()=>{done=true;toast("Scan finished. Everything it found is in use.");}),nav2(true,()=>{S.wizStep=3;go()},"Next")))}
  else if(step===3){const allow=h("input",{type:"checkbox",checked:!!st.allow_internet}),auto=h("input",{type:"checkbox",checked:st.auto_network_test!==false});
   box.append(h("div",{class:"card"},h("h3",{},"Privacy and downloads"),
    h("p",{class:"small"},"Legacy Player never sends anything about you, your computer or your games anywhere. Multiplayer talks only to the server address you choose; other players see your name and tag and nothing else."),
    h("p",{},h("label",{class:"small"},allow," Allow internet downloads (engines from official project releases, RetroArch cores from libretro, update checks). Each download still asks you first.")),
    h("p",{},h("label",{class:"small"},auto," Test my network when Legacy Player opens, so I can tell you if you should host or join. Only this computer and your chosen server are contacted.")),
    h("p",{class:"small muted"},"BIOS files for PS1/PS2/Xbox/DS are never downloaded: they belong to the console makers. I use the copies you dumped from your own consoles."),
    nav2(true,async()=>{await act(()=>api("settings",{key:"allow_internet",value:allow.checked}));const r=await act(()=>api("settings",{key:"auto_network_test",value:auto.checked}));if(r)S.settings=r.values;S.wizStep=4;go()})))}
  else{const hm=await api("home");const en=await api("engines");const bios=en.bios.reduce((n,b)=>n+(b.found.length?1:0),0);const p=await api("profile",{claim:true});S.profile=p;renderWho();
   box.append(h("div",{class:"hero"},martin(120,"cheer"),h("div",{},h("h1",{},"You're good to go."),h("p",{},"Everything is locked in. Here is what I found:"))),
    h("div",{class:"card",style:"margin-top:14px"},
     h("div",{class:"sumrow"},h("span",{},"You are"),h("b",{},p.player)),
     h("div",{class:"sumrow"},h("span",{},"Games in your library"),h("b",{},String(hm.games_total))),
     h("div",{class:"sumrow"},h("span",{},"Consoles ready to play"),h("b",{},hm.consoles_ready+" of "+hm.consoles_total)),
     h("div",{class:"sumrow"},h("span",{},"Emulators"),h("b",{},hm.emulators.length?hm.emulators.map(e=>e.name).join(", "):"none yet")),
     h("div",{class:"sumrow"},h("span",{},"BIOS sets found"),h("b",{},bios+" of "+en.bios.length)),
     p.claimed?null:h("p",{class:"small muted",style:"margin-top:10px"},p.note),
     h("div",{class:"row",style:"margin-top:16px"},h("button",{class:"btn primary",onclick:fin},"Enter Legacy Player"))))}
 };render()}

/* ---------- Help ---------- */
function viewHelp(m){
 const sec=(id,t,...p)=>h("div",{class:"card",id:"h-"+id,style:"margin-bottom:12px"},h("h3",{style:"margin-top:0"},t),...p.map(x=>h("p",{},x)));
 m.append(h("h2",{},"Help"),
  sec("games","Your games stay yours","Legacy Player scans your games folder by file type and folder name. It lists files; it never opens, copies, or changes them, and it only removes a game when you choose Uninstall and confirm, and it ships no games, BIOS, or firmware."),
  sec("playing","Playing","Pressing Play starts the emulator you chose for that console with your game. Emulators are separate programs; Legacy Player opens and organizes them. Console mode shows the same library in a big-screen layout you can drive with a pad."),
  sec("saves","How save files work",
   "A game's progress lives in a save file, and a quick snapshot of the exact moment is a save state. They are written by the emulator, not by Legacy Player, so where they end up depends on the emulator.",
   "For RetroArch consoles Legacy Player gives every console its own tidy folder (saves and save states) under one root and passes it to RetroArch each time it launches. Look at Saves to see the folders or move the root, for example into a OneDrive or Dropbox folder if you want them synced.",
   "Other emulators keep their own folders. Under Saves you can point each console at the folder its emulator uses, and backups will copy from there. PS1, PS2 and GameCube use a memory card file that is shared by many games, so one backup holds all of them.",
   "A backup is a plain timestamped copy kept in the Legacy Player data folder. Restoring first backs up whatever is there now, so restoring can never cost you progress. Nothing is ever overwritten without a backup, and game files are never touched."),
  sec("together","Playing together (technical)","A coordination server runs on Windows, Linux, or a Raspberry Pi. Each player's emulator sends button presses; the server releases a frame only when every player's input has arrived (lockstep), and players compare state checksums to detect desync. This only works when the emulator is deterministic, so support is tiered per console and per game."),
  sec("codes","Server codes, invite codes and names","A server code (LP-...) gets a friend to your server. A room invite code lets them into one room. Both expire or can be revoked. Your name comes with a four-character tag from the server so nobody active there shares it. The server stores only hashes of codes. Traffic is encrypted when the server runs with TLS, which internet hosting requires."),
  sec("notify","Notifications","You are told when someone asks to join, joins, leaves, disconnects, is removed by the host, or when the server restarts. A removed player sees the host's reason."),
  sec("server","Starting and stopping the server","Use Servers: Start, Restart and Stop. From a terminal, python -m server.cli start --detach, stop, restart, and status work the same everywhere. Stopping saves rooms; starting resumes them. A match in progress returns to the ready step so everyone re-syncs."),
  sec("match","Starting a match","NES, SNES, Game Boy, GBA, Genesis and Atari start through RetroArch netplay. GameCube and Wii open Dolphin and guide you through its NetPlay window with the room address filled in. Other consoles have rooms and invites but no match launcher yet."),
  sec("privacy","Privacy","Legacy Player never sends anything about you, your computer or your games anywhere. Addresses are hidden behind a little eye until you press it. Matches go through the server relay by default so players never learn each other's address. Scans read names only. Downloads and update checks happen only when you press a button and have allowed internet access in Settings."));
 if(S.anchor){const el=$("#h-"+S.anchor);if(el)setTimeout(()=>el.scrollIntoView({behavior:"smooth",block:"start"}),60)}
}
