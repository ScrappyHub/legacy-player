"use strict";
const TOKEN="__LP_TOKEN__";
const $=(s,r=document)=>r.querySelector(s);
/* null or false children of replaceChildren would print as the word "null": drop them everywhere */
{const rc=Element.prototype.replaceChildren;Element.prototype.replaceChildren=function(...k){return rc.apply(this,k.flat(3).filter(x=>x!=null&&x!==false))}}
function h(tag,attrs,...kids){const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs||{})){if(k==="class")e.className=v;else if(k.startsWith("on"))e.addEventListener(k.slice(2),v);else if(v===true)e.setAttribute(k,"");else if(v!==false&&v!=null)e.setAttribute(k,v)}
 for(const c of kids.flat()){if(c==null||c===false)continue;e.append(c.nodeType?c:document.createTextNode(String(c)))}return e}
/* A thin shimmer bar at the top and a hopping Martin show the app is working. Quiet background polls do not trigger it. */
let pending=0,busyT=null;const QUIET=new Set(["ping","mp_state","status","scan_pc","server_status","pads","bye","network_last","setup_status","specs","keyboard","home","server_control"]);
async function api(name,body={}){const loud=!QUIET.has(name);if(loud){pending++;if(pending===1)busyT=setTimeout(()=>document.body.classList.add("busy"),200)}
 try{const r=await fetch("/api/"+name,{method:"POST",headers:{"Content-Type":"application/json","X-LP-Token":TOKEN},body:JSON.stringify(body)});
  const j=await r.json();if(!r.ok)throw new Error(j.error||"Request failed");return j}
 finally{if(loud){pending=Math.max(0,pending-1);if(!pending){clearTimeout(busyT);document.body.classList.remove("busy")}}}}
function toast(text,level){const t=h("div",{class:"toast "+(level||"")},text);$("#toasts").append(t);setTimeout(()=>t.remove(),level==="warn"?9000:5000)}
function ask(text,yes){return new Promise(res=>{const done=v=>{ov.remove();res(v)};const ov=h("div",{class:"modal",role:"dialog","aria-modal":"true"},h("div",{class:"modalbox"},h("p",{},text),h("div",{class:"row",style:"justify-content:flex-end;gap:8px"},h("button",{class:"btn",onclick:()=>done(false)},"Cancel"),h("button",{class:"btn primary",onclick:()=>done(true)},yes||"OK"))));document.body.append(ov);ov.querySelector(".primary").focus()})}
async function act(fn,ok){try{const r=await fn();if(ok)toast(ok);return r}catch(e){toast(e.message,"err")}}
function why(text){const box=h("div",{class:"why",hidden:true},text);const b=h("button",{class:"i","aria-label":"What is this?",title:"What is this?",onclick:()=>{box.hidden=!box.hidden}},"i");return[b,box]}
function whyInline(label,text){const[b,box]=why(text);return h("span",{},label,b,box)}
const NETPLAY={strong:"Good fit",["per-game"]:"Needs a game pack","experimental":"Experimental","not-practical":"Not practical yet"};

/* ---------- small helpers ---------- */
function ago(t){if(!t)return"never";const s=Math.max(0,Date.now()/1000-t);if(s<45)return"just now";if(s<3600)return Math.round(s/60)+" min ago";if(s<86400)return Math.round(s/3600)+" h ago";return Math.round(s/86400)+" days ago"}
function fmtBytes(b){if(b==null)return"–";const g=b/1073741824;return g>=1?g.toFixed(g>=10?0:1)+" GB":Math.round(b/1048576)+" MB"}
function svgEl(html){const t=document.createElement("template");t.innerHTML=html.trim();return t.content.firstElementChild}
const EYE='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>';
const EYE_OFF='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 19c-7 0-11-7-11-7a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 7 11 7a18.5 18.5 0 0 1-2.16 3.19M14.12 14.12a3 3 0 1 1-4.24-4.24"/><path d="M1 1l22 22"/></svg>';
/* An address is hidden until the little eye is pressed. The mask has a fixed length so it says nothing about the address. */
function ipSpan(text){if(!text)return h("span",{},"–");let on=false;const v=h("span",{class:"ipv"},"•••.•••.•••.•••");const b=h("button",{class:"eye",type:"button",title:"Show or hide the address","aria-label":"Show or hide the address",onclick:()=>{on=!on;v.textContent=on?text:"•••.•••.•••.•••";b.replaceChildren(svgEl(on?EYE_OFF:EYE))}},svgEl(EYE));return h("span",{class:"ip"},v,b)}

