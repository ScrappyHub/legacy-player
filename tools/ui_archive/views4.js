/* ================= consoles: sprites, colours, banners ================= */
const TPL={
 pad:["..KKKKKKKKKKKK..",".KBBBBBBBBBBBBK.","KBBBKBBBBBBXBBBK","KBBKKKBBBBXBXBBK","KBBBKBBBBBBXBBBK","KBBBBBBBBBBBBBBK",".KBBBKKKKKKBBBK.","..KKK......KKK.."],
 pad2:["..KKKKKKKKKKKK..",".KBBBBBBBBBBBBK.","KBBKKBBBBBBXBBBK","KBBKKBBBBBXBXBBK","KBBBBBBBBBBXBBBK","KBBBKKBBKKBBBBBK",".KBBKKBBKKBBBBK.","..KKK......KKK.."],
 n64:[".KKKK..KK..KKKK.","KBBBBK.KK.KBBBBK","KBKBBBKBBKBBBXBK","KBBBBBKBBKBBXBXK","KBBBBBKBBKBBBXBK",".KBBBBBKKBBBBBK.","..KBBBBBBBBBBK..","...KBBBBBBBBK...","....KKKKKKKK...."],
 gb:[".KKKKKKKKK.","KBBBBBBBBBK","KBKKKKKKKBK","KBKSSSSSKBK","KBKSSSSSKBK","KBKSSSSSKBK","KBKKKKKKKBK","KBBBBBBBBBK","KBBKBBBBXBK","KBKKKBBXBBK","KBBKBBBBBBK","KBBBBBBBBBK","KBBBBBBBBKK",".KKKKKKKKK."],
 gba:[".KKKKKKKKKKKKKK.","KBBBBBBBBBBBBBBK","KBKBBKKKKKKBBXBK","KKKKBKSSSSKBXBXK","KBKBBKSSSSKBBXBK","KBBBBKKKKKKBBBBK","KBBBBBBBBBBBBBBK",".KKKKKKKKKKKKKK."],
 psp:[".KKKKKKKKKKKKKKKK.","KBBBBBBBBBBBBBBBBK","KBKBBKSSSSSSKBBXBK","KKKKBKSSSSSSKBXBXK","KBKBBKSSSSSSKBBXBK","KBBBBKSSSSSSKBBBBK","KBBBBBBBBBBBBBBBBK",".KKKKKKKKKKKKKKKK."],
 ds:[".KKKKKKKKKK.","KBBBBBBBBBBK","KBKKKKKKKKBK","KBKSSSSSSKBK","KBKSSSSSSKBK","KBKKKKKKKKBK","KAAAAAAAAAAK","KBKKKKKKKKBK","KBKSSSSSSKBK","KBKSSSSSSKBK","KBKKKKKKKKBK",".KKKKKKKKKK."],
 stick:["....KK....","...KAAK...","...KAAK...","....KK....","....KK....","....KK....",".KKKKKKKK.","KBBBBBBBBK","KBBBBXBBBK","KBBBBBBBBK","KBBBBBBBBK",".KKKKKKKK."],
 box:[".KKKKKKKKKKKKKK.","KBBBBBBBBBBBBBBK","KBBKKKKKKKKKKBBK","KBBKAAAAAAAAKBBK","KBBKKKKKKKKKKBBK","KBBBBBBBBBBBXBBK",".KKKKKKKKKKKKKK."],
 remote:[".KKKK.","KBBBBK","KBBBBK","KBKKBK","KBBBBK","KBXXBK","KBBBBK","KBKKBK","KBBBBK","KBBBBK","KBBBBK","KBBBBK","KBBBBK",".KKKK."]};
