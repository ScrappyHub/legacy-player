import re
js=rep(js,'return h("div",{class:"game",tabindex:0,role:"button",onclick:()=>openGame(g.id)','return h("div",{class:"game","data-gid":g.id,tabindex:0,role:"button",onclick:()=>openGame(g.id)')
js=rep(js,'h("div",{class:"tvcard"+(i===gi?" sel":""),onclick:()=>{gi=i;render()},ondblclick:()=>play(g)}','h("div",{class:"tvcard"+(i===gi?" sel":""),"data-gid":g.id,onclick:()=>{gi=i;render()},ondblclick:()=>play(g)}')
js=rep(js,'const d=S.lib=await api("library",{console:S.console,q:S.q,favorites:S.fav,sort:S.sort});\n const st=','const d=S.lib=await api("library",{console:S.console,q:S.q,favorites:S.fav,sort:S.sort,collection:S.collection,hidden:S.showHidden});\n const st=')
js=rep(js,'async function refreshGrid(){const d=S.lib=await api("library",{console:S.console,q:S.q,favorites:S.fav,sort:S.sort});','async function refreshGrid(){const d=S.lib=await api("library",{console:S.console,q:S.q,favorites:S.fav,sort:S.sort,collection:S.collection,hidden:S.showHidden});')
js=rep(js,' m.append(h("div",{class:"chips",id:"chips"}));',' m.append(h("div",{class:"chips",id:"chips"}),h("div",{class:"chips",id:"colchips",style:"margin-top:4px"}));')
js=rep(js,'function drawChips(d){const c=$("#chips");','function drawChips(d){drawCols(d);const c=$("#chips");')
_m=re.search(r'async function viewSetup\(m\)\{\n clearInterval\(S\.setupTimer\);\n const root=h\("div",\{\}\);m\.append\(h\("h2",\{\},"Setup"\),\n  h\("div",\{class:"why"\},"[^\n]*"\),root\);',js)
assert _m
js=js[:_m.start()]+'async function viewSupplies(m){\n clearInterval(S.setupTimer);\n const root=h("div",{});m.append(root);'+js[_m.end():]
js=rep(js,'const st=S.settings||(S.settings=(await api("settings")).values);\n document.documentElement.dataset.theme=st.theme;\n if(!d.roots.length)','const st=S.settings=(await api("settings")).values;\n document.documentElement.dataset.theme=st.theme;\n if(!d.roots.length)')
js=rep(js,"it never copies, moves, or edits your files.","it never copies or edits your files, and only removes a game if you choose Uninstall.")

js=rep(js,'  coverBtn(),h("button",{class:"btn",onclick:rescan},"Rescan")));','  h("button",{class:"btn",onclick:rescan},"Rescan")));')
js=rep(js,' drawChips(d);drawGrid(d);\n}',' drawChips(d);drawGrid(d);\n m.append(h("div",{class:"libfoot"},coverBtn(),h("span",{class:"small muted"},"Box art is looked up by game name. If a game has none, right-click it to find or add a picture.")));\n}')
js=rep(js,'  h("h3",{},"Live test"),live,','  h("h3",{},"Keyboard"),kbSection(),\n  h("h3",{},"Live test"),live,')
js=rep(js,'  h("h3",{},"Your controllers"),padsBox,wizBox,','  inputBanner(),h("h3",{},"Your controllers"),padsBox,wizBox,')

js=rep(js,'  h("div",{class:"row"},h("button",{class:"btn primary",onclick:()=>srvAct("start")},"Start")','  st.online?h("div",{class:"inbanner ok"},"Your server is running. Closing this window with X keeps Legacy Player in the tray (notification area) so it stays managed; right-click the tray icon to stop it, copy a fresh server code or exit."):"",\n  h("div",{class:"row"},h("button",{class:"btn primary",onclick:()=>srvAct("start")},"Start")')

js=rep(js,"""h("div",{class:"row"},h("label",{class:"small"},"Players per room ",players),h("label",{class:"small"},"Rooms ",rooms),h("label",{class:"small"},"Waiting line ",line)),""","""h("div",{class:"fieldrow"},fld("Players per room",players),fld("Rooms",rooms),fld("Waiting line",line)),""")
js=rep(js,"""h("div",{class:"row",style:"margin-top:8px"},h("label",{class:"small"},"Address friends use ",pub)),""","""h("div",{class:"fieldrow",style:"margin-top:10px"},fld("Address friends use",pub)),""")
js=rep(js,"""placeholder:"blank = this computer's home-network address",style:"width:min(280px,100%)\"""","""placeholder:"blank = this computer's home-network address",style:"width:min(380px,100%)\"""")

js=rep(js,"""const showCode=async()=>{const c=await act(()=>api("server_code",{}));if(!c)return;""","""const showCode=async refresh=>{if(refresh===true&&!await ask("Make a fresh server code? The old code stops working for new people. Everyone already connected stays connected.","Make a fresh code"))return;
  const c=await act(()=>api("server_code",{refresh:refresh===true}));if(!c)return;if(c.rotated)toast("Fresh code made. Players already connected stay connected.");""")
js=rep(js,"""h("button",{class:"btn",onclick:()=>copyText(c.code)},"Copy")),""","""h("button",{class:"btn",onclick:()=>copyText(c.code)},"Copy"),h("button",{class:"btn",title:"Stops the old code working for new people. Anyone already connected stays connected.",onclick:()=>showCode(true)},"Make a fresh code")),""")
js=rep(js,"""h("div",{class:"row"},h("button",{class:"btn primary",onclick:showCode},"Make my server code")),codeBox));""","""h("div",{class:"row"},h("button",{class:"btn primary",onclick:()=>showCode(false)},"Make my server code")),codeBox));""")
js=rep(js,"""const codeBox=h("div",{});""","""const codeBox=h("div",{style:"margin-top:16px"});""")

js=rep(js,"""h("p",{class:"small muted"},c.reach)""","""h("p",{class:"small muted"},c.reach),h("p",{class:"small muted"},"Made a code by mistake, or shared it too widely? Make a fresh one: the old code stops working for new people, while players already connected stay connected until they leave or something fails.")""")
