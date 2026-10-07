
/* ================= controller + keyboard status, keyboard layouts ================= */
function kbKeyName(e){const c=e.code||"",k=e.key||"";
 if(/^Key[A-Z]$/.test(c)||/^[a-zA-Z]$/.test(k))return(/^[a-zA-Z]$/.test(k)?k:c.slice(3)).toLowerCase();
 if(/^[0-9]$/.test(k))return"num"+k;if(/^Digit[0-9]$/.test(c))return"num"+c.slice(5);
 return({ArrowUp:"up",ArrowDown:"down",ArrowLeft:"left",ArrowRight:"right",Enter:"enter",Space:"space",Backspace:"backspace",Tab:"tab",ShiftLeft:"shift",ShiftRight:"rshift",ControlLeft:"ctrl",ControlRight:"rctrl",AltLeft:"alt",AltRight:"ralt"})[c]||null}
const KEYLABEL={up:"↑",down:"↓",left:"←",right:"→",enter:"Enter",space:"Space",backspace:"Backspace",tab:"Tab",shift:"Left Shift",rshift:"Right Shift",ctrl:"Left Ctrl",rctrl:"Right Ctrl",alt:"Left Alt",ralt:"Right Alt"};
const keyLabel=k=>KEYLABEL[k]||(/^num\d$/.test(k)?k.slice(3):k.toUpperCase());
async function loadKb(){try{S.kb=await api("keyboard",{})}catch(e){}paintInput()}
function paintInput(){const el=$("#inpill");if(!el)return;const ps=livePads(),kbn=S.kb?S.kb.name:"Classic (arrow keys)",kbs=S.kb&&S.kb.layout==="wasd"?"WASD":S.kb&&S.kb.layout==="custom"?"Custom":"Arrows";
 el.classList.toggle("ok",!!ps.length);el.classList.toggle("off",!ps.length);
 $("#intxt").textContent=ps.length?"Pad: "+padPrettyName(ps[0].id).slice(0,16)+(ps.length>1?" +"+(ps.length-1):""):"No pad · "+kbs+" keys";
 el.title=ps.length?ps.length+" controller"+(ps.length>1?"s":"")+" connected. Click to manage controllers and keyboard keys.":"No controller detected. If one is plugged in, press a button on it first. You can play with the keyboard ("+kbn+" layout). Click to change it."}
(function(){let last=-1;
 addEventListener("gamepadconnected",e=>{paintInput();toast("Controller connected: "+padPrettyName(e.gamepad.id).slice(0,40))});
 addEventListener("gamepaddisconnected",e=>{paintInput();toast("Controller disconnected: "+padPrettyName(e.gamepad.id).slice(0,40)+". The keyboard layout takes over.","warn")});
 setInterval(()=>{const n=livePads().length;if(n!==last){last=n;paintInput()}},2500);
 setTimeout(()=>{const el=$("#inpill");if(el)el.onclick=()=>nav("controllers");loadKb()},0)})();
document.addEventListener("selectstart",e=>{const t=e.target&&e.target.closest?e.target:e.target&&e.target.parentElement;if(t&&t.closest&&t.closest(".office,.docspot,.martin,.pet,#brand,.byebye"))e.preventDefault()});

function kbSection(){
 const box=h("div",{class:"card kbbox"});
 const draw=k=>{S.kb=k;paintInput();
  const picked=k.layout;
  const keysRow=k.roles.map(r=>{const b=h("button",{class:"keycap",type:"button",title:"Click, then press the key you want",onclick:()=>learn(r.id,b)},keyLabel(k.keys[r.id]));
   return h("div",{class:"kbrow"},h("span",{},r.name),b)});
  box.replaceChildren(
   h("p",{class:"small muted",style:"margin:0 0 10px"},"Player 1 can play from the keyboard when no controller is plugged in (or alongside one). Pick a layout, or click a key below and press the one you want. Works with RetroArch."),
   h("div",{class:"row",style:"gap:8px;margin-bottom:6px"},...Object.entries(k.presets).map(([id,p])=>h("button",{class:"btn"+(picked===id?" primary":""),onclick:async()=>{const r=await act(()=>api("keyboard",{layout:id}),"Keyboard layout: "+p.label);if(r)draw(r)}},p.label)),
    h("span",{class:"badge"},picked==="custom"?"your own keys":"preset")),
   picked!=="custom"&&k.presets[picked]?h("p",{class:"small muted",style:"margin:0 0 8px"},k.presets[picked].note):"",
   h("div",{class:"kbgrid"},...keysRow))};
 const learn=(role,btn)=>{btn.textContent="Press a key…";btn.classList.add("learning");
  const off=()=>{removeEventListener("keydown",on,true);btn.classList.remove("learning")};
  const on=async e=>{e.preventDefault();e.stopPropagation();
   if(e.key==="Escape"){off();draw(S.kb);return}
   const name=kbKeyName(e);if(!name){toast("That key can't be used. Try a letter, number, arrow, Enter, Space, Tab, Shift, Ctrl or Alt.","warn");return}
   off();const keys={...S.kb.keys},old=keys[role];
   const other=Object.keys(keys).find(r=>r!==role&&keys[r]===name);if(other)keys[other]=old;   // swap so no two buttons share a key
   keys[role]=name;const r=await act(()=>api("keyboard",{layout:"custom",keys}));draw(r||S.kb)};
  addEventListener("keydown",on,true)};
 api("keyboard",{}).then(draw);return box}