/* g: banner gradient, tpl: sprite, B body, A accent, X buttons, S screen, tag: one friendly line, anim: how the sprite moves */
const CON={
 all:{g:["#3b6bff","#7a5cff"],tag:"Every console, one place",anim:"bob"},
 atari:{g:["#6b3410","#d9a23a"],tpl:"stick",B:"#4a3326",A:"#e8c07a",X:"#e63b2e",tag:"One button, one stick, endless afternoons",anim:"joy"},
 nes:{g:["#8c1d1d","#3a3f55"],tpl:"pad",B:"#c9c9cf",X:"#d63a3a",tag:"The one that started it all",anim:"wig"},
 snes:{g:["#4b3b9a","#a9abc6"],tpl:"pad2",B:"#cfd0dc",X:"#7b5ac8",tag:"Four colours of pure joy",anim:"wig"},
 genesis:{g:["#0d1230","#2b5cff"],tpl:"pad",B:"#262833",X:"#e8e8ee",tag:"Blast processing!",anim:"wig"},
 gb:{g:["#3f4f1f","#9bbc0f"],tpl:"gb",B:"#b9bcae",S:"#8bac0f",X:"#8a2a5a",tag:"Pocket-sized forever",anim:"sway"},
 gbc:{g:["#5a22c4","#25cfa8"],tpl:"gb",B:"#7a4fe0",S:"#9bbc0f",X:"#e8e8ee",tag:"Now in colour",anim:"sway"},
 gba:{g:["#35247f","#7a5cff"],tpl:"gba",B:"#6a4fcf",S:"#9ac08a",X:"#e8e8ee",tag:"Shoulder buttons, big adventures",anim:"sway"},
 ps1:{g:["#262a44","#8a8fb0"],tpl:"pad2",B:"#bdbdc6",X:"#4bd0a0",tag:"Insert disc, press start",anim:"wig"},
 n64:{g:["#16367a","#d6a21a"],tpl:"n64",B:"#7d7d86",X:"#f2c230",tag:"Three prongs, four players",anim:"wig"},
 gamecube:{g:["#3b2a8a","#8a6fe8"],tpl:"pad2",B:"#6f55d0",X:"#3bd0a0",tag:"Small cube, big party",anim:"wig"},
 ps2:{g:["#0a0f2e","#2b4cc8"],tpl:"box",B:"#16181f",A:"#3b6bff",X:"#3bd0a0",tag:"The best-selling console ever",anim:"bob"},
 xbox:{g:["#0b3a14","#5fd13a"],tpl:"pad2",B:"#2c8a2c",X:"#e8e8ee",tag:"Halo-powered",anim:"wig"},
 ds:{g:["#2b3b66","#9ab0d8"],tpl:"ds",B:"#c9c9d2",S:"#7ec8e8",A:"#8a8fa8",tag:"Two screens, touch to play",anim:"flip"},
 psp:{g:["#10131f","#2bb1ff"],tpl:"psp",B:"#16161e",S:"#6fd0ff",X:"#e8e8ee",tag:"Console games on the go",anim:"sway"},
 wii:{g:["#0a86b8","#8fd8f2"],tpl:"remote",B:"#f2f2f4",X:"#3b6bff",tag:"Swing it!",anim:"swing"},
 x360:{g:["#1b4a14","#8bd13a"],tpl:"pad2",B:"#e6e6ea",X:"#4bd13a",tag:"Achievement unlocked",anim:"wig"},
 "3ds":{g:["#a31818","#ff7a5c"],tpl:"ds",B:"#d63a3a",S:"#7ec8e8",A:"#7a1010",tag:"3D without the glasses",anim:"flip"},
 ps3:{g:["#0b0b14","#5a5aa0"],tpl:"pad2",B:"#1a1a22",X:"#bdbdd0",tag:"Blu-ray, big worlds",anim:"wig"}};
function pixelsC(rows,size,cls,pal){const w=rows[0].length,hh=rows.length;let r="";rows.forEach((row,y)=>{[...row].forEach((c,x)=>{if(c!==".")r+=`<rect x="${x}" y="${y}" width="1" height="1" fill="${pal[c]||"#000"}"/>`})});
 return svgEl(`<svg class="px ${cls||""}" viewBox="0 0 ${w} ${hh}" width="${size}" height="${Math.round(size*hh/w)}" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${r}</svg>`)}