/* ---------- pixel art: Martin and the avatars ---------- */
const PAL={W:"#f6f7fc",G:"#9aa3b8",D:"#3a4058",E:"#14172a",P:"#ff8fb0",R:"#ff5a6a",Y:"#ffd23f",B:"#5b7cff",C:"#4de3ff",S:"#f2c9a0",O:"#ff9f43",N:"#47d36b",K:"#2b3157",L:"#c3b5ff",Z:"#ff8e7a",z:"#ffc2b3",X:"#c24b3a",T:"#2e8f4e"};
function pixels(rows,size,cls){const w=rows[0].length,hh=rows.length;let r="";rows.forEach((row,y)=>{[...row].forEach((c,x)=>{if(c!==".")r+=`<rect ${c==="E"?'class="peye" ':""}x="${x}" y="${y}" width="1" height="1" fill="${PAL[c]}"/>`})});
 return svgEl(`<svg class="px ${cls||""}" viewBox="0 0 ${w} ${hh}" width="${size}" height="${Math.round(size*hh/w)}" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${r}</svg>`)}
/* Martin: a white and grey cat with a tabby M on his forehead */
const MARTIN=["..DD........DD..",".DGGD......DGGD.",".DGWDDDDDDDDWGD.","DWWWWGWWWWGWWWWD","DWWWWGGWWGGWWWWD","DWWWWGWGGWGWWWWD","DWWWEEWWWWEEWWWD","DWWWEEWWWWEEWWWD","DWGWWWWPPWWWWGWD","DWWWWWDWWDWWWWWD",".DWWWWWDDWWWWWD.","..DDWWWWWWWWDD..","....DDDDDDDD...."];
/* A salmon-pink heraldic rose, drawn from a few rules: five rounded petals, a lighter inner ring, a gold seed and green barbs between the petals */
function roseRows(){const n=16,c=7.5,rows=[];
 for(let y=0;y<n;y++){let r="";for(let x=0;x<n;x++){const dx=x-c,dy=y-c,d=Math.hypot(dx,dy),a=Math.atan2(dy,dx)+Math.PI/2;
  const petal=5.3+1.9*Math.cos(5*a),barb=d>5.2&&d<7.7&&Math.cos(5*a)<-0.82;
  let ch=".";if(d<petal)ch=d<2.1?"Y":d<3.6?"X":d<5?"Z":(d<petal-0.9?"Z":"z");if(d<petal&&d>=3.6&&d<4.5)ch="z";if(!(d<petal)&&barb)ch="T";
  if(d<2.1&&d>1.2&&(x+y)%2===0)ch="Y";r+=ch}rows.push(r)}
 const out=rows.map((row,y)=>[...row].map((ch,x)=>{if(ch!==".")return ch;const nb=[[1,0],[-1,0],[0,1],[0,-1]].some(([ox,oy])=>{const rr=rows[y+oy];return rr&&rr[x+ox]&&rr[x+ox]!=="."});return nb?"D":"."}).join(""));return out}
