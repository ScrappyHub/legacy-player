/* ---------- cover art ---------- */
function coverEl(g,cls){
 if(g.cover)return h("img",{class:"cv "+(cls||""),src:"/cover/"+encodeURIComponent(g.id)+".png?t="+encodeURIComponent(TOKEN),alt:"",loading:"lazy"});
 const init=consoleName(g.console).replace(/[^A-Z0-9]/g,"")||consoleName(g.console).slice(0,3).toUpperCase();
 return h("div",{class:"cv blank "+(cls||""),"data-c":g.console},h("span",{},init.slice(0,4)))}
async function fetchCovers(){
 if(!await ask("Get cover art? Legacy Player asks thumbnails.libretro.com (the picture library RetroArch uses) for each game's box art by its name. Only game names are sent. Pictures are kept on this computer and it runs in the background.","Get cover art"))return;
 const first=await act(()=>api("covers",{action:"start",consent:true}));if(!first)return;
 const id="covtoast";let v=first;
 while(v.state==="running"){const old=$("#"+id);if(old)old.remove();$("#toasts").append(h("div",{class:"toast",id})) ;$("#"+id).append(h("span",{class:"spin"}),"Getting cover art… "+v.done+" of "+v.total+" ("+v.found+" found)");
  await new Promise(r=>setTimeout(r,1500));v=await api("covers",{}).catch(()=>({state:"error"}))}
 const old=$("#"+id);if(old)old.remove();
 toast(v.state==="done"?"Cover art finished: "+v.found+" new, "+v.have+" in total.":"Cover art stopped.",v.found?"":"warn");go()}

/* ---------- Display and video ---------- */
async function viewDisplay(m){
 const d=await api("video");const F=Object.entries(d.fields);
 const eff=(v)=>v?"On":"Off";const def=k=>d.defaults[k]!==undefined?d.defaults[k]:d.base[k];
 const defRow=h("div",{},...F.map(([k,f])=>h("div",{style:"margin:8px 0"},h("label",{},h("input",{type:"checkbox",checked:(d.defaults[k]!==undefined?d.defaults[k]:d.base[k]),onchange:async e=>{await act(()=>api("video",{scope:"all",key:k,value:e.target.checked}),"Saved");go()}})," "+f.label),h("div",{class:"small muted"},f.help))));
 const cell=(c,k)=>{const own=c.own[k];return h("select",{"aria-label":c.name+" "+k,onchange:async e=>{const v=e.target.value;await act(()=>api("video",{scope:c.id,key:k,value:v===""?null:v==="1"}));go()}},
   h("option",{value:"",selected:own===undefined},"Default ("+eff(def(k))+")"),h("option",{value:"1",selected:own===true},"On"),h("option",{value:"0",selected:own===false},"Off"))};
 m.append(h("h2",{},"Display and video"),
  h("div",{class:"why"},"Pick how games should look once, here. Legacy Player applies it every time it opens a game: fully for RetroArch, and the start-up full-screen option for the emulators that have one. Where an emulator keeps its own graphics settings (resolution, shaders, 3D scaling), you set those inside the emulator once and it remembers; the table says which is which."),
  h("div",{class:"card"},h("h3",{style:"margin-top:0"},"For every console"),defRow),
  h("div",{class:"card",style:"margin-top:14px"},h("h3",{style:"margin-top:0"},whyInline("One console different?","Pick On or Off for a console to override the choice above for just that console. Default follows the choice above.")),
   h("div",{style:"overflow-x:auto"},h("table",{},h("thead",{},h("tr",{},h("th",{},"Console"),...F.map(([k,f])=>h("th",{},f.label)),h("th",{},"Controls"))),
    h("tbody",{},...d.consoles.map(c=>h("tr",{},h("td",{},h("b",{},c.name),h("div",{class:"small muted"},c.how)),...F.map(([k])=>h("td",{},c.emulator?cell(c,k):h("span",{class:"muted small"},"–"))),
     h("td",{},h("button",{class:"btn",onclick:()=>{S.ctrl=c.id;nav("controllers")}},c.pad_layout_customized?"Custom layout":"Open")))))))));
}

