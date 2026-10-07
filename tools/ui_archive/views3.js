/* ================= right-click menu, game properties, custom covers ================= */
const GAMES={};
function allowNet(){return !!(S.settings&&S.settings.allow_internet)}
function closeCtx(){document.querySelectorAll(".ctx").forEach(x=>x.remove())}
function ctxMenu(x,y,items){closeCtx();
 const build=list=>h("div",{class:"ctxlist",role:"menu"},...list.filter(Boolean).map(it=>{
  if(it==="-")return h("hr");
  const b=h("button",{type:"button",role:"menuitem",class:(it.bold?"bold ":"")+(it.sub?"hassub":""),disabled:!!it.disabled,title:it.title||""},
   h("span",{class:"ck"},it.check?"✓":""),h("span",{class:"lb"},it.label),it.sub?h("span",{class:"arr"},"▸"):null);
  if(it.sub){const sub=h("div",{class:"ctxsub"},build(it.sub));const wrap=h("div",{class:"ctxitem"},b,sub);
   const fit=()=>requestAnimationFrame(()=>{sub.style.top="-6px";const r=sub.getBoundingClientRect();if(r.bottom>innerHeight-6)sub.style.top=(-6-(r.bottom-innerHeight+6))+"px"});
   wrap.addEventListener("mouseenter",fit);b.addEventListener("click",e=>{e.stopPropagation();wrap.classList.toggle("open");fit()});return wrap}
  b.addEventListener("click",e=>{e.stopPropagation();closeCtx();it.fn&&it.fn()});return h("div",{class:"ctxitem"},b)}));
 const m=h("div",{class:"ctx"},build(items));document.body.append(m);
 const r=m.getBoundingClientRect();m.style.left=Math.max(6,Math.min(x,innerWidth-r.width-6))+"px";m.style.top=Math.max(6,Math.min(y,innerHeight-r.height-6))+"px";
 if(x+r.width*2>innerWidth)m.classList.add("flip");
 const first=m.querySelector("button:not([disabled])");if(first)first.focus({preventScroll:true})}
document.addEventListener("click",closeCtx);document.addEventListener("scroll",closeCtx,true);window.addEventListener("resize",closeCtx);
document.addEventListener("keydown",e=>{const m=document.querySelector(".ctx");if(!m)return;
 if(e.key==="Escape"){closeCtx();return}
 if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();const bs=[...(document.activeElement&&document.activeElement.closest(".ctxlist")||m).querySelectorAll(":scope > .ctxitem > button:not([disabled])")];if(!bs.length)return;
  let i=bs.indexOf(document.activeElement);i=e.key==="ArrowDown"?(i+1)%bs.length:(i-1+bs.length)%bs.length;bs[i].focus()}
 if(e.key==="ArrowRight"&&document.activeElement&&document.activeElement.classList.contains("hassub")){e.preventDefault();const w=document.activeElement.parentElement;w.classList.add("open");const s=w.querySelector(".ctxsub button:not([disabled])");if(s)s.focus()}
 if(e.key==="ArrowLeft"){const sub=document.activeElement&&document.activeElement.closest(".ctxsub");if(sub){e.preventDefault();sub.parentElement.classList.remove("open");sub.parentElement.querySelector(":scope > button").focus()}}});

document.addEventListener("contextmenu",e=>{const el=e.target.closest&&e.target.closest("[data-gid]");if(!el)return;const g=GAMES[el.dataset.gid];if(!g)return;e.preventDefault();
 let x=e.clientX,y=e.clientY;if(!x&&!y){const r=el.getBoundingClientRect();x=r.left+20;y=r.top+20}gameMenu(g,x,y)});