const AVATARS={
 martin:{name:"Martin",rows:MARTIN},
 rose:{name:"Rose",rows:roseRows()},
 heart:{name:"Heart",rows:[".RR..RR.","RRRRRRRR","RRRRRRRR","RRRRRRRR",".RRRRRR.","..RRRR..","...RR...","........"]},
 star:{name:"Star",rows:["...YY...","...YY...","YYYYYYYY",".YYYYYY.","..YYYY..",".YYYYYY.",".YY..YY.","YY....YY"]},
 ghost:{name:"Ghost",rows:["..WWWW..",".WWWWWW.","WWWWWWWW","WEEWWEEW","WWWWWWWW","WWWWWWWW","WWWWWWWW","WW.WW.WW"]},
 robot:{name:"Robot",rows:["...GG...","..GGGG..",".GGGGGG.",".GCGGCG.",".GGGGGG.",".GGRRGG.","..G..G..",".GG..GG."]},
 mushroom:{name:"Mushroom",rows:["..RRRR..",".RWRRWR.","RRRWWRRR","RRRRRRRR","..SSSS..","..SESS..","..SSSS..","..SSSS.."]},
 rocket:{name:"Rocket",rows:["...BB...","..BWWB..","..BWWB..","..BBBB..",".RBBBBR.",".R.BB.R.","...OO...","..O..O.."]},
 alien:{name:"Alien",rows:[".N....N.","..N..N..",".NNNNNN.","NNENNENN","NNNNNNNN",".NNNNNN.",".N.NN.N.","N......N"]},
 controller:{name:"Controller",rows:["........",".GGGGGG.","GGGGGGGG","GWGGGRRG","WWWGGRRG","GWGGGGGG","GG....GG","........"]},
 slime:{name:"Slime",rows:["........","...CC...","..CCCC..",".CCCCCC.","CCECCECC","CCCCCCCC","CCCCCCCC",".CCCCCC."]},
 gem:{name:"Gem",rows:["........",".LLLLLL.","LWLLLLBL","LLLLLLBB",".LLLLBB.","..LLBB..","...LB...","........"]},
 moon:{name:"Moon",rows:["..YYY...",".YYY....","YYY.....","YYY.....","YYY.....",".YYY....","..YYYY..","........"]},
};
function martin(size,cls){return pixels(MARTIN,size,"martin "+(cls||""))}
function avatarEl(id,size,cls){const a=AVATARS[id]||AVATARS.martin;return pixels(a.rows,size,"avatar "+(cls||""))}

const S={tab:"home",console:null,q:"",fav:false,sort:"title",lib:null,settings:null,room:null,online:null,lastNotice:null,profile:null,netcheck:null,netBusy:false};
const PRIMARY=[["home","Home"],["library","Library"],["console","Console mode"],["setup","Setup"],["together","Server Info"],["servers","Servers"]];

function renderNav(){const n=$("#nav");n.replaceChildren(...PRIMARY.map(([id,l])=>h("button",{class:S.tab===id?"on":"",onclick:()=>{S.tab=id;S.anchor=null;go()}},l+(id==="together"&&S.room?" ●":""))));renderWho();renderLive()}
function renderWho(){const w=$("#who");if(!w)return;const p=S.profile||{alias:"Player",avatar:"martin",player:"Player"};
 w.replaceChildren(avatarEl(p.avatar,26),h("span",{class:"nm"},p.player||p.alias))}
async function go(){closeMenus();renderNav();const old=$("#main"),m=old.cloneNode(false);old.replaceWith(m);window.scrollTo(0,0);
 Promise.resolve(({home:viewHome,library:viewLibrary,together:viewTogether,servers:viewServers,console:viewConsole,setup:viewSetup,engines:viewEngines,controllers:viewControllers,saves:viewSaves,emulators:viewEmulators,settings:viewSettings,credits:viewCredits,welcome:viewWelcome,help:viewHelp,storage:viewStorage,profile:viewProfile,display:viewDisplay})[S.tab](m)).then(()=>{if(S.tab==="home")homeArtTip()}).catch(e=>{console.error("page error",e);toast("Something went wrong drawing this page: "+(e&&e.message||e),"err")})}
function nav(tab,anchor){S.tab=tab;S.anchor=anchor||null;go()}

/* ---------- menu bar ---------- */
function menuDefs(){return[
 ["Account",[["Profile and avatar",()=>nav("profile")],["Network",()=>nav("together")],["Settings",()=>nav("settings")],["Check for updates",checkUpdates],"-",["Exit Legacy Player",quitApp]]],
 ["Games",[["Library",()=>nav("library")],["Console mode",()=>nav("console")],["Storage by console",()=>nav("storage")],["Display and video",()=>nav("display")],["Controllers",()=>nav("controllers")],["Saves and backups",()=>nav("saves")],"-",["Rescan my games",()=>rescan()]]],
 ["Online",[...liveMenu(),["Server Info",()=>nav("together")],["Servers",()=>nav("servers")]]],
 ["Tools",[["Doctor's office (Setup)",()=>nav("setup")],["Engines",()=>nav("engines")],["Emulators",()=>nav("emulators")],["Scan this computer",async()=>{nav("engines");}],["Credits",()=>nav("credits")]]],
 ["Help",[["How it works",()=>nav("help")],["How save files work",()=>nav("help","saves")],["Privacy",()=>nav("help","privacy")],["Uninstall Legacy Player...",()=>retireClinic()]]]]}