function conInfo(id){return CON[id]||{g:["#3b6bff","#7a5cff"],tag:"",anim:"bob"}}
function conSprite(id,size,cls,cap){const c=conInfo(id);if(id==="all")return martin(size,"cs "+(cls||""));
 if(!c.tpl)return pixels(AVATARS.controller.rows,size,"cs "+(cls||""));
 const rows=TPL[c.tpl],ratio=rows.length/rows[0].length,lim=cap||0.62;if(ratio>lim)size=Math.round(size*lim/ratio);
 return pixelsC(rows,size,"cs a-"+c.anim+" "+(cls||""),{K:"#12141f",B:c.B||"#ccc",A:c.A||"#999",X:c.X||"#e33",S:c.S||"#8bd",W:"#fff"})}
function conStyle(id){const g=conInfo(id).g;return`--c1:${g[0]};--c2:${g[1]}`}
function conChip(id,name,count,on,onclick,extra){return h("button",{type:"button",class:"conchip"+(on?" on":""),style:conStyle(id),onclick,title:conInfo(id).tag},
 h("span",{class:"cico"},conSprite(id,38)),h("span",{class:"cnm"},name),count!=null?h("small",{},count):null,extra||null)}

function drawChips(d){drawCols(d);const c=$("#chips");
 c.replaceChildren(h("button",{class:"chip"+(S.console?"":" on"),onclick:()=>{S.console=null;go()}},"All",h("small",{},d.total)),
  ...d.consoles.map(k=>h("button",{class:"chip conmini"+(S.console===k.id?" on":""),style:conStyle(k.id),title:k.netplay_note,onclick:()=>{S.console=k.id;go()}},h("span",{class:"cico"},conSprite(k.id,22)),k.name,h("small",{},k.count))))}