/* dropping a picture on a game sets its cover */
document.addEventListener("dragover",e=>{if(e.target.closest&&e.target.closest("[data-gid]")&&[...(e.dataTransfer&&e.dataTransfer.types||[])].includes("Files"))e.preventDefault()});
document.addEventListener("drop",e=>{const el=e.target.closest&&e.target.closest("[data-gid]");if(!el)return;const f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(!f||!/^image\//.test(f.type))return;e.preventDefault();setCoverFile(GAMES[el.dataset.gid],f)});

function coverEl(g,cls){GAMES[g.id]=g;
 if(g.cover)return h("img",{class:"cv "+(cls||""),src:"/cover/"+encodeURIComponent(g.id)+".png?t="+encodeURIComponent(TOKEN)+"&v="+(g.cover_v||0),alt:"",loading:"lazy"});
 const init=consoleName(g.console).replace(/[^A-Z0-9]/g,"")||consoleName(g.console).slice(0,3).toUpperCase();
 return h("div",{class:"cv blank "+(cls||""),"data-c":g.console},h("span",{},init.slice(0,4)))}
function refreshAfter(){closeCtx();const y=window.scrollY;go();setTimeout(()=>window.scrollTo(0,y),450)}

async function playGame(g){
 if(S.settings&&S.settings.confirm_launch&&!await ask("Open "+g.title+"?"))return;
 const r=await act(()=>api("launch",{id:g.id}));if(r){S.running={title:r.launched};toast("Opening "+r.launched+" in "+r.emulator+"…")}}
async function gameMenu(g,x,y){
 const cols=(await api("collections").catch(()=>({collections:[]}))).collections;
 const ok=fn=>async()=>{const r=await act(fn);if(r!==undefined)refreshAfter()};
 const items=[
  {label:"▶  Play",bold:true,fn:()=>playGame(g),disabled:!g.emulator,title:g.emulator?"":"No emulator is ready for this console. The doctor can help in his office."},
  {label:"Play online (host a room)…",fn:()=>{S.joinGame=g.id;nav("together")}},
  {label:"Details",fn:()=>openGame(g.id)},"-",
  {label:g.favorite?"Remove from favorites":"Add to favorites",fn:ok(()=>api("favorite",{id:g.id,favorite:!g.favorite}))},
  {label:"Add to collection",sub:[...cols.map(c=>({label:c.name,check:(g.collections||[]).includes(c.name),fn:ok(()=>api("collections",{action:(g.collections||[]).includes(c.name)?"remove":"add",name:c.name,id:g.id}))})),cols.length?"-":null,
    {label:"New collection…",fn:async()=>{const n=await askText("New collection","","e.g. Co-op nights, Childhood, To finish");if(!n)return;const r=await act(async()=>{await api("collections",{action:"create",name:n});return api("collections",{action:"add",name:n,id:g.id})},"Added to "+n);if(r)refreshAfter()}}]},
  {label:"Manage",sub:[
   {label:"Set custom cover art…",fn:()=>pickCover(g)},
   g.custom_cover?{label:"Remove my custom cover",fn:ok(()=>api("game_cover",{id:g.id,action:"remove"}))}:null,
   {label:"Get box art for this game…",fn:()=>fetchOneCover(g)},
   {label:g.hidden?"Show in library again":"Hide from library",fn:ok(()=>api("game_meta",{id:g.id,hidden:!g.hidden}))},"-",
   {label:"Browse local files",fn:()=>act(()=>api("game_files",{id:g.id,what:"game"}))},
   {label:"Open saves folder",fn:()=>act(()=>api("game_files",{id:g.id,what:"saves"}))},
   {label:"Copy file path",fn:async()=>{const d=await act(()=>api("game",{id:g.id}));if(!d)return;try{await navigator.clipboard.writeText(d.path||"");toast("Path copied")}catch(e){toast(d.path||"No path","")}}},
   {label:"Back up this game's saves",fn:()=>act(()=>api("backup",{id:g.id}),"Backup made")},"-",
   {label:"Uninstall…",fn:()=>uninstallGame(g)}]},"-",
  {label:"Properties…",fn:()=>gameProps(g.id)}];
 ctxMenu(x,y,items)}

function askText(title,value,placeholder){return new Promise(res=>{const done=v=>{ov.remove();res(v)};
 const inp=h("input",{type:"text",value:value||"",placeholder:placeholder||"",maxlength:80,style:"width:100%",onkeydown:e=>{if(e.key==="Enter")done(inp.value.trim());if(e.key==="Escape")done(null)}});
 const ov=h("div",{class:"modal",role:"dialog","aria-modal":"true"},h("div",{class:"modalbox"},h("h3",{style:"margin-top:0"},title),inp,h("div",{class:"row",style:"justify-content:flex-end;gap:8px;margin-top:14px"},h("button",{class:"btn",onclick:()=>done(null)},"Cancel"),h("button",{class:"btn primary",onclick:()=>done(inp.value.trim())},"OK"))));
 document.body.append(ov);inp.focus();inp.select()})}

/* ---- pictures ---- */
async function shrinkImage(file){const url=await new Promise((ok,no)=>{const fr=new FileReader();fr.onload=()=>ok(fr.result);fr.onerror=no;fr.readAsDataURL(file)});const img=new Image();
 await new Promise((ok,no)=>{img.onload=ok;img.onerror=no;img.src=url});
 const sc=Math.min(1,480/Math.max(img.width,img.height)),w=Math.max(1,Math.round(img.width*sc)),hh=Math.max(1,Math.round(img.height*sc));
 const c=document.createElement("canvas");c.width=w;c.height=hh;const x=c.getContext("2d");x.fillStyle="#1a1d33";x.fillRect(0,0,w,hh);x.drawImage(img,0,0,w,hh);
 let q=.92,out;do{out=c.toDataURL("image/jpeg",q);q-=.1}while(out.length>700000&&q>.3);return out.split(",")[1]}
async function setCoverFile(g,file){if(!g||!file)return;
 let data;try{data=await shrinkImage(file)}catch(e){toast("That picture could not be read.","err");return}
 const r=await act(()=>api("game_cover",{id:g.id,data}),"Cover set for "+g.title);if(r){GAMES[g.id]=r;refreshAfter();return r}}
function pickCover(g,after){const inp=h("input",{type:"file",accept:"image/png,image/jpeg,image/webp,image/gif",style:"display:none"});document.body.append(inp);
 inp.addEventListener("change",async()=>{const f=inp.files[0];inp.remove();if(f){const r=await setCoverFile(g,f);if(r&&after)after(r)}});inp.click()}
async function fetchOneCover(g){
 const s=await api("settings");S.settings=s.values;if(!allowNet()){netTipModal();return}
 if(!await ask("Ask thumbnails.libretro.com for the box art of "+g.title+"? Only this game's name is sent. The picture is kept on this computer.","Get box art"))return;
 let v=await act(()=>api("game_fetch_cover",{id:g.id,consent:true}));if(!v)return;
 for(let i=0;i<30&&v.state==="running";i++){await new Promise(r=>setTimeout(r,800));v=await api("covers",{}).catch(()=>({state:"error"}))}
 toast(v.found?"Got the box art.":"No box art found for that game's name. You can set your own picture.",v.found?"":"warn");refreshAfter()}

/* ---- the little 8-bit star that explains why internet-only options are off ---- */
function starBubble(){return h("div",{class:"startip",role:"note"},pixels(AVATARS.star.rows,28,"twinkle"),h("div",{class:"bub"},"Set Allow internet downloads for this option!",h("button",{class:"btn",onclick:()=>{closeModals();nav("settings")}},"Open Settings")))}
function closeModals(){document.querySelectorAll(".modal.tipmodal").forEach(x=>x.remove())}
function netTipModal(){closeModals();const ov=h("div",{class:"modal tipmodal",onclick:e=>{if(e.target===ov)ov.remove()}},h("div",{class:"modalbox"},starBubble(),h("div",{class:"row",style:"justify-content:flex-end;margin-top:12px"},h("button",{class:"btn",onclick:()=>ov.remove()},"Not now"))));document.body.append(ov)}
function coverBtn(){const off=!allowNet();let wrap;
 const b=h("button",{class:"btn",title:off?"Needs 'Allow internet downloads'":"Fetch box art for your games (asks first)","aria-describedby":off?"covtip":null,onclick:()=>{if(!allowNet()){wrap.classList.add("show");clearTimeout(wrap._t);wrap._t=setTimeout(()=>wrap.classList.remove("show"),8000);return}fetchCovers()}},"Get cover art",off?pixels(AVATARS.star.rows,14,"twinkle"):null);
 const tip=starBubble();tip.id="covtip";
 wrap=h("span",{class:"tipwrap"+(off?" off":"")},b,off?tip:null);
 if(off&&!S.starShown){S.starShown=true;setTimeout(()=>{wrap.classList.add("show");setTimeout(()=>wrap.classList.remove("show"),7000)},600)}
 return wrap}
async function fetchCovers(){
 const s=await api("settings");S.settings=s.values;if(!allowNet()){netTipModal();return}
 if(!await ask("Get cover art? Legacy Player asks thumbnails.libretro.com (the picture library RetroArch uses) for each game's box art by its name. Only game names are sent. Pictures are kept on this computer and it runs in the background.","Get cover art"))return;
 const first=await act(()=>api("covers",{action:"start",consent:true}));if(!first)return;
 const id="covtoast";let v=first;
 while(v.state==="running"){const old=$("#"+id);if(old)old.remove();$("#toasts").append(h("div",{class:"toast",id}));$("#"+id).append(h("span",{class:"spin"}),"Getting cover art… "+v.done+" of "+v.total+" ("+v.found+" found)");
  await new Promise(r=>setTimeout(r,1500));v=await api("covers",{}).catch(()=>({state:"error"}))}
 const old=$("#"+id);if(old)old.remove();
 toast(v.state==="done"?"Cover art finished: "+v.found+" new, "+v.have+" in total.":"Cover art stopped.",v.found?"":"warn");go()}

/* ---- collections and hidden games on the Library page ---- */
async function newCollection(){const n=await askText("New collection","","e.g. Co-op nights, Childhood, To finish");if(!n)return;
 const r=await act(()=>api("collections",{action:"create",name:n}),"Collection made");if(r){S.collection=n;go()}}
function drawCols(d){const c=$("#colchips");if(!c||!d)return;const cols=d.collections||[];
 c.replaceChildren(h("span",{class:"small muted",style:"align-self:center"},"Collections"),
  h("button",{class:"chip"+(!S.collection?" on":""),onclick:()=>{S.collection=null;go()}},"All"),
  ...cols.map(k=>h("button",{class:"chip"+(S.collection===k.name?" on":""),title:"Right-click to delete this collection",onclick:()=>{S.collection=S.collection===k.name?null:k.name;go()},
    oncontextmenu:e=>{e.preventDefault();ctxMenu(e.clientX,e.clientY,[{label:"Delete collection “"+k.name+"”",fn:async()=>{if(await ask("Delete the collection “"+k.name+"”? The games stay in your library.","Delete")){await act(()=>api("collections",{action:"delete",name:k.name}));if(S.collection===k.name)S.collection=null;go()}}}])}},k.name,h("small",{},k.count))),
  h("button",{class:"chip",onclick:newCollection},"+ New"),
  d.hidden_total||S.showHidden?h("button",{class:"chip"+(S.showHidden?" on":""),title:"Games you hid from the library",onclick:()=>{S.showHidden=!S.showHidden;go()}},"Hidden",h("small",{},d.hidden_total)):null)}

/* ---- Properties ---- */
async function gameProps(id){
 const g=await act(()=>api("game",{id}));if(!g)return;GAMES[g.id]=g;
 const close=()=>ov.remove();
 const cols=(await api("collections").catch(()=>({collections:[]}))).collections;
 const title=h("input",{type:"text",value:g.own_title?g.title:"",placeholder:g.original_title,maxlength:80,style:"width:100%"});
 const emu=h("select",{style:"width:100%"},h("option",{value:""},"Automatic (what the doctor set for this console)"),...g.emulator_choices.map(e=>h("option",{value:e.id,selected:g.own_emulator===e.id},e.name+(e.installed?"":" (not found on this computer)"))));
 const args=h("input",{type:"text",value:g.args,placeholder:"Usually empty",maxlength:200,style:"width:100%"});
 const note=h("textarea",{rows:3,maxlength:400,placeholder:"Your own note about this game",style:"width:100%"},g.note||"");
 const hidden=h("input",{type:"checkbox",checked:g.hidden});const fav=h("input",{type:"checkbox",checked:g.favorite});
 const colBoxes=cols.map(c=>({c,el:h("input",{type:"checkbox",checked:(g.collections||[]).includes(c.name)})}));
 const coverBox=h("div",{class:"propcover"});
 const drawCover=x=>{coverBox.replaceChildren(coverEl(x,"prop"),h("div",{class:"row",style:"margin-top:8px;gap:6px"},
   h("button",{class:"btn",onclick:()=>pickCover(x,r=>{Object.assign(g,r);drawCover(r)})},"Choose picture…"),
   x.custom_cover?h("button",{class:"btn",onclick:async()=>{const r=await act(()=>api("game_cover",{id:g.id,action:"remove"}));if(r){Object.assign(g,r);drawCover(r)}}},"Remove"):null),
   h("div",{class:"small muted",style:"margin-top:6px"},"You can also drop a picture onto a game."))};
 drawCover(g);
 const row=(l,el,help)=>h("label",{class:"prow"},h("span",{class:"pl"},l),el,help?h("span",{class:"small muted"},help):null);
 const ov=h("div",{class:"modal",role:"dialog","aria-modal":"true",onclick:e=>{if(e.target===ov)close()}},h("div",{class:"modalbox wide"},
  h("h3",{style:"margin:0 0 12px"},"Properties · "+g.title),
  h("div",{class:"propgrid"},coverBox,h("div",{},
   row("Name",title,"Only changes how it appears here. Your file keeps its name."),
   row("Emulator",emu,"Use a different emulator for just this game."),
   row("Launch options",args,"Extra options handed to the emulator when this game starts. Leave empty unless the emulator's own help tells you what to type."),
   row("Note",note),
   h("div",{class:"row",style:"gap:16px;margin:6px 0"},h("label",{},fav," Favorite"),h("label",{},hidden," Hide from library")),
   cols.length?h("div",{class:"row",style:"gap:12px;margin:6px 0"},h("span",{class:"small muted"},"Collections"),...colBoxes.map(b=>h("label",{class:"small"},b.el," "+b.c.name))):null)),
  h("div",{class:"small muted propinfo"},
   h("div",{},g.console_name+(g.region?" · "+g.region:"")+" · "+g.size_mb+" MB · played "+g.plays+(g.plays===1?" time":" times")+(g.last_played?" · last "+ago(g.last_played):"")),
   h("div",{style:"word-break:break-all"},g.path||""),h("div",{},"Saves: "+(g.save_source||"not set")+" ("+g.save_files.length+" file"+(g.save_files.length===1?"":"s")+")")),
  h("div",{class:"row",style:"justify-content:flex-end;gap:8px;margin-top:14px"},
   h("button",{class:"btn",onclick:()=>act(()=>api("game_files",{id:g.id,what:"game"}))},"Browse files"),h("button",{class:"btn bad",onclick:()=>{close();uninstallGame(g)}},"Uninstall…"),h("div",{class:"grow"}),
   h("button",{class:"btn",onclick:close},"Close"),
   h("button",{class:"btn primary",onclick:async()=>{
    const r=await act(async()=>{await api("game_meta",{id:g.id,title:title.value,emulator:emu.value,args:args.value,note:note.value,hidden:hidden.checked});
     if(fav.checked!==g.favorite)await api("favorite",{id:g.id,favorite:fav.checked});
     for(const b of colBoxes){const had=(g.collections||[]).includes(b.c.name);if(b.el.checked!==had)await api("collections",{action:b.el.checked?"add":"remove",name:b.c.name,id:g.id})}return true},"Saved");
    if(r){close();refreshAfter()}}},"Save"))));
 document.body.append(ov);title.focus()}

/* ================= the doctor's office (Setup) ================= */
const PLANT=["...N..N...","..NNNNNN..",".NNTNNTNN.","..NNNTNN..","...NTNN...","....TT....","..XXXXXX..","..XXXXXX..","...XXXX...","...XXXX..."];
const DIPLOMA=["YYYYYYYYYYYYYY","YWWWWWWWWWWWWY","YWGGGGGGGGGGWY","YWWWWWWWWWWWWY","YWGGGGGGGGWWWY","YWGGGGGGGGWWWY","YWWWWWWWWRRWWY","YWWWWWWWWRRWWY","YWWWWWWWWWWWWY","YYYYYYYYYYYYYY"];
const WINDOW=["DDDDDDDDDDDDDDDD","DCCCCCCDCCCCCCCD","DCCCYYCDCCCCCCCD","DCCYYYYDCCCWWCCD","DCCCYYCDCCWWWWCD","DCCCCCCDCCCCCCCD","DDDDDDDDDDDDDDDD","DCCCCCCDCCCCCCCD","DCCCCCCDCCCCCCCD","DCNNCCCDCCCCCNND","DNNNNCCDCCCNNNND","DNNNNNNDNNNNNNND","DDDDDDDDDDDDDDDD","..LLLLLLLLLLLL.."];
const CROSS=["...RRR...","...RRR...","...RRR...","RRRRRRRRR","RRRRRRRRR","RRRRRRRRR","...RRR...","...RRR...","...RRR..."];
const BOOKS=[".RR.BBB.YY.NNN.LL.RR.","RRR.BBB.YY.NNN.LL.RR","RRR.BBB.YY.NNN.LL.RR","RRR.BBB.YY.NNN.LL.RR","RRR.BBB.YY.NNN.LL.RR","KKKKKKKKKKKKKKKKKKKK"];
const FX_ICONS=[["G","..GG.GG.","..GGGGG.","...GGG..","...GG...","..GG....",".GG.....","GG......","G......."],["G","..G..G..",".GGGGGG.","GGG..GGG",".G....G.",".G....G.","GGG..GGG",".GGGGGG.","..G..G.."],
 ["Y","...YY...","..YY....",".YYYYY..","...YY...","..YY....",".YY.....","Y.......","........"],["R"].concat(AVATARS.heart.rows),["Y"].concat(AVATARS.star.rows),["C","..CC.CC.",".CCCCCCC",".CCCCCCC","..CCCCC.","...CCC..","....C...","........","........"]].map(a=>a.slice(1));
const WORK_LINES={install:["Tightening your cores…","Percussive maintenance!","Have you tried turning it off and on again?","This will only pinch a little.","Hold still, little emulator!","Applying one (1) bandage to RetroArch.","Scrubbing in… 20 seconds, like always."],
 scan:["Peeking behind the couch cushions…","Counting your ROMs… 1, 2, 3, lots!","Checking under the sofa for BIOS files.","Stethoscope on the hard drive: ba-dum, ba-dum.","Dusting off the cartridges…","Is that a Game Boy in my pocket? Oh, it's a stethoscope."]};
let DOCW={on:false,t:null,fx:null,i:0};
function docWork(on,kind){
 const spot=$(".docspot"),say=$(".docsay"),fx=$(".fxlayer");
 DOCW.on=on;DOCW.kind=on?kind:null;clearInterval(DOCW.t);clearInterval(DOCW.fx);
 if(spot)spot.classList.toggle("working",on);
 if(!on){const d=S.doc;if(say&&d&&!S.visit)say.textContent=doctorSay(d);return}
 const lines=WORK_LINES[kind]||WORK_LINES.scan;DOCW.i=Math.floor(Math.random()*lines.length);
 const talk=()=>{const s=$(".docsay");if(s&&!S.visit){s.textContent=lines[DOCW.i++%lines.length]}};talk();DOCW.t=setInterval(talk,2300);
 DOCW.fx=setInterval(()=>{const f=$(".fxlayer");if(!f){clearInterval(DOCW.fx);return}
  const ic=FX_ICONS[Math.floor(Math.random()*FX_ICONS.length)],e=pixels(ic,20+Math.random()*10,"fx");e.style.left=(8+Math.random()*84)+"%";f.append(e);setTimeout(()=>e.remove(),1800)},330)}
function buildVisit(dr){const act=dr.issues.filter(i=>!i.dismissed),L=[],n=(x,w)=>x+" "+w+(x===1?"":"s");
 L.push(["happy","Well hello there, player! Hop up on the table and let's see how you're doing."]);
 if(dr.games){const top=dr.library.slice().sort((a,b)=>b.count-a.count).slice(0,3).map(c=>c.name+" ("+c.count+")");
  L.push(["happy","Let me see... "+n(dr.games,"game")+" across "+n(dr.library.length,"console")+"! Mostly "+(top.length>1?top.slice(0,-1).join(", ")+" and "+top[top.length-1]:top[0])+". Nice collection!"])}
 else L.push(["sad","Hmm, I don't see any games yet. Point me at your games folder in Library and I'll count them!"]);
 const cards=dr.emulator_cards||[];
 if(S.specs&&(S.specs.gpus.length||S.specs.ram_gb)){const sp=S.specs,v=sp.verdicts||[],heavy=(v[2]||{}).level,mid=(v[1]||{}).level;
  L.push(["happy","Now your machine: "+(sp.gpus.length?sp.gpus[0].name+" graphics":"graphics I can't read")+(sp.ram_gb?", "+sp.ram_gb+" GB of memory":"")+(sp.cpu?", and a "+sp.cpu+".":".")+" "+
   (heavy==="great"?"Strong machine! Even the heavy consoles should purr.":heavy==="maybe"?"Solid for most things. The heaviest ones, like PS3, may struggle.":mid==="great"?"Good for the classics and the mid-generation ones.":"A cozy little machine: stick to the classics and handhelds.")])}
 if(cards.length){const nm=cards.map(c=>c.name);L.push(["happy","My waiting room has "+n(cards.length,"emulator")+": "+(nm.length>1?nm.slice(0,-1).join(", ")+" and "+nm[nm.length-1]:nm[0])+". All awake and ready!"])}
 else L.push(["sad","My waiting room is empty! We need an emulator. Open Engines and I'll help you find one."]);
 L.push([dr.consoles_ready?"happy":"worried",dr.consoles_ready+" of "+dr.consoles_total+" consoles are ready to play. "+(dr.library.some(c=>!c.emulator)?"Still waiting on: "+dr.library.filter(c=>!c.emulator).map(c=>c.name).join(", ")+".":"Every console you own has a doctor on call!")]);
 L.push([dr.saves_ready?"happy":"worried",dr.saves_ready?"Your save folders are in great shape. No lost progress on my watch!":"I haven't made your save folders yet. Press Scan everything and I'll set them up."]);
 L.push(["happy",dr.bios_needed?"BIOS files: "+dr.bios_have+" of "+dr.bios_needed+" found.":"No BIOS files needed for what you have. Easy!"]);
 L.push([dr.last_scan?"happy":"worried",dr.last_scan?"I last scanned your computer "+ago(dr.last_scan)+".":"I've never scanned your computer. Let's fix that with a Scan everything!"]);
 if(act.length){L.push(["worried","Now, about "+(act.length===1?"that one thing":"those "+act.length+" things")+"..."]);act.slice(0,4).forEach(i=>L.push(["worried",i.text]));
  L.push(["worried","Don't worry. Press Fix on the case files below and I'll get right on it, or tell me you don't need it."]);
  L.push(["happy","Sort those out and you'll be healthy as can be. And then the best medicine is to stay home and play video games!"])}
 else if(dr.games&&cards.length){L.push(["happy","Heart rate: steady. Saves: safe. Emulators: awake. You are healthy as can be!"]);L.push(["happy","My prescription: stay home and play video games! Doctor's orders!","rx"])}
 else L.push(["happy","Get your games and an emulator in, and come back. I'll be here, polishing my stethoscope!"]);
 return L}
const TIRED={
 3:["sigh","*sigh* You're back already? Okay. Let me look at you one more time.","Still {g} games. Still {e}. Nothing moved.","Still healthy. Same prescription: stay home and play video games."],
 4:["eyeroll","*rolls eyes* Again? I literally just did this.","Same games. Same emulators. I promise.","Healthy. Stay home. Play games. Please."],
 5:["facepalm","*facepalm* Do you need to hear it a fifth time?","Your emulators are fine. They are always fine.","Healthy as ever. Go. Play. Be free."],
 6:["rub","*rubs temples* My head hurts. And I'm the doctor.","I'm running out of ways to say \u201cyou're fine\u201d.","Prescription: video games. And a nap. For me."],
 7:["yawn","*yaaawn* Is it midnight? Feels like midnight.","...where was I? Oh. Games. You have games.","Healthy. ...zzz... stay home... play..."],
 8:["drum","*drums fingers on the desk* Tap. Tap. Tap.","I have other patients. Okay, I don't. But still.","Healthy! Now go play something!"],
 9:["glare","*glares* One. More. Time.","Don't make me hide the stethoscope.","You are healthy. You WILL remain healthy. GO. PLAY."],
 10:["suspicious","Wait a second...","...you're not sick. You're not even a little bit sick.","Are you just messing with me?"]};
function visitLines(dr){
 const now=Date.now();if(!S.docLast||now-S.docLast>10*60000)S.docVisits=0;S.docLast=now;S.docVisits=(S.docVisits||0)+1;const n=S.docVisits;
 if(n<=2)return buildVisit(dr);
 const t=TIRED[Math.min(n,10)],act=dr.issues.filter(i=>!i.dismissed);
 const fill=x=>x.replace("{g}",dr.games).replace("{e}",(dr.emulator_cards||[]).length+" emulator"+((dr.emulator_cards||[]).length===1?"":"s"));
 const L=[[t[0],fill(t[1])],[t[0],fill(t[2])]];
 if(act.length)L.push([t[0],"You still have "+act.length+" thing"+(act.length===1?"":"s")+" in the case files. Fix those, or tell me you don't need them."]);
 else if(n>=10){L.push(["suspicious",t[3]],["suspicious",n===10?"...Because I'm going to keep doing this either way. Stay home. Play video games.":"I KNOW you're messing with me. Prescription: stay home. Play video games. (Again.)","rx"]);}
 else L.push([t[0],t[3],"rx"]);
 return L}
async function startVisit(dr){
 if(S.visit)return;const spot=$(".docspot"),say=$(".docsay"),scene=$(".office");if(!say)return;S.visit=true;const rx=$(".rx");if(rx)rx.remove();
 const lines=visitLines(dr);let skip=false;
 const paint=m=>{spot.replaceChildren(pixels(doctorRows(m),176,"doctor "+m))};
 const next=()=>new Promise(res=>{const done=()=>{scene.removeEventListener("click",done);document.removeEventListener("keydown",key);res()};
  const key=e=>{if(e.key==="Enter"||e.key===" "||e.key==="a"){e.preventDefault();done()}if(e.key==="Escape"){skip=true;done()}};
  scene.addEventListener("click",done);document.addEventListener("keydown",key)});
 scene.classList.add("visiting");
 for(let k=0;k<lines.length&&!skip;k++){const[m,text,tag]=lines[k];paint(m);
  say.classList.add("talk");say.textContent="";let i=0,quick=false;
  const skipType=()=>{quick=true};scene.addEventListener("click",skipType,{once:true});
  while(i<text.length&&!quick){say.textContent=text.slice(0,++i);await new Promise(r=>setTimeout(r,18))}say.textContent=text;
  say.classList.remove("talk");scene.removeEventListener("click",skipType);
  if(tag==="rx"){showRx()}
  const more=h("span",{class:"more"},k<lines.length-1?" ▼":" ■");say.append(more);
  if(k<lines.length-1)await next()}
 S.visit=false;scene.classList.remove("visiting");const tired=(S.docVisits||0)>=3;paint(tired?(S.docVisits>=10?"suspicious":"sigh"):dr.mood);say.textContent=tired?(S.docVisits>=10?"...I'm watching you.":"I need a coffee."):doctorSay(dr)}
function showRx(){const scene=$(".office");if(!scene||$(".rx"))return;const n=S.docVisits||1;
 const body=n>=10?["Stay home.","Play video games.","(Stop messing with me.)"]:n>=6?["Stay home.","Play games.","Let me sleep."]:n>=3?["Stay home.","Play games."]:["Stay home.","Play video games.","Repeat daily."];
 scene.append(h("div",{class:"rx"},h("div",{class:"rxh"},"℞ PRESCRIPTION"+(n>2?" #"+n:"")),...body.map(x=>h("div",{},x)),h("div",{class:"rxs"},"— Doc")))}
const GRADS=[["#3b6bff","#7a5cff"],["#d9468f","#ff8a5c"],["#0aa57a","#2bd1b0"],["#7b4dff","#4fc3ff"],["#e8a21a","#ff6a3d"],["#2b8cff","#3be0a8"]];
function caseCards(dr,refresh){const act=dr.issues.filter(i=>!i.dismissed),quiet=dr.issues.filter(i=>i.dismissed);
 const ic={core:AVATARS.gem,emulator:AVATARS.controller,bios:AVATARS.ghost};
 const fix=i=>i.kind==="core"?{t:"Install the core",fn:()=>{const el=$("#supplies");if(el)el.scrollIntoView({behavior:"smooth"});toast("Press “Install missing cores” in the supply cabinet","")}}:{t:i.kind==="bios"?"Find BIOS files":"Find an emulator",fn:()=>nav("engines")};
 return h("div",{},act.length?h("div",{class:"cases"},...act.map((i,n)=>{const g=GRADS[n%GRADS.length],f=fix(i);
   return h("div",{class:"case",style:`--c1:${g[0]};--c2:${g[1]}`},h("span",{class:"stamp"},"NEEDS A DOCTOR"),pixels((ic[i.kind]||AVATARS.gem).rows,44,"caseicon"),
    h("div",{class:"ct"},i.kind==="core"?"Missing core":i.kind==="bios"?"Missing BIOS":"Missing emulator"),h("p",{},i.text),
    h("div",{class:"row",style:"gap:8px"},h("button",{class:"btn primary",onclick:f.fn},f.t),
     h("button",{class:"btn",title:"I do not want to install that. Stop worrying about it.",onclick:async()=>{await act(()=>api("doctor_dismiss",{key:i.key}));refresh()}},"I don't need it")))})):null,
  quiet.length?h("div",{class:"small muted",style:"margin-top:8px"},quiet.length+" worr"+(quiet.length>1?"ies":"y")+" set aside. ",h("a",{href:"#",onclick:async e=>{e.preventDefault();for(const q of quiet)await api("doctor_dismiss",{key:q.key,undo:true});refresh()}},"Bring back")):null)}
function emulatorCards(dr){const cards=dr.emulator_cards||[];const av=[AVATARS.controller,AVATARS.gem,AVATARS.rocket,AVATARS.star,AVATARS.robot,AVATARS.ghost];
 if(!cards.length)return h("div",{class:"ecard empty"},pixels(AVATARS.ghost.rows,44),h("div",{class:"en"},"The waiting room is empty"),h("p",{class:"small"},"No emulators found yet."),h("button",{class:"btn primary",onclick:()=>nav("engines")},"Find emulators"));
 return h("div",{class:"ecards"},...cards.map((c,n)=>{const g=GRADS[n%GRADS.length];
  return h("div",{class:"ecard",style:`--c1:${g[0]};--c2:${g[1]}`,title:c.path},h("span",{class:"healthy"},"✓ HEALTHY"),pixels(av[n%av.length].rows,52,"eicon"),h("div",{class:"en"},c.name),
   h("div",{class:"chips",style:"margin:6px 0"},...(c.consoles.length?c.consoles.slice(0,6).map(x=>h("span",{class:"chip",style:"cursor:default"},x)):[h("span",{class:"chip",style:"cursor:default"},"standing by")])),
   h("div",{class:"small",style:"opacity:.9"},c.games?"Plays "+c.games+" of your games":"No games waiting for it yet"),h("div",{class:"epath small"},c.path))}))}
async function viewSetup(m){
 clearInterval(S.setupTimer);clearInterval(S.officeTimer);S.visit=false;
 const dr=S.doc=await api("doctor");
 const refresh=()=>{const y=window.scrollY;go();setTimeout(()=>window.scrollTo(0,y),450)};
 const spot=h("div",{class:"docspot",title:"Click me for a check-up!",onclick:e=>{if(S.visit)return;e.stopPropagation();startVisit(S.doc)}}),say=h("div",{class:"docsay"});
 const paint=d=>{S.doc=d;spot.replaceChildren(pixels(doctorRows(d.mood),176,"doctor "+d.mood));if(!S.visit&&!DOCW.on)say.textContent=doctorSay(d)};
 const report=doctorCard(dr,{office:true,noWorries:true,onDraw:paint});
 const supplies=h("div",{id:"supplies",class:"supplies"});
 const specsBox=h("div",{class:"specs"},h("p",{class:"small muted"},"Reading your computer…"));
 (S.specs?Promise.resolve(S.specs):api("specs")).then(sp=>{S.specs=sp;paintSpecs(specsBox,sp)}).catch(()=>specsBox.replaceChildren(h("p",{class:"small muted"},"Could not read this computer's details.")));
 const start=h("button",{class:"pressstart",type:"button",onclick:e=>{e.stopPropagation();startVisit(S.doc)}},"▶ PRESS START");
 m.append(h("h2",{},"The Doctor's Office"),
  h("div",{class:"why"},"Come on in! Press Start or click the doctor for a check-up. He checks your games, emulators, save folders and BIOS files. The supply cabinet below stocks what he can safely install for you."),
  h("div",{class:"officegrid"},
   h("div",{class:"office"},h("div",{class:"wall"},
     h("div",{class:"decor win"},pixels(WINDOW,150)),h("div",{class:"decor dip"},pixels(DIPLOMA,92)),h("div",{class:"decor sign"},pixels(CROSS,40)),h("div",{class:"decor plant"},pixels(PLANT,64)),h("div",{class:"decor books"},pixels(BOOKS,130))),
    h("div",{class:"deskzone"},say,spot,h("div",{class:"desk"},h("span",{class:"plate"},"DOC"),h("span",{class:"deskcat"},martin(52)))),h("div",{class:"fxlayer"}),start),
   h("div",{class:"clip"},h("h3",{style:"margin:0 0 10px"},"Today's check-up"),report)),
  dr.issues.length?h("h3",{class:"sect"},"Case files"):"",caseCards(dr,refresh),
  h("h3",{class:"sect"},"In the waiting room: your emulators"),emulatorCards(dr),
  h("h3",{class:"sect"},"The patient's chart: what you're playing on"),specsBox,
  h("h3",{class:"sect"},"The supply cabinet"),supplies,
  h("h3",{class:"sect"},"Closing the clinic"),
  h("div",{class:"card row",style:"align-items:center;gap:14px"},h("div",{class:"grow small muted"},"Done with Legacy Player? The doctor can uninstall it for you: he removes what Legacy Player installed, keeps your saves unless you say otherwise, never touches your games, and hands you a discharge report."),
   h("button",{class:"btn bad",onclick:()=>retireClinic()},"Uninstall Legacy Player...")));
 viewSupplies(supplies);
 /* he gets busy while an install runs */
 S.officeTimer=setInterval(async()=>{if(S.tab!=="setup"){clearInterval(S.officeTimer);docWork(false);return}
  const st=await api("setup_status").catch(()=>null);if(!st)return;const running=st.job&&st.job.state==="running";
  if(running&&!DOCW.on)docWork(true,"install");else if(!running&&DOCW.on&&DOCW.kind!=="scan"){docWork(false)}},1800);
 if(S.autoVisit){S.autoVisit=false;setTimeout(()=>startVisit(S.doc),700)}}

/* ================= online: it is obvious when you are connected ================= */
function liveInfo(){const r=S.room,w=(S.waits||[])[0];
 if(r&&r.queue)return{kind:"wait",text:"In line #"+r.queue.position+" for "+r.game};
 if(r&&r.waiting_for_host)return{kind:"wait",text:"Waiting for the host to let you in"};
 if(r){const n=(r.members||[]).length,avg=r.stats&&r.stats.average&&r.stats.average.ping_ms;
  return{kind:"room",text:"ONLINE · "+r.game+" · "+n+(r.max_players?"/"+r.max_players:"")+" player"+(n===1?"":"s")+(avg!=null?" · "+Math.round(avg)+" ms":"")}}
 if(w)return{kind:"wait",text:"In line"+(w.position?" #"+w.position:"")+" for "+w.game};
 if(S.online)return{kind:"server",text:"Connected to a server"};
 return{kind:"off",text:"Multiplayer server offline"}}
function liveMenu(){const i=liveInfo();return[[(i.kind==="room"?"● ":i.kind==="wait"?"◐ ":i.kind==="server"?"○ ":"✕ ")+(i.kind==="room"?"In a room: "+S.room.game:i.kind==="off"?"Not connected":i.text),()=>nav(i.kind==="off"?"servers":"together")],"-"]}
function renderLive(){
 const i=liveInfo(),pill=$("#srv");
 if(pill){pill.className="srvpill "+i.kind;pill.title=i.kind==="off"?"Open Servers":"Open your room";pill.onclick=()=>nav(i.kind==="off"?"servers":"together");
  pill.replaceChildren(h("span",{class:"dot"+(i.kind==="room"||i.kind==="server"?" on":"")+(i.kind==="room"?" pulse":"")}),h("span",{id:"srvtxt"},i.text))}
 const bar=$("#livebar");
 if(bar){const r=S.room;
  if(r&&i.kind==="room"){bar.hidden=false;const n=(r.members||[]).length,avg=r.stats&&r.stats.average&&r.stats.average.ping_ms;
   bar.replaceChildren(h("span",{class:"onair"},h("span",{class:"dot on pulse"}),"ONLINE"),
    h("span",{class:"lv"},h("b",{},r.game),h("span",{class:"muted"}," · "+consoleName(r.console)+" · "+(r.role==="host"?"you are hosting":"you joined"))),
    h("span",{class:"lvp"},...(r.members||[]).map(p=>h("span",{class:"lvchip"+(p.me?" me":"")+(p.ready?" rdy":"")},p.name+(p.me?" (you)":"")))),
    h("span",{class:"grow"}),
    h("span",{class:"badge"},n+(r.max_players?"/"+r.max_players:"")+" players"),avg!=null?h("span",{class:"badge"},Math.round(avg)+" ms"):null,h("span",{class:"badge"},r.state),
    S.running?h("span",{class:"badge good"},"game running"):null,
    r.role==="host"&&r.invite_code?h("button",{class:"btn",title:"Copy the invite code for friends",onclick:async()=>{try{await navigator.clipboard.writeText(r.invite_code);toast("Invite code copied")}catch(e){toast("Invite code: "+r.invite_code)}}},"Copy invite"):null,
    S.tab==="together"?null:h("button",{class:"btn primary",onclick:()=>nav("together")},"Open room"),
    h("button",{class:"btn bad",onclick:async()=>{if(!await ask(r.role==="host"?"Close the room? Everyone is disconnected.":"Leave the room?",r.role==="host"?"Close room":"Leave"))return;await act(()=>api("mp_leave"));S.room=null;renderNav();if(S.tab==="together")go()}},r.role==="host"?"Close":"Leave"))}
  else if(i.kind==="wait"){bar.hidden=false;bar.replaceChildren(h("span",{class:"onair wait"},h("span",{class:"dot"}),"IN LINE"),h("span",{class:"lv"},i.text),h("span",{class:"grow"}),S.tab==="together"?null:h("button",{class:"btn",onclick:()=>nav("together")},"Open"))}
  else{bar.hidden=true;bar.replaceChildren()}}
 const sig=i.kind+"|"+(S.room?S.room.game:"");
 if(sig!==S.menuSig&&!document.querySelector(".menu.open")&&$("#menubar")&&$("#menubar").children.length){S.menuSig=sig;buildMenubar()}}
async function pingServer(){const r=await api("server_status").catch(()=>({online:false}));S.online=r.online;
 if(r.online&&!S.onlineSeen){S.onlineSeen=true;autoNetTest(S.netcheck&&S.netcheck.server&&S.netcheck.server.ok?1200:0)}
 renderLive();return r}

/* ================= the patient's chart: what this computer is ================= */
const SPEC_ICON={gpu:["B",".BBBBBBBBBBB.","B.....B....B","B.BB..B.BB.B","B.BB..B.BB.B","B.....B....B",".BBBBBBBBBBB.","..W.W.W.W.W.."].slice(1),
 cpu:["Y","..Y.Y.Y.Y..","YYYYYYYYYYYY","Y..........Y","Y..YYYYYY..Y","Y..Y....Y..Y","Y..YYYYYY..Y","Y..........Y","YYYYYYYYYYYY","..Y.Y.Y.Y.."].slice(1),
 ram:["N","NNNNNNNNNNNN","N.N.N.N.N..N","N.N.N.N.N..N","NNNNNNNNNNNN","N.N.N.N.N.N.","............"].slice(1),
 os:["C","CCCCCCCCCC","C........C","C........C","C........C","CCCCCCCCCC","...CCCC...","..CCCCCC.."].slice(1)};
function specIcon(k){const rows=SPEC_ICON[k];const col={gpu:"#7a9bff",cpu:PAL.Y,ram:PAL.N,os:PAL.C}[k];const w=Math.max(...rows.map(r=>r.length));
 return pixelsC(rows.map(r=>r.padEnd(w,".").replace(/[^.]/g,"X")),44,"specico",{X:col})}
function paintSpecs(box,sp){
 const tile=(k,label,main,sub,g)=>h("div",{class:"spec",style:`--c1:${g[0]};--c2:${g[1]}`},specIcon(k),h("div",{class:"sl"},label),h("div",{class:"sm"},main||"Unknown"),sub?h("div",{class:"ss"},sub):null);
 const gpus=sp.gpus||[];
 box.replaceChildren(h("div",{class:"specgrid"},
  tile("gpu",gpus.length>1?"Graphics (main first)":"Graphics",gpus.length?gpus[0].name:"",gpus.length>1?"Also: "+gpus.slice(1).map(g=>g.name).join(", "):"",["#3b6bff","#7a5cff"]),
  tile("cpu","Processor",sp.cpu,[sp.cores?sp.cores+" cores":null,sp.threads?sp.threads+" threads":null].filter(Boolean).join(" · "),["#e8a21a","#ff6a3d"]),
  tile("ram","Memory",sp.ram_gb?sp.ram_gb+" GB":"",sp.arch||"",["#0aa57a","#2bd1b0"]),
  tile("os","System",sp.os,"",["#2b8cff","#3be0a8"])),
 h("div",{class:"verdicts"},...(sp.verdicts||[]).map(v=>h("div",{class:"verdict "+v.level},h("b",{},v.level==="great"?"Should run well":v.level==="maybe"?"Might struggle":"Probably too heavy"),h("span",{class:"vl"},v.label),h("span",{class:"small"},v.consoles)))),
 h("p",{class:"small muted"},"A rough guide from your processor, memory and graphics card, not a test. It was read on this computer and is never sent anywhere."))}