/* ---------- Saves: backups ---------- */
function backupsCard(B){
 const inp=h("input",{type:"text",value:B.custom?B.folder:"",placeholder:B.folder,style:"min-width:min(480px,100%)"});
 const setFolder=async v=>{const r=await act(()=>api("backups",{folder:v}),v?"Backups will be stored there":"Back to the default folder");if(r)go()};
 return h("div",{class:"card",style:"margin-top:12px"},h("h3",{style:"margin-top:0"},whyInline("Backups","A backup is one zip file with every save file from every console, stamped with the date. Keep them in the default folder, or point this at a USB drive, another disk or a synced folder (OneDrive, Dropbox) to store them somewhere safer. Restoring zips whatever is there now first, so it can never cost you progress.")),
  h("div",{class:"row"},h("button",{class:"btn primary",onclick:async()=>{const r=await act(()=>api("backup_all"));if(r){toast("Backed up "+r.files+" save file"+(r.files===1?"":"s")+" from "+r.consoles+" console"+(r.consoles===1?"":"s"));go()}}},"Back up all saves now"),
   h("span",{class:"small muted"},"Backups are kept in: "+B.folder)),
  h("div",{class:"row",style:"margin-top:10px"},inp,h("button",{class:"btn",onclick:()=>setFolder(inp.value.trim())},"Store backups here"),B.custom?h("button",{class:"btn",onclick:()=>setFolder("")},"Use the default folder"):null),
  B.backups.length?h("table",{style:"margin-top:10px"},h("thead",{},h("tr",{},["Backup","When","Consoles","Files","Size",""].map(t=>h("th",{},t)))),
   h("tbody",{},...B.backups.map(b=>h("tr",{},h("td",{class:"small"},b.name),h("td",{},new Date(b.made*1000).toLocaleString()),h("td",{class:"small"},b.consoles.join(", ")),h("td",{},String(b.files)),h("td",{},fmtBytes(b.bytes)),
    h("td",{},h("button",{class:"btn",onclick:async()=>{if(!await ask("Restore this backup? Every save file in it goes back to its console's save folder. What is there now is zipped and kept first.","Restore"))return;const r=await act(()=>api("restore_all",{name:b.name}));if(r){toast("Restored "+r.restored+" file"+(r.restored===1?"":"s")+(r.safety_backup?". Your previous saves were kept as "+r.safety_backup:""));go()}}},"Restore"))))))
   :h("p",{class:"small muted",style:"margin-top:10px"},"No whole-library backups yet."))}

/* ---------- Pick a game: console first, then game, only what you can actually play ---------- */
function gamePicker(games){
 let list=games.filter(g=>g.emulator);const note=list.length?null:"None of your games has an emulator ready yet, so all of them are listed. The doctor on Home can tell you what is missing.";if(!list.length)list=games;
 const cons=[...new Set(list.map(g=>g.console))];
 const start=S.joinGame&&list.find(g=>g.id===S.joinGame);
 const cs=h("select",{"aria-label":"Console"},...cons.map(c=>h("option",{value:c,selected:start?start.console===c:false},consoleName(c)+" ("+list.filter(g=>g.console===c).length+")")));
 const q=h("input",{type:"search",placeholder:"Search this console","aria-label":"Search games",style:"width:200px"});
 const sel=h("select",{"aria-label":"Game",style:"min-width:min(320px,100%)"});
 const fill=()=>{const t=q.value.toLowerCase();sel.replaceChildren(...list.filter(g=>g.console===cs.value&&(!t||g.title.toLowerCase().includes(t))).map(g=>h("option",{value:g.id,selected:start&&g.id===start.id},g.title+(g.region?" ("+g.region+")":"")+(g.emulator?" · "+g.emulator:""))))};
 cs.addEventListener("change",()=>{q.value="";fill()});q.addEventListener("input",fill);fill();
 return{sel,el:h("div",{},h("div",{class:"row"},h("label",{class:"small"},"1. Console ",cs),h("label",{class:"small"},"Find ",q)),h("div",{class:"row",style:"margin-top:6px"},h("label",{class:"small"},"2. Game ",sel)),note?h("p",{class:"small warn"},note):null)}}