/* ================= Console mode ================= */
async function viewConsole(m){
 const d=await api("library",{sort:S.sort});S.lib=d;
 const real=d.consoles.filter(c=>c.count);const consoles=real.length>1?[{id:"all",name:"All",count:d.games.length,maker:"Every console"},...real]:real;
 const E=await api("emulators").catch(()=>({consoles:[]}));const emu=id=>E.consoles.find(c=>c.id===id)||{options:[]};
 let ci=Math.max(0,consoles.findIndex(c=>c.id===S.console)),gi=0;
 const wrap=h("div",{class:"tv"});m.append(wrap);
 const gamesOf=c=>c.id==="all"?d.games:d.games.filter(g=>g.console===c.id);
 let swap=true;
 const render=()=>{
  const c=consoles[ci];const games=c?gamesOf(c):[];gi=Math.min(gi,Math.max(0,games.length-1));
  if(!c){wrap.replaceChildren(h("p",{class:"muted"},"No games yet. Add your games folder in Library."));return}
  wrap.style.cssText=conStyle(c.id);
  const emuNames=[...new Set(games.map(g=>g.emulator).filter(Boolean))];
  const banner=h("div",{class:"conbanner"+(swap?" swap":""),"data-con":c.id},h("div",{class:"bgfx"}),
   h("div",{class:"bsprite"},conSprite(c.id,150,"big",0.9)),
   h("div",{class:"binfo"},h("div",{class:"bmaker"},c.maker||""),h("h2",{},c.name),h("div",{class:"btag"},conInfo(c.id).tag),
    h("div",{class:"bstats"},h("span",{class:"badge"},games.length+" game"+(games.length===1?"":"s")),
     emuNames.length?h("span",{class:"badge good"},"plays in "+emuNames.slice(0,3).join(", ")):h("span",{class:"badge warn"},"no emulator yet"),
     h("span",{class:"p1"},"▶ PLAYER 1 READY"))),
   (c.id!=="all"&&emu(c.id).options.length)?h("label",{class:"bemu small"},"Opens with ",h("select",{"aria-label":"Emulator for "+c.name,onchange:async e=>{const r=await act(()=>api("console_emulator",{console:c.id,emulator:e.target.value||null}));if(r){E.consoles=r.consoles;const f=await api("library",{sort:S.sort});d.games=f.games;render()}}},
      h("option",{value:""},"Automatic"),...emu(c.id).options.map(o=>h("option",{value:o.id,selected:emu(c.id).chosen===o.id},o.name+(o.installed?"":" (not found)"))))):null);
  swap=false;
  wrap.replaceChildren(
   h("div",{class:"conbar"},...consoles.map((x,i)=>conChip(x.id,x.name==="All"?"All":x.name,x.count,i===ci,()=>{ci=i;gi=0;swap=true;S.console=x.id==="all"?null:x.id;render()}))),
   banner,
   games.length?h("div",{class:"tvgrid"},...games.map((g,i)=>h("div",{class:"tvcard"+(i===gi?" sel":""),"data-gid":g.id,style:`--d:${Math.min(i,14)*35}ms;${conStyle(g.console)}`,onclick:()=>{gi=i;render()},ondblclick:()=>play(g)},
     c.id==="all"?h("span",{class:"tvcon",title:consoleName(g.console)},conSprite(g.console,22)):null,coverEl(g,"tv"),h("div",{class:"tvtitle"},g.title),h("div",{class:"small muted"},[g.region,c.id==="all"?consoleName(g.console):null,g.emulator||"no emulator"].filter(Boolean).join(" · "))))):h("p",{class:"muted"},"No games for this console yet."),
   h("p",{class:"small muted tvhelp"},"D-pad or arrows: move · A / Enter: play · Shoulder buttons or [ ]: change console · B / Esc: back to Library · right-click a game for more"));
  const sel=wrap.querySelector(".tvcard.sel");if(sel)sel.scrollIntoView({block:"nearest"});
  const cb=wrap.querySelector(".conchip.on");if(cb)cb.scrollIntoView({block:"nearest",inline:"center"});
 };
 const play=async g=>{const r=await act(()=>api("launch",{id:g.id}));if(r){S.running={title:r.launched}}if(r)toast("Started "+r.launched+" in "+r.emulator)};
 const move=(dx,dy)=>{const c=consoles[ci];if(!c)return;const games=gamesOf(c);const cols=Math.max(1,Math.floor((wrap.clientWidth-20)/180));
  gi=Math.max(0,Math.min(games.length-1,gi+dx+dy*cols));render()};
 const go2=n=>{ci=(ci+n+consoles.length)%consoles.length;gi=0;swap=true;S.console=consoles[ci].id==="all"?null:consoles[ci].id;render()};
 const key=e=>{if(S.tab!=="console"){document.removeEventListener("keydown",key);return}
  if(e.target&&/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;
  const map={ArrowLeft:()=>move(-1,0),ArrowRight:()=>move(1,0),ArrowUp:()=>move(0,-1),ArrowDown:()=>move(0,1),
   Enter:()=>{const c=consoles[ci];const games=c?gamesOf(c):[];if(games[gi])play(games[gi])},
   "[":()=>go2(-1),"]":()=>go2(1),Escape:()=>{S.tab="library";go()}};
  if(document.querySelector(".ctx,.modal"))return;
  if(map[e.key]){e.preventDefault();map[e.key]()}};
 document.addEventListener("keydown",key);
 let last={};
 clearInterval(S.tvTimer);S.tvTimer=setInterval(()=>{if(S.tab!=="console"){clearInterval(S.tvTimer);return}
  const p=livePads()[0];if(!p)return;const prof=(S.P&&S.P.profiles[padKey(p)])||null;const lit=litSlots(p,prof);
  const edge=s=>{const now=lit.has(s);const was=!!last[s];last[s]=now;return now&&!was};
  if(edge(14))move(-1,0);if(edge(15))move(1,0);if(edge(12))move(0,-1);if(edge(13))move(0,1);
  if(edge(0)){const c=consoles[ci];const games=c?gamesOf(c):[];if(games[gi])play(games[gi])}
  if(edge(4))go2(-1);if(edge(5))go2(1);
  if(edge(1)){S.tab="library";go()}},50);
 if(!S.P)S.P=await api("pads").catch(()=>null);
 render();
}

/* ================= Display and video ================= */
const VIDEO_ICON={fullscreen:["Y","YY....YY","Y......Y","........","........","........","........","Y......Y","YY....YY"],
 integer:["C","C.C.C.C.",".C.C.C.C","C.C.C.C.",".C.C.C.C","C.C.C.C.",".C.C.C.C","C.C.C.C.",".C.C.C.C"],
 keep_shape:["N","NNNNNNNN","N......N","N......N","N......N","N......N","N......N","N......N","NNNNNNNN"],
 smooth:["P","...PP...","..PPPP..",".PPPPPP.","PPPPPPPP","PPPPPPPP",".PPPPPP.","..PPPP..","...PP..."],
 vsync:["L","LLLLLLLL","........","LLLLLLLL","........","LLLLLLLL","........","LLLLLLLL","........"]};
const VIDEO_TITLE={fullscreen:"Start full screen",integer:"Sharp pixels",keep_shape:"Keep the game's shape",smooth:"Smooth the picture",vsync:"Wait for the screen (vsync)"};
const VIDEO_PLAIN={fullscreen:"The game fills your whole screen, no window around it.",integer:"Pixels are scaled in whole steps, so they stay perfectly crisp. Black bars may appear.",
 keep_shape:"A 4:3 game stays 4:3 instead of being stretched to fit a wide screen.",smooth:"Softens blocky pixels. Off keeps hard, retro pixels.",vsync:"Waits for your screen's refresh so the picture does not tear. Can add a tiny delay."};
function vIcon(k,size){const rows=VIDEO_ICON[k].slice(1);const col=VIDEO_ICON[k][0];return pixelsC(rows.map(r=>r.replace(/[^.]/g,"W")),size||26,"vicon",{W:PAL[col]})}
/* a little TV that shows what the choices do */
function tvPreview(get){const art=pixels(MARTIN,208,"pvart");
 const win=h("div",{class:"pvwin"},h("span",{},"Legacy Player"),h("b",{},"– □ ✕")),tear=h("div",{class:"pvtear"}),screen=h("div",{class:"pvscreen"},art),frame=h("div",{class:"pvtv"},win,screen,tear);
 const note=h("div",{class:"small muted pvnote"});
 const upd=()=>{const s=get();frame.classList.toggle("full",!!s.fullscreen);win.style.display=s.fullscreen?"none":"flex";
  screen.classList.toggle("stretch",!s.keep_shape);screen.classList.toggle("whole",!!s.integer);art.classList.toggle("soft",!!s.smooth);tear.style.display=s.vsync?"none":"block";
  const bits=[s.fullscreen?"fills the screen":"in a window",s.keep_shape?"keeps its shape":"stretched wide",s.integer?"whole-step pixels":"any size",s.smooth?"smoothed":"crisp pixels",s.vsync?"no tearing":"may tear"];note.textContent="Preview: "+bits.join(" · ")};
 upd();return{el:h("div",{class:"pvbox"},frame,note),update:upd}}
async function viewDisplay(m){
 const d=await api("video");const F=Object.keys(d.fields);
 const defs=()=>{const o={};F.forEach(k=>o[k]=d.defaults[k]!==undefined?d.defaults[k]:d.base[k]);return o};
 const cur=S.dispConsole&&d.consoles.find(c=>c.id===S.dispConsole)?S.dispConsole:null;
 const pvAll=tvPreview(defs);
 const tiles=h("div",{class:"vtiles"},...F.map(k=>{const on=defs()[k];const sw=h("input",{type:"checkbox",checked:on,role:"switch","aria-label":VIDEO_TITLE[k]||d.fields[k].label});
  sw.addEventListener("change",async()=>{d.defaults[k]=sw.checked;pvAll.update();const r=await act(()=>api("video",{scope:"all",key:k,value:sw.checked}));if(r)toast(VIDEO_TITLE[k]+": "+(sw.checked?"on":"off"))});
  return h("label",{class:"vtile"},vIcon(k,30),h("div",{class:"vt"},h("b",{},VIDEO_TITLE[k]||d.fields[k].label),h("span",{class:"small muted"},VIDEO_PLAIN[k]||d.fields[k].help)),h("span",{class:"switch"},sw,h("i",{})))}));
 m.append(h("h2",{},"Display and video"),
  h("div",{class:"why"},"Choose how games look once, and Legacy Player applies it each time a game opens. RetroArch gets every choice. Other emulators only get “start full screen”; their own graphics options (resolution, shaders, 3D) live inside each emulator and it remembers them."),
  h("div",{class:"vgrid"},h("div",{},h("h3",{class:"sect",style:"margin-top:0"},"1. For every console"),tiles),h("div",{},h("h3",{class:"sect",style:"margin-top:0"},"What it looks like"),pvAll.el)),
  h("h3",{class:"sect"},"2. Pick a console to set up differently"),
  h("div",{class:"conbar"},...d.consoles.map(c=>{const own=Object.keys(c.own||{}).length;return conChip(c.id,c.name,null,cur===c.id,()=>{S.dispConsole=cur===c.id?null:c.id;go()},own?h("span",{class:"cust",title:"Has its own choices"},own+" custom"):null)})));
 const c=cur&&d.consoles.find(x=>x.id===cur);
 if(!c){const custom=d.consoles.filter(x=>Object.keys(x.own||{}).length);
  m.append(h("div",{class:"card vhint"},conSprite("all",44),h("div",{},h("b",{},"Everything follows the settings above."),h("div",{class:"small muted"},custom.length?"Customized: "+custom.map(x=>x.name).join(", ")+".":"Pick a console above if one of them should look different."))));return}
 const eff=()=>{const o=defs();F.forEach(k=>{if(c.own[k]!==undefined)o[k]=c.own[k]});return o};
 const pvC=tvPreview(eff);
 const seg=k=>{const applies=(c.applies||[]).includes(k);const own=c.own[k];const dv=defs()[k];
  const opts=[["","Same as default ("+(dv?"on":"off")+")"],["1","On"],["0","Off"]];
  const cur2=own===undefined?"":own?"1":"0";
  return h("div",{class:"vrow"+(applies?"":" off")},vIcon(k,24),h("div",{class:"vt"},h("b",{},VIDEO_TITLE[k]||d.fields[k].label),applies?null:h("span",{class:"small muted"},c.emulator?"Set this inside "+c.emulator+" once.":"No emulator for this console yet.")),
   h("div",{class:"segmented",role:"radiogroup"},...opts.map(([v,l])=>h("button",{type:"button",role:"radio","aria-checked":cur2===v,class:cur2===v?"on":"",disabled:!applies,onclick:async()=>{
     const val=v===""?null:v==="1";if(val===null)delete c.own[k];else c.own[k]=val;await act(()=>api("video",{scope:c.id,key:k,value:val}));go()}},l))))};
 m.append(h("div",{class:"card vpanel",style:conStyle(c.id)},
  h("div",{class:"vphead"},conSprite(c.id,100,"big",0.8),h("div",{class:"grow"},h("div",{class:"bmaker"},"Setting up"),h("h2",{style:"margin:0"},c.name),h("div",{class:"small",style:"opacity:.9"},c.how)),
   h("div",{class:"row"},Object.keys(c.own||{}).length?h("button",{class:"btn",onclick:async()=>{for(const k of Object.keys(c.own)){await api("video",{scope:c.id,key:k,value:null})}toast("Back to the defaults");go()}},"Reset to defaults"):null,
    h("button",{class:"btn",onclick:()=>{S.ctrl=c.id;nav("controllers")}},c.pad_layout_customized?"Controller layout (custom)":"Controller layout"))),
  h("div",{class:"vpbody"},h("div",{},...F.map(seg)),pvC.el)))}

/* ================= a doctor avatar ================= */
AVATARS.doctor={name:"Doctor",rows:["...KKKKKK...","..KKKKKKKK..","..KSSSSSSK..","..SEESSEES..","..SSSSSSSS..","..SSDDDDSS..","...SSSSSS...",".WWWWGGWWWW.","WWWGWWWWGWWW","WWWGWWWWGRWW","WWWWGGGGWRRR","WWWWWWWWWWRW"]};

/* ================= uninstalling a game ================= */
async function uninstallGame(g){
 const plan=await act(()=>api("game_uninstall",{id:g.id}));if(!plan)return;
 const delSaves=h("input",{type:"checkbox"}),perm=h("input",{type:"checkbox"});
 const close=()=>ov.remove();const err=h("div",{class:"small bad",role:"alert",style:"margin-top:8px"});
 const hasSaves=plan.saves.length||plan.backups;
 const ov=h("div",{class:"modal",role:"dialog","aria-modal":"true",onclick:e=>{if(e.target===ov)close()}},h("div",{class:"modalbox wide"},
  h("h3",{style:"margin:0 0 6px"},"Uninstall "+plan.title+"?"),
  h("p",{class:"small muted",style:"margin:0 0 10px"},"These files will be removed from your computer ("+plan.total_mb+" MB). They go to the Recycle Bin first, so you can still get them back from there."),
  h("div",{class:"unlist"},...plan.files.map(f=>h("div",{class:"unrow"},h("b",{},f.name),h("span",{class:"small muted"},f.mb+" MB · "+f.folder)))),
  hasSaves?h("label",{class:"unopt"},delSaves,h("span",{},h("b",{},"Also delete my save files for this game"),h("span",{class:"small muted"}," ("+plan.saves.length+" save file"+(plan.saves.length===1?"":"s")+", "+plan.backups+" backup file"+(plan.backups===1?"":"s")+")"),
    h("div",{class:"small warn"},"Leave this off to keep your progress in case you reinstall the game later.")))
   :h("p",{class:"small muted"},"No save files were found for this game."),
  h("label",{class:"unopt small"},perm,h("span",{},"Delete permanently instead of using the Recycle Bin (cannot be undone)")),
  h("p",{class:"small muted"},"Only want it out of sight? Use “Hide from library” instead; that keeps the file."),err,
  h("div",{class:"row",style:"justify-content:flex-end;gap:8px;margin-top:12px"},h("button",{class:"btn",onclick:close},"Cancel"),
   h("button",{class:"btn bad",onclick:async()=>{err.textContent="";let r;try{r=await api("game_uninstall",{id:g.id,confirm:true,delete_saves:delSaves.checked,permanent:perm.checked})}catch(e){err.textContent=e.message;toast(e.message,"err");return}
     close();toast("Uninstalled "+r.removed+" ("+r.where+")"+(r.saves_kept?". Your "+r.saves_kept+" save file"+(r.saves_kept===1?"":"s")+" stayed.":"."));
     document.querySelectorAll(".modal,.scrim,.drawer").forEach(x=>x.remove());refreshAfter()}},"Uninstall"))));
 document.body.append(ov)}

/* ================= closing the clinic: uninstalling Legacy Player itself ================= */
const RETIRE_LINES={emulators:"Sweeping out the waiting room...",library:"Shredding the paperwork...",saves:"Clearing the save shelves...",logs:"Wiping the clipboard...",program:"Locking up the clinic..."};
async function retireClinic(){
 const plan=await act(()=>api("self_uninstall",{}));if(!plan)return;
 const keep=h("input",{type:"checkbox",checked:true}),prog=h("input",{type:"checkbox",checked:true});
 const doc=h("div",{class:"docspot retiredoc"},pixels(doctorRows("worried"),104,"doctor worried"));
 const say=h("div",{class:"retiresay"},"Leaving already? I'll clean up properly so nothing is left behind. Your games stay untouched. Here's what I'll tidy:");
 const body=h("div",{class:"retirebody"});
 const ov=h("div",{class:"modal",role:"dialog","aria-modal":"true"},h("div",{class:"modalbox wide retire"},
  h("div",{class:"retirehead"},doc,say),body));
 const close=()=>ov.remove();
 const item=(i)=>h("div",{class:"unrow rrow","data-k":i.key},h("span",{class:"rmark"},"•"),h("div",{class:"grow"},h("b",{},i.label),h("div",{class:"small muted"},i.why)),h("span",{class:"small muted rsize"},i.mb?i.mb+" MB":""));
 const mark=(k,txt,cls)=>{const r=body.querySelector(`[data-k="${k}"]`);if(!r)return;r.classList.add(cls);r.querySelector(".rmark").textContent=txt};
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const saves=plan.items.find(i=>i.key==="saves"),program=plan.items.find(i=>i.key==="program");
 body.append(h("div",{class:"unlist"},...plan.items.map(item)),
  saves?h("label",{class:"unopt"},keep,h("span",{},h("b",{},"Keep my game saves and backups"),h("div",{class:"small muted"},"Recommended. Saves stay in "+plan.data_dir+" so your progress is safe if you come back. Untick to delete them too (cannot be undone)."))):"",
  program&&program.available?h("label",{class:"unopt small"},prog,h("span",{},"Also remove the Legacy Player program file (it goes when the window closes)")):"",
  h("p",{class:"small muted"},"Never touched: your game files, emulators you installed yourself"+(plan.never_touched.length?", "+plan.never_touched.map(x=>x.label.toLowerCase()+" ("+x.path+")").join(", "):"")+"."),
  h("div",{class:"row",style:"justify-content:flex-end;gap:8px;margin-top:12px"},h("button",{class:"btn",onclick:close},"Never mind"),
   h("button",{class:"btn bad",onclick:()=>run()},"Start the clean-up")));
 async function run(){
  const keepSaves=!saves||keep.checked,rmProg=!!(program&&program.available&&prog.checked);
  if(saves&&!keepSaves&&!(await ask("Your save files and backups will be gone for good. Delete them too?","Delete them")))return;
  body.querySelectorAll("button,input").forEach(x=>x.disabled=true);
  body.querySelectorAll(".unopt,:scope>.row,:scope>p").forEach(x=>x.remove());
  doc.replaceChildren(pixels(doctorRows("happy"),104,"doctor happy"));doc.classList.add("working");
  say.textContent="Gloves on. This won't take long!";
  const r=await act(()=>api("self_uninstall",{confirm:true,keep_saves:keepSaves,remove_program:rmProg}));
  if(!r){close();return}
  if(r.server_stopped){await wait(500);say.textContent="Switching off your server first so nothing is left running..."}
  for(const s of r.steps){await wait(650);say.textContent=s.status==="kept"?"Your saves go in a safe box. They stay.":(RETIRE_LINES[s.key]||"Tidying...");
   mark(s.key,s.status==="kept"?"♥":s.status==="problem"?"!":"✓",s.status==="kept"?"rkept":s.status==="problem"?"rprob":"rdone");
   if(s.status==="after_close"){const row=body.querySelector(`[data-k="${s.key}"] .rsize`);if(row)row.textContent="when closing"}}
  await wait(700);doc.classList.remove("working");
  const ok=!r.problems.length;
  doc.replaceChildren(pixels(doctorRows(ok?"happy":"worried"),104,"doctor "+(ok?"happy":"worried")));
  say.textContent=ok?"All clean! It was a pleasure treating you. Now go home and play some video games.":"Almost all clean, but a few things wouldn't budge. The notes are below.";
  const line=(a,b,warn)=>h("div",{class:warn?"w":""},a+": "+b);
  body.replaceChildren(h("div",{class:"discharge"},h("div",{class:"retro"},
    h("div",{class:"hd"},"Discharge report"),
    ...r.steps.map(s=>line(s.label.replace(/^The /,""),s.status==="kept"?"kept safe":s.status==="removed"?"removed":s.status==="after_close"?"leaves when you close":s.status==="skipped"?"not applicable":"needs a hand",s.status==="problem")),
    r.server_stopped?line("Your server","stopped first"):"",
    line("Space freed",r.freed_mb+" MB"),
    r.kept_saves?line("Saves","kept in "+plan.data_dir):line("Saves","deleted"),
    line("Your games","untouched")),
   h("div",{class:"stamp2 "+(ok?"ok":"warn")},ok?"UNINSTALL SUCCESSFULLY COMPLETED":"COMPLETED WITH NOTES")),
   r.problems.length?h("div",{class:"small warn",style:"margin-top:10px"},"Could not remove (maybe in use): "+r.problems.slice(0,5).join("; ")+". You can delete those by hand."):null,
   h("p",{class:"small muted"},r.program_pending?"Press the button below. Legacy Player closes and the doctor removes the last pieces a few seconds later.":"Press the button below to close Legacy Player."),
   h("div",{class:"row",style:"justify-content:flex-end;margin-top:10px"},h("button",{class:"btn primary",onclick:async()=>{try{await api("quit",{})}catch(e){}
     document.body.replaceChildren(h("div",{class:"byebye"},pixels(doctorRows("happy"),120,"doctor happy"),h("h2",{},"Legacy Player has been uninstalled"),h("p",{class:"muted"},"You can close this window. Thanks for playing!")));try{window.close()}catch(e){}}},"Close Legacy Player")))}
 document.body.append(ov)}