function closeMenus(){document.querySelectorAll(".menu.open").forEach(x=>x.classList.remove("open"))}
function buildMenubar(){const bar=$("#menubar");
 const menus=menuDefs().map(([name,items])=>{const m=h("div",{class:"menu"},h("button",{type:"button",onclick:e=>{e.stopPropagation();const was=m.classList.contains("open");closeMenus();if(!was)m.classList.add("open")},onmouseenter:()=>{if(document.querySelector(".menu.open")){closeMenus();m.classList.add("open")}}},name),
  h("div",{class:"dd",role:"menu"},...items.map(it=>it==="-"?h("hr"):h("button",{type:"button",role:"menuitem",onclick:()=>{closeMenus();it[1]()}},it[0]))));return m});
 bar.replaceChildren(...menus,h("div",{class:"grow"}),h("button",{class:"who",id:"who",type:"button",title:"Your profile",onclick:()=>nav("profile")}));renderWho()}
document.addEventListener("click",closeMenus);document.addEventListener("keydown",e=>{if(e.key==="Escape")closeMenus()});
async function checkUpdates(){const r=await act(()=>api("check_update"));if(!r)return;
 if(r.newer){if(await ask("Version "+r.latest+" is available (you have "+r.current+"). Open its download page?","Open page"))window.open(r.page,"_blank","noopener")}
 else toast(r.ok?r.message+" You have "+r.current+".":r.message,r.ok?"":"warn")}
async function quitApp(){const busy=S.room||(S.waits&&S.waits.length)||S.running;
 let srv=false;try{srv=!!(await api("server_control",{action:"status"})).running}catch(e){}
 if(await ask(busy?"Quit Legacy Player? You will leave your room"+(S.running?" and your game keeps running in its own window":"")+".":"Quit Legacy Player? To keep it running in the tray instead, just close the window with X.","Quit")){
  if(srv&&await ask("Your server is running for friends. Stop it too? (Press Cancel to leave it running on its own.)","Stop my server"))try{await api("server_control",{action:"stop"})}catch(e){}
  try{await api("quit")}catch(e){}document.title="Legacy Player closed";try{window.close()}catch(e){}document.body.replaceChildren(h("div",{style:"padding:60px;text-align:center"},martin(96),h("p",{},"Legacy Player has closed. You can close this window.")))}}

/* ---------- network test runs by itself so Server Info already knows where you stand ---------- */
async function pollNet(){S.netBusy=true;redrawNet();
 for(let i=0;i<60;i++){const r=await api("network_last").catch(()=>null);if(r){if(r.at)S.netcheck=r;if(!r.running)break}await new Promise(x=>setTimeout(x,800))}
 S.netBusy=false;redrawNet()}
async function runNetTest(){if(S.netBusy)return;await act(()=>api("network_start"));pollNet()}
async function autoNetTest(maxAge){
 if(S.netBusy||!S.settings||!S.settings.auto_network_test)return;
 if(!S.netcheck){const last=await api("network_last").catch(()=>null);if(last&&last.at)S.netcheck=last}
 if(S.netcheck&&S.netcheck.at&&Date.now()/1000-S.netcheck.at<maxAge)return;
 runNetTest()}
function redrawNet(){const b=$("#netbox");if(b)drawNetCheck(b)}