function inputBanner(){const ps=livePads(),kb=S.kb;
 return h("div",{class:"inbanner "+(ps.length?"ok":"warn")},ps.length?"Controller connected: "+ps.map(p=>padPrettyName(p.id).slice(0,40)).join(", "):"No controller detected. Plug one in and press a button on it, or play with the keyboard ("+(kb?kb.name:"Classic")+" layout, set below).")}

/* ================= finding box art, with options when it isn't available ================= */
function findArt(g,opts){opts=opts||{};closeModals();
 const close=()=>{removeEventListener("paste",onPaste);ov.remove()};
 const onPaste=async e=>{const it=[...(e.clipboardData&&e.clipboardData.items||[])].find(i=>i.type.startsWith("image/"));if(!it)return;e.preventDefault();
  const f=it.getAsFile();close();await setCoverFile(g,f)};
 const opt=(t,d,fn,extra)=>h("button",{class:"artopt",type:"button",onclick:fn},h("b",{},t),h("span",{class:"small muted"},d),extra||"");
 const q=encodeURIComponent(g.title+" "+consoleName(g.console)+" box art");
 const ov=h("div",{class:"modal tipmodal",onclick:e=>{if(e.target===ov)close()}},h("div",{class:"modalbox wide"},
  h("h3",{style:"margin:0 0 4px"},"Find box art for "+g.title),
  h("p",{class:"small muted",style:"margin:0 0 12px"},opts.tried?"The picture library doesn't have this one under that name. Here are other ways to get a picture:":"Choose how you'd like to get a picture:"),
  h("div",{class:"artopts"},
   opt(opts.tried?"Try the online library again":"Look it up online","Asks thumbnails.libretro.com using only the game's name.",()=>{close();fetchOneCover(g,{again:true})}),
   opt("Choose a picture file","Pick an image from this computer (PNG, JPG, WEBP or GIF).",()=>{close();pickCover(g)}),
   opt("Paste a picture","Copy any image in your browser (right-click, Copy image), then press Ctrl+V right here.",()=>{toast("Ready. Press Ctrl+V to paste your picture.","")}),
   h("a",{class:"artopt",href:"https://duckduckgo.com/?q="+q+"&iax=images&ia=images",target:"_blank",rel:"noopener noreferrer"},h("b",{},"Search the web for it"),h("span",{class:"small muted"},"Opens an image search in your browser. Copy or save the one you like, then paste or choose it here.")),
   opt("Keep the plain "+consoleName(g.console)+" card","No picture is fine. The card shows the console's colors.",close)),
  h("div",{class:"row",style:"justify-content:flex-end;margin-top:12px"},h("button",{class:"btn",onclick:close},"Close"))));
 addEventListener("paste",onPaste);document.body.append(ov)}
async function fetchOneCover(g,o){
 const s=await api("settings");S.settings=s.values;if(!allowNet()){netTipModal();return}
 if(!(o&&o.again)&&!await ask("Ask thumbnails.libretro.com for the box art of "+g.title+"? Only this game's name is sent. The picture is kept on this computer.","Get box art"))return;
 let v=await act(()=>api("game_fetch_cover",{id:g.id,consent:true}));if(!v)return;
 for(let i=0;i<30&&v.state==="running";i++){await new Promise(r=>setTimeout(r,800));v=await api("covers",{}).catch(()=>({state:"error"}))}
 if(v.found){toast("Got the box art.");refreshAfter()}else findArt(g,{tried:true})}
async function homeArtTip(){
 if(S.tab!=="home")return;const d=await api("home").catch(()=>null);if(!d||S.tab!=="home")return;
 const g=(d.recent||[]).find(x=>!x.cover);if(!g||S.artTipOff===g.id||$(".arttip"))return;
 const head=[...document.querySelectorAll("#main h2,#main h3")].find(x=>/Recent games/.test(x.textContent));if(!head)return;
 head.after(h("div",{class:"startip inline arttip",role:"note"},pixels(AVATARS.star.rows,28,"twinkle"),h("div",{class:"bub"},
  "No box art for "+g.title+" yet.",h("div",{class:"row",style:"gap:6px"},h("button",{class:"btn",onclick:()=>{GAMES[g.id]=GAMES[g.id]||g;findArt(g)}},"Find art"),
   h("button",{class:"btn",onclick:e=>{S.artTipOff=g.id;e.target.closest(".arttip").remove()}},"Not now")))))}