/* ---------- petting Martin ---------- */
const MEOWS=["meow!","purr purr","mrrp?","nya~","*purrrr*","meow meow","mew!","prrrr...","more pets pls","*headbonk*","mrow!","*slow blink*","I love it here","nice to see you","*kneads happily*"];
let pet={el:null,last:0,timer:null,n:0,raf:0};
/* The bubble belongs to the cat that was petted: it follows that cat while it is visible (scrolling, resizing) and goes away by itself. */
function placeBubble(){const b=$("#bubble");if(!b)return;if(!pet.el||!pet.el.isConnected){b.remove();return}
 const r=pet.el.getBoundingClientRect();const off=r.bottom<0||r.top>innerHeight||r.right<0||r.left>innerWidth;b.style.visibility=off?"hidden":"visible";
 const w=b.offsetWidth||90;let left=r.right+8;if(left+w>innerWidth-6)left=Math.max(6,r.left-w-8);
 b.style.left=left+"px";b.style.top=Math.max(6,r.top-26)+"px";pet.raf=requestAnimationFrame(placeBubble)}
function say(text,el){let b=$("#bubble");if(el)pet.el=el;if(!b){b=h("div",{id:"bubble",role:"status"});document.body.append(b)}
 if(!pet.el||!pet.el.isConnected)pet.el=document.querySelector("#logomartin .martin");if(!pet.el)return;
 b.textContent=text;b.style.animation="none";void b.offsetWidth;b.style.animation="";
 cancelAnimationFrame(pet.raf);placeBubble();clearTimeout(pet.timer);pet.timer=setTimeout(()=>{cancelAnimationFrame(pet.raf);const x=$("#bubble");if(x)x.remove()},3200)}
function nextMeow(){let t;do{t=MEOWS[Math.floor(Math.random()*MEOWS.length)]}while(t===pet.text&&MEOWS.length>1);pet.text=t;return t}
/* a bubble only appears right after a pet, never on its own */
document.addEventListener("click",e=>{const m=e.target.closest&&e.target.closest(".martin");if(!m||m.closest("#boot"))return;
 pet.el=m;pet.last=Date.now();pet.n++;m.classList.remove("pet");void m.getBoundingClientRect();m.classList.add("pet");
 const r=m.getBoundingClientRect();const hrt=pixels(AVATARS.heart.rows,18,"");hrt.classList.add("petheart");hrt.style.left=(r.left+r.width/2-9+(Math.random()*30-15))+"px";hrt.style.top=(r.top+4)+"px";document.body.append(hrt);setTimeout(()=>hrt.remove(),1000);
 say(pet.n%7===0?"you're the best!":nextMeow())});

/* Poking the doctor on the Home page: he answers in a bubble, and gets more tired the more you poke (resets after a while) */
const POKES=["Ow! I'm a doctor, not a pin cushion.","Careful, these hands are insured.","Say ahh!","Your pixels look healthy.","Have you tried staying home and playing video games?","Appointments are in the Setup tab, you know.","Hmm. Your high score is in perfect health."];
const POKES_TIRED=["Okay, okay, I'm awake!","Please stop poking the doctor.","I'm writing you a prescription for patience.","My clipboard is getting dizzy.","...Is this a bit?"];
const poke={n:0,t:0,last:""};
document.addEventListener("click",e=>{const d=e.target.closest&&e.target.closest(".px.doctor");if(!d||d.closest(".docspot,#boot,.modal"))return;
 const now=Date.now();if(now-poke.t>10000)poke.n=0;poke.t=now;poke.n++;
 d.classList.remove("poked");void d.getBoundingClientRect();d.classList.add("poked");
 const pool=poke.n>=5?POKES_TIRED:POKES;let t;do{t=pool[Math.floor(Math.random()*pool.length)]}while(t===poke.last&&pool.length>1);poke.last=t;
 const r=d.getBoundingClientRect();const cr=pixels(CROSS,16,"");cr.classList.add("petheart");cr.style.left=(r.left+r.width/2-8+(Math.random()*30-15))+"px";cr.style.top=(r.top+4)+"px";document.body.append(cr);setTimeout(()=>cr.remove(),1000);
 say(t,d)});

/* Martin is the app's icon too (tab, window, tray and program file); the rose belongs to the Featured card */
{const l=document.createElement("link");l.rel="icon";const rows=MARTIN;let r="";rows.forEach((row,y)=>[...row].forEach((c,x)=>{if(c!==".")r+=`<rect x="${x}" y="${y}" width="1" height="1" fill="${PAL[c]}"/>`}));
 l.href="data:image/svg+xml,"+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -1.5 16 16" shape-rendering="crispEdges">${r}</svg>`);document.head.append(l)}
