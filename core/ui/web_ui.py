"""
VECTOR Web Dashboard — FastAPI router serving the browser UI.

Mounted at /ui on the existing FastAPI server (core/main.py).
Zero npm, zero Node.js, zero external dependencies.
Single-file HTML dashboard with VECTOR dark theme.

Access: http://127.0.0.1:8000/ui
"""

__all__ = [
    "dashboard",
    "router",
    "web_agents",
    "web_arxiv",
    "web_chat",
    "web_chat_ws",
    "web_devto",
    "web_github",
    "web_goals",
    "web_hn",
    "web_karpathy",
    "web_memory",
    "web_search",
    "web_tasks",
    "web_tasks_cancel",
    "web_tasks_submit",
]


from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from loguru import logger

from core.config import CONFIG

router = APIRouter(prefix="/ui", tags=["ui"])

_VERSION = CONFIG.get("version", "1.0.0")
_OWNER = CONFIG.get("owner_name", "Arghyadeep")

# â”€â”€ HTML dashboard (single file, no template engine needed) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>VECTOR</title>
  <style>
    :root{--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--border:#30363d;
          --green:#00ff41;--cyan:#39d353;--text:#e6edf3;--dim:#8b949e;
          --red:#f85149;--yellow:#e3b341;}
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:var(--bg);color:var(--text);font-family:'JetBrains Mono','Fira Code','Courier New',monospace;
         font-size:13px;height:100vh;display:flex;flex-direction:column}
    header{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 20px;
           display:flex;align-items:center;gap:16px;flex-shrink:0}
    .logo{font-size:18px;font-weight:700;color:var(--green);letter-spacing:4px}
    .version{color:var(--dim);font-size:11px}
    .header-status{margin-left:auto;display:flex;gap:12px;align-items:center}
    .badge{padding:2px 8px;border-radius:4px;font-size:11px;border:1px solid var(--border)}
    .badge.green{border-color:var(--green);color:var(--green)}
    .badge.yellow{border-color:var(--yellow);color:var(--yellow)}
    .badge.red{border-color:var(--red);color:var(--red)}
    .main{display:grid;grid-template-columns:200px 1fr 260px;flex:1;overflow:hidden}
    .sidebar{background:var(--bg2);border-right:1px solid var(--border);overflow-y:auto;padding:10px 0}
    .sidebar-section{padding:8px 14px 3px;color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:1px}
    .nav-item{padding:6px 14px;cursor:pointer;color:var(--dim);border-left:2px solid transparent;transition:all .15s}
    .nav-item:hover,.nav-item.active{color:var(--text);background:var(--bg3);border-left-color:var(--green)}
    .nav-item.active{color:var(--green)}
    .content{display:flex;flex-direction:column;overflow:hidden}
    .tab-bar{background:var(--bg2);border-bottom:1px solid var(--border);display:flex;flex-shrink:0}
    .tab{padding:8px 16px;cursor:pointer;color:var(--dim);border-bottom:2px solid transparent;font-size:12px}
    .tab:hover{color:var(--text)}.tab.active{color:var(--green);border-bottom-color:var(--green)}
    .panel{flex:1;overflow-y:auto;padding:16px;display:none}
    .panel.active{display:block}
    #chat-panel{display:none;flex-direction:column;flex:1;overflow:hidden}
    #chat-panel.active{display:flex}
    #chat-messages{flex:1;overflow-y:auto;padding:14px}
    .msg{margin-bottom:10px;padding:9px 12px;border-radius:6px;max-width:85%;line-height:1.5}
    .msg.user{background:var(--bg3);border:1px solid var(--border);margin-left:auto;color:var(--cyan)}
    .msg.vector{background:rgba(0,255,65,.05);border:1px solid rgba(0,255,65,.2)}
    .msg-label{font-size:10px;color:var(--green);font-weight:700;margin-bottom:5px}
    .msg.sys{color:var(--dim);font-size:11px;font-style:italic;background:none;border:none;padding:3px 0}
    #chat-bar{background:var(--bg2);border-top:1px solid var(--border);padding:10px 14px;
              display:flex;gap:8px;flex-shrink:0}
    #chat-in{flex:1;background:var(--bg3);border:1px solid var(--border);border-radius:6px;
             color:var(--text);padding:8px 10px;font-family:inherit;font-size:13px;outline:none;resize:none}
    #chat-in:focus{border-color:var(--green)}
    #send-btn{background:var(--green);color:var(--bg);border:none;border-radius:6px;padding:8px 14px;
              cursor:pointer;font-family:inherit;font-weight:700;font-size:12px}
    #send-btn:disabled{opacity:.4;cursor:not-allowed}
    .right-panel{background:var(--bg2);border-left:1px solid var(--border);overflow-y:auto;padding:14px}
    .card{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:10px;margin-bottom:10px}
    .card-title{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--green);margin-bottom:7px}
    .hp-bar{background:var(--bg);border-radius:3px;height:5px;margin:3px 0;overflow:hidden}
    .hp-fill{height:100%;background:var(--green);border-radius:3px;transition:width .3s}
    .stat-row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--border);font-size:12px}
    .stat-row:last-child{border-bottom:none}
    .stat-label{color:var(--dim)}.stat-value{color:var(--cyan)}
    .dist-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:9px}
    .dist-card{background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:9px;cursor:pointer;transition:border-color .15s}
    .dist-card:hover{border-color:var(--green)}
    .dist-name{color:var(--cyan);font-weight:700;font-size:12px}
    .dist-agents{color:var(--dim);font-size:11px;margin-top:2px}
    .mem-item{border-left:2px solid var(--green);padding:5px 9px;margin-bottom:7px;background:var(--bg3);border-radius:0 4px 4px 0}
    .action-btn{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--dim);
                padding:6px 10px;border-radius:4px;cursor:pointer;font-family:inherit;font-size:11px;
                text-align:left;margin-bottom:5px}
    .action-btn:hover{border-color:var(--green);color:var(--green)}
    ::-webkit-scrollbar{width:5px}
    ::-webkit-scrollbar-track{background:var(--bg2)}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
    ::-webkit-scrollbar-thumb:hover{background:var(--green)}
    @media(max-width:800px){.main{grid-template-columns:1fr}.sidebar,.right-panel{display:none}}
  </style>
</head>
<body>

<header>
  <span class="logo">V.E.C.T.O.R.</span>
  <span class="version">v__VER__ &mdash; __OWNER__'s Autonomous AI</span>
  <div class="header-status">
    <span class="badge" id="ollama-badge">Ollama: &mdash;</span>
    <span class="badge" id="loop-badge">Loop: &mdash;</span>
    <span class="badge" id="clock-badge"></span>
  </div>
</header>

<div class="main">
  <nav class="sidebar">
    <div class="sidebar-section">Interact</div>
    <div class="nav-item active" data-tab="chat">Chat</div>
    <div class="nav-item" data-tab="search">Research</div>
    <div class="sidebar-section" style="margin-top:6px">Intelligence</div>
    <div class="nav-item" data-tab="goals">Goals</div>
    <div class="nav-item" data-tab="memory">Memory</div>
    <div class="nav-item" data-tab="districts">Districts</div>
    <div class="sidebar-section" style="margin-top:6px">Track</div>
    <div class="nav-item" data-tab="tasks">Tasks</div>
    <div class="nav-item" data-tab="karpathy">Karpathy</div>
    <div class="nav-item" data-tab="agents">Agents HP</div>
    <div class="sidebar-section" style="margin-top:6px">System</div>
    <div class="nav-item" onclick="window.open('/docs','_blank')">API Docs</div>
    <div class="nav-item" onclick="window.open('/status','_blank')">Status JSON</div>
  </nav>

  <div class="content">
    <div class="tab-bar">
      <div class="tab active" data-tab="chat">Chat</div>
      <div class="tab" data-tab="search">Research</div>
      <div class="tab" data-tab="goals">Goals</div>
      <div class="tab" data-tab="memory">Memory</div>
      <div class="tab" data-tab="districts">Districts</div>
      <div class="tab" data-tab="tasks">Tasks</div>
      <div class="tab" data-tab="karpathy">Karpathy</div>
      <div class="tab" data-tab="agents">Agents</div>
    </div>

    <div id="chat-panel" class="active">
      <div id="chat-messages">
        <div class="msg sys">VECTOR v__VER__ ready &mdash; type a message or /help for commands.</div>
      </div>
      <div id="chat-bar">
        <textarea id="chat-in" rows="1" placeholder="Message VECTOR..." maxlength="2000"></textarea>
        <button id="send-btn">Send</button>
      </div>
    </div>

    <div id="search-panel" class="panel">
      <h3 style="color:var(--green);margin-bottom:10px">Research Hub</h3>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <input id="search-q" type="text" placeholder="Search web, ArXiv, GitHub, HN..."
          style="flex:1;background:var(--bg3);border:1px solid var(--border);border-radius:6px;
                 color:var(--text);padding:8px 10px;font-family:inherit;font-size:13px;outline:none"/>
        <button id="search-go" style="background:var(--green);color:var(--bg);border:none;border-radius:6px;padding:8px 14px;cursor:pointer;font-weight:700;font-family:inherit">Search</button>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">
        <button class="badge" id="btn-hn" style="cursor:pointer">HN Top</button>
        <button class="badge" id="btn-gh" style="cursor:pointer">GitHub Trending</button>
        <button class="badge" id="btn-devto" style="cursor:pointer">DEV.to AI</button>
        <button class="badge" id="btn-arxiv" style="cursor:pointer">ArXiv LLM</button>
      </div>
      <div id="search-results"></div>
    </div>

    <div id="goals-panel" class="panel">
      <h3 style="color:var(--green);margin-bottom:10px">Active Goals</h3>
      <div id="goals-content"></div>
    </div>

    <div id="memory-panel" class="panel">
      <h3 style="color:var(--green);margin-bottom:10px">Episodic Memory</h3>
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <input id="mem-q" type="text" placeholder="Search memories..."
          style="flex:1;background:var(--bg3);border:1px solid var(--border);border-radius:6px;
                 color:var(--text);padding:6px 10px;font-family:inherit;font-size:12px;outline:none"/>
        <button id="mem-search-btn" style="background:var(--bg3);color:var(--cyan);border:1px solid var(--border);border-radius:6px;padding:6px 12px;cursor:pointer;font-family:inherit">Search</button>
      </div>
      <div id="memory-content"></div>
    </div>

    <div id="districts-panel" class="panel">
      <h3 style="color:var(--green);margin-bottom:10px">VECTOR City &mdash; 25 Districts</h3>
      <div class="dist-grid" id="dist-grid"></div>
    </div>

    <div id="tasks-panel" class="panel">
      <h3 style="color:var(--green);margin-bottom:10px">Background Tasks</h3>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <input id="bg-task-input" type="text" placeholder="Describe a task for vector-deep..."
          style="flex:1;background:var(--bg3);border:1px solid var(--border);color:var(--text);
                 padding:6px 10px;border-radius:4px;font-family:inherit;font-size:12px"/>
        <button onclick="submitBgTask()"
          style="background:var(--bg3);border:1px solid var(--green);color:var(--green);
                 padding:6px 14px;border-radius:4px;cursor:pointer;font-family:inherit">Run BG</button>
        <button onclick="loadTasks()"
          style="background:var(--bg3);border:1px solid var(--border);color:var(--dim);
                 padding:6px 10px;border-radius:4px;cursor:pointer;font-family:inherit">Refresh</button>
      </div>
      <div id="tasks-running"></div>
      <div id="tasks-recent" style="margin-top:14px"></div>
    </div>

    <div id="karpathy-panel" class="panel">
      <h3 style="color:var(--green);margin-bottom:10px">Karpathy Track &mdash; RULE 12: 30min/day</h3>
      <div id="karpathy-content"></div>
    </div>

    <div id="agents-panel" class="panel">
      <h3 style="color:var(--green);margin-bottom:10px">Agent HP &mdash; Darwinian System</h3>
      <div id="agents-content"></div>
    </div>
  </div>

  <div class="right-panel">
    <div class="card">
      <div class="card-title">System</div>
      <div class="stat-row"><span class="stat-label">Model</span><span class="stat-value">vector-focus</span></div>
      <div class="stat-row"><span class="stat-label">Ollama</span><span class="stat-value" id="r-ollama">&mdash;</span></div>
      <div class="stat-row"><span class="stat-label">Loop</span><span class="stat-value" id="r-loop">&mdash;</span></div>
    </div>
    <div class="card">
      <div class="card-title">Comms</div>
      <div class="stat-row"><span class="stat-label">Urgent</span><span class="stat-value" style="color:var(--red)" id="r-urgent">&mdash;</span></div>
      <div class="stat-row"><span class="stat-label">Unread</span><span class="stat-value" id="r-unread">&mdash;</span></div>
      <div class="stat-row"><span class="stat-label">Pending</span><span class="stat-value" id="r-pending">&mdash;</span></div>
    </div>
    <div class="card">
      <div class="card-title">HP</div>
      <div style="color:var(--green);font-size:28px;font-weight:700" id="r-hp">500</div>
      <div class="hp-bar"><div class="hp-fill" id="r-hp-fill" style="width:50%"></div></div>
      <div style="color:var(--dim);font-size:10px;margin-top:3px">Gen 1</div>
    </div>
    <div class="card">
      <div class="card-title">Quick</div>
      <button class="action-btn" id="qa-news">Today's AI News</button>
      <button class="action-btn" id="qa-hn">HN Top Stories</button>
      <button class="action-btn" id="qa-goals">Refresh Goals</button>
      <button class="action-btn" id="qa-mem">Recent Memory</button>
    </div>
  </div>
</div>

<script>
(function(){
  "use strict";

  // â”€â”€ safe text node helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  function txt(s){return document.createTextNode(String(s||""))}
  function el(tag,attrs,children){
    const e=document.createElement(tag);
    if(attrs)Object.entries(attrs).forEach(([k,v])=>{
      if(k==="style")e.style.cssText=v;
      else if(k==="class")e.className=v;
      else e.setAttribute(k,v);
    });
    (children||[]).forEach(c=>e.appendChild(typeof c==="string"?txt(c):c));
    return e;
  }
  function clear(id){const e=document.getElementById(id);if(e)e.textContent="";return e}
  function append(id,node){const e=document.getElementById(id);if(e)e.appendChild(node)}

  // â”€â”€ Tab routing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const LAZY={goals:loadGoals,memory:loadMemory,districts:loadDistricts,
               tasks:loadTasks,karpathy:loadKarpathy,agents:loadAgents};

  function showTab(name){
    document.querySelectorAll(".panel, #chat-panel").forEach(p=>{
      p.classList.remove("active");
    });
    document.querySelectorAll(".tab, .nav-item[data-tab]").forEach(t=>{
      if(t.dataset.tab===name)t.classList.add("active");
      else t.classList.remove("active");
    });
    const panel=document.getElementById(name+"-panel");
    if(panel)panel.classList.add("active");
    if(LAZY[name])LAZY[name]();
  }

  document.querySelectorAll(".tab, .nav-item[data-tab]").forEach(t=>{
    t.addEventListener("click",()=>showTab(t.dataset.tab));
  });

  // â”€â”€ Chat â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  let chatHistory=[];
  try{
    const saved=sessionStorage.getItem("vector-chat");
    if(saved)chatHistory=JSON.parse(saved);
  }catch(e){}

  function saveChat(){
    try{sessionStorage.setItem("vector-chat",JSON.stringify(chatHistory));}catch(e){}
  }

  document.getElementById("chat-in").addEventListener("keydown",e=>{
    if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMessage();}
  });
  document.getElementById("send-btn").addEventListener("click",sendMessage);

  function addMsg(role,text){
    const box=document.getElementById("chat-messages");
    const wrap=el("div",{class:"msg "+role});
    if(role==="vector"){wrap.appendChild(el("div",{class:"msg-label"},["VECTOR"]));}
    wrap.appendChild(txt(text));
    box.appendChild(wrap);
    box.scrollTop=box.scrollHeight;
  }

  async function sendMessage(){
    const inp=document.getElementById("chat-in");
    const btn=document.getElementById("send-btn");
    const text=inp.value.trim();
    if(!text)return;
    inp.value="";
    addMsg("user",text);
    btn.disabled=true;
    try{
      const r=await fetch("/ui/chat",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({message:text,history:chatHistory})
      });
      const d=await r.json();
      const resp=d.response||d.error||"No response";
      addMsg("vector",resp);
      chatHistory.push({role:"user",content:text});
      chatHistory.push({role:"assistant",content:resp});
      if(chatHistory.length>20)chatHistory=chatHistory.slice(-20);
      saveChat();
    }catch(e){addMsg("sys","Error: "+e.message);}
    btn.disabled=false;
    inp.focus();
  }

  // â”€â”€ Search â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  document.getElementById("search-go").addEventListener("click",doSearch);
  document.getElementById("search-q").addEventListener("keydown",e=>{if(e.key==="Enter")doSearch();});
  document.getElementById("btn-hn").addEventListener("click",()=>fetchAndRender("/ui/hn"));
  document.getElementById("btn-gh").addEventListener("click",()=>fetchAndRender("/ui/github"));
  document.getElementById("btn-devto").addEventListener("click",()=>fetchAndRender("/ui/devto"));
  document.getElementById("btn-arxiv").addEventListener("click",()=>fetchAndRender("/ui/arxiv"));

  function doSearch(){
    const q=document.getElementById("search-q").value.trim();
    if(!q)return;
    fetchAndRender("/ui/search?q="+encodeURIComponent(q));
  }

  async function fetchAndRender(url){
    showTab("search");
    const el2=document.getElementById("search-results");
    el2.textContent="Loading...";
    try{
      const r=await fetch(url);
      const d=await r.json();
      renderResults(d.results||[]);
    }catch(e){el2.textContent="Error: "+e.message;}
  }

  function renderResults(items){
    const container=document.getElementById("search-results");
    container.textContent="";
    if(!items.length){container.textContent="No results.";return;}
    items.forEach(item=>{
      const card=el("div",{class:"card",style:"margin-bottom:9px"});
      const title=item.title||item.name||"Untitled";
      const url=item.url||"";
      const desc=item.snippet||item.description||item.summary||item.tagline||"";
      const source=item.source||"";
      const meta=[];
      if(item.score)meta.push("score: "+item.score);
      if(item.stars)meta.push("stars: "+item.stars);

      if(url){
        const a=el("a",{href:url,target:"_blank",
          style:"color:var(--cyan);text-decoration:none;font-weight:600"},
          [title]);
        card.appendChild(a);
      }else{
        card.appendChild(el("div",{style:"color:var(--cyan);font-weight:600"},[title]));
      }
      if(url)card.appendChild(el("div",{style:"color:var(--dim);font-size:10px;margin-top:2px"},[url]));
      if(desc)card.appendChild(el("div",{style:"margin-top:4px;font-size:12px"},[desc.substring(0,200)]));
      const foot=el("div",{style:"margin-top:4px;color:var(--dim);font-size:10px"});
      if(meta.length)foot.appendChild(txt(meta.join(" | ")+"  "));
      if(source){
        foot.appendChild(el("span",{style:"border:1px solid #30363d;padding:1px 5px;border-radius:3px"},[source]));
      }
      card.appendChild(foot);
      container.appendChild(card);
    });
  }

  // â”€â”€ Goals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  async function loadGoals(){
    const c=clear("goals-content");
    try{
      const r=await fetch("/ui/goals");
      const d=await r.json();
      const goals=d.goals||[];
      if(!goals.length){c.textContent="No active goals.";return;}
      goals.forEach((g,i)=>{
        const card=el("div",{class:"card",style:"margin-bottom:8px"});
        const action=typeof g==="object"?(g.action||JSON.stringify(g)):String(g);
        card.appendChild(el("div",{style:"color:var(--cyan);font-weight:600"},[(i+1)+". "+action]));
        if(g.priority)card.appendChild(el("div",{style:"color:var(--dim);font-size:11px;margin-top:3px"},["Priority: "+g.priority]));
        c.appendChild(card);
      });
    }catch(e){c.textContent="Error: "+e.message;}
  }

  // â”€â”€ Memory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  document.getElementById("mem-search-btn").addEventListener("click",searchMem);
  document.getElementById("mem-q").addEventListener("keydown",e=>{if(e.key==="Enter")searchMem();});

  async function loadMemory(){
    const c=clear("memory-content");
    c.textContent="Loading...";
    try{
      const r=await fetch("/ui/memory?limit=20");
      const d=await r.json();
      renderMemory(d.memories||[]);
    }catch(e){document.getElementById("memory-content").textContent="Error: "+e.message;}
  }

  async function searchMem(){
    const q=document.getElementById("mem-q").value.trim();
    if(!q)return;
    const c=clear("memory-content");
    c.textContent="Searching...";
    const r=await fetch("/ui/memory?q="+encodeURIComponent(q)+"&limit=10");
    const d=await r.json();
    renderMemory(d.memories||[]);
  }

  function renderMemory(mems){
    const c=clear("memory-content");
    if(!mems.length){c.textContent="No memories found.";return;}
    mems.forEach(m=>{
      const item=el("div",{class:"mem-item"});
      item.appendChild(el("div",{style:"color:var(--dim);font-size:10px"},
        [(m.timestamp||"")+" — "+(m.event_type||"")+" — "+(m.source||"")]));
      item.appendChild(el("div",{style:"font-size:12px;margin-top:2px"},
        [(m.content||"").substring(0,200)]));
      c.appendChild(item);
    });
  }

  // â”€â”€ Districts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const DISTRICTS=[
    ["01","governance","LLM Council, Mayor"],
    ["02","security","ThreatScout, Malware"],
    ["03","coding","GitBot, BugHunter"],
    ["04","time_calendar","KIITScraper, Deadlines"],
    ["05","communications","VectorCode multi-platform"],
    ["06","memory_curator","LightRAG, Consolidation"],
    ["07","research","WebScout, PaperReader"],
    ["08","intelligence","PatternDetective"],
    ["09","skills","SkillMapper, GapAnalyst"],
    ["10","languages","HI/BN/AS/JA/EN"],
    ["11","interview_prep","MockInterviewer"],
    ["12","learning","VideoIngestor, Concepts"],
    ["13","finance","UPI, Budget, Tax"],
    ["14","health","Sleep, Fatigue, Exercise"],
    ["15","reflection","DailyReview, Journal"],
    ["16","startups","MarketScanner, Validator"],
    ["17","investment","StockAnalyst NSE/BSE"],
    ["18","content","ScriptGen, VideoMerger"],
    ["19","agency","ClientManager, Strategy"],
    ["20","karpathy_lab","30min/day, Training"],
    ["21","projects","Planner, DocWriter"],
    ["22","relationships","ContactMgr, Comms"],
    ["23","privacy","DataFlowAuditor"],
    ["24","pattern_detective","BehaviorAnalyst"],
    ["25","news_trends","AINewsBot, Opportunity"],
  ];

  function loadDistricts(){
    const grid=clear("dist-grid");
    DISTRICTS.forEach(([num,name,agents])=>{
      const card=el("div",{class:"dist-card"});
      card.appendChild(el("div",{class:"dist-name"},[num+". "+name]));
      card.appendChild(el("div",{class:"dist-agents"},[agents]));
      grid.appendChild(card);
    });
  }

  // â”€â”€ Karpathy â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  async function loadKarpathy(){
    const c=clear("karpathy-content");
    try{
      const r=await fetch("/ui/karpathy");
      const d=await r.json();
      const streakCard=el("div",{class:"card"});
      streakCard.appendChild(el("div",{class:"card-title"},["Streak"]));
      streakCard.appendChild(el("div",{style:"font-size:36px;font-weight:700;color:var(--green)"},
        [String(d.streak||0)+" days"]));
      const todayCard=el("div",{class:"card"});
      todayCard.appendChild(el("div",{class:"card-title"},["Today"]));
      todayCard.appendChild(el("div",{style:"color:var(--dim);font-size:12px"},
        [d.today||"No session yet. python -m core.ui.chat → /karpathy"]));
      c.appendChild(streakCard);
      c.appendChild(todayCard);
    }catch(e){c.textContent="Error: "+e.message;}
  }

  // â”€â”€ Agents HP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  async function loadAgents(){
    const c=clear("agents-content");
    try{
      const r=await fetch("/ui/agents");
      const d=await r.json();
      const agents=d.agents||[];
      if(!agents.length){c.textContent="No agents in registry.";return;}
      agents.forEach(a=>{
        const card=el("div",{class:"card",style:"margin-bottom:7px"});
        const top=el("div",{style:"display:flex;justify-content:space-between;margin-bottom:3px"});
        const hp=a.hp||0;
        const hpColor=hp>500?"var(--green)":hp>200?"var(--yellow)":"var(--red)";
        top.appendChild(el("span",{style:"color:var(--cyan);font-weight:600"},[a.name||"?"]));
        top.appendChild(el("span",{style:"color:"+hpColor},["HP "+hp]));
        card.appendChild(top);
        const bar=el("div",{class:"hp-bar"});
        const fill=el("div",{class:"hp-fill"});
        fill.style.width=Math.min(hp/10,100)+"%";
        fill.style.background=hpColor;
        bar.appendChild(fill);
        card.appendChild(bar);
        card.appendChild(el("div",{style:"color:var(--dim);font-size:10px;margin-top:2px"},
          [(a.district||"?")+" — Gen "+(a.generation||1)]));
        c.appendChild(card);
      });
    }catch(e){c.textContent="Error: "+e.message;}
  }

  // â”€â”€ Status polling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  async function pollStatus(){
    try{
      const r=await fetch("/status");
      const d=await r.json();
      const ob=document.getElementById("ollama-badge");
      ob.textContent=d.ollama_available?"Ollama: OK":"Ollama: DOWN";
      ob.className="badge "+(d.ollama_available?"green":"red");
      document.getElementById("loop-badge").textContent="Loop: "+(d.loop_running?"ACTIVE":"STOPPED");
      document.getElementById("r-ollama").textContent=d.ollama_available?"OK":"DOWN";
      document.getElementById("r-loop").textContent=d.loop_running?"ACTIVE":"STOPPED";
      const comms=d.comms||{};
      document.getElementById("r-urgent").textContent=comms.urgent??"—";
      document.getElementById("r-unread").textContent=comms.unread??"—";
      document.getElementById("r-pending").textContent=comms.pending??"—";
    }catch(e){
        document.getElementById("ollama-badge").className="badge red";
        document.getElementById("ollama-badge").textContent="Ollama: LOST";
        document.getElementById("loop-badge").className="badge red";
        document.getElementById("loop-badge").textContent="Loop: UNKNOWN";
        document.getElementById("r-ollama").textContent="—";
        document.getElementById("r-loop").textContent="—";
        document.getElementById("r-urgent").textContent="—";
        document.getElementById("r-unread").textContent="—";
        document.getElementById("r-pending").textContent="—";
        console.warn("pollStatus failed:", e.message);
    }
  }

  // â”€â”€ Clock â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  function tick(){
    document.getElementById("clock-badge").textContent=
      new Date().toLocaleTimeString("en-GB",{hour12:false});
  }

  // â”€â”€ Quick action buttons â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  document.getElementById("qa-news").addEventListener("click",()=>{
    document.getElementById("search-q").value="AI news today";
    fetchAndRender("/ui/search?q=AI+news+today");
  });
  document.getElementById("qa-hn").addEventListener("click",()=>fetchAndRender("/ui/hn"));
  document.getElementById("qa-goals").addEventListener("click",loadGoals);
  document.getElementById("qa-mem").addEventListener("click",()=>{showTab("memory");loadMemory();});

  // â”€â”€ Background Tasks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  async function loadTasks(){
    try{
      const r2=await fetch("/tasks/"); const d=await r2.json();
      const runEl=document.getElementById("tasks-running");
      const recEl=document.getElementById("tasks-recent");
      if(!runEl||!recEl)return;
      runEl.textContent="";
      recEl.textContent="";

      const STATUS_COL={running:"#00ff41",done:"#39d353",failed:"#f85149",
                        cancelled:"#8b949e",queued:"#e3b341"};

      function makeRow(t){
        const row=document.createElement("div");
        row.style.cssText="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)";
        const id=document.createElement("span");
        id.style.cssText="color:var(--dim);font-size:11px;width:70px;flex-shrink:0";
        id.textContent=t.id;
        const name=document.createElement("span");
        name.style.cssText="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
        name.textContent=t.name;
        const stat=document.createElement("span");
        stat.style.cssText="font-size:11px;width:80px;text-align:right;flex-shrink:0";
        stat.style.color=STATUS_COL[t.status]||"#e6edf3";
        stat.textContent=t.status;
        const elapsed=document.createElement("span");
        elapsed.style.cssText="color:var(--dim);font-size:11px;width:50px;text-align:right;flex-shrink:0";
        elapsed.textContent=t.elapsed+"s";
        const dist=document.createElement("span");
        dist.style.cssText="color:var(--dim);font-size:11px;width:80px;text-align:right;flex-shrink:0";
        dist.textContent=t.district;
        row.appendChild(id);row.appendChild(name);row.appendChild(stat);
        row.appendChild(elapsed);row.appendChild(dist);
        if(t.status==="running"){
          const cancelBtn=document.createElement("button");
          cancelBtn.textContent="✕";
          cancelBtn.style.cssText="background:none;border:1px solid var(--red);color:var(--red);"+
            "cursor:pointer;font-size:10px;padding:1px 5px;border-radius:3px;flex-shrink:0";
          cancelBtn.addEventListener("click",async()=>{
            await apiFetch("/tasks/"+t.id,{method:"DELETE"});
            loadTasks();
          });
          row.appendChild(cancelBtn);
        }
        return row;
      }

      const running=(d.tasks||[]);
      if(running.length){
        const h=document.createElement("div");
        h.style.cssText="color:var(--green);font-size:11px;margin-bottom:4px;font-weight:700";
        h.textContent="â–¶ RUNNING ("+running.length+")";
        runEl.appendChild(h);
        running.forEach(t=>runEl.appendChild(makeRow(t)));
      } else {
        const idle=document.createElement("div");
        idle.style.cssText="color:var(--dim);font-size:12px";
        idle.textContent="No tasks running.";
        runEl.appendChild(idle);
      }

      const recent=(d.recent||[]);
      if(recent.length){
        const h=document.createElement("div");
        h.style.cssText="color:var(--dim);font-size:11px;margin-bottom:4px;font-weight:700";
        h.textContent="RECENT";
        recEl.appendChild(h);
        recent.forEach(t=>recEl.appendChild(makeRow(t)));
      }
    }catch(e){console.error("tasks error",e);}
  }

  async function submitBgTask(){
    const inp=document.getElementById("bg-task-input");
    if(!inp||!inp.value.trim())return;
    const query=inp.value.trim();
    inp.value="";
    try{
      await apiFetch("/tasks/submit",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({name:query.slice(0,60),query:query,district:"core",priority:"LOW"})
      });
      showTab("tasks");
      loadTasks();
    }catch(e){console.error("submit task error",e);}
  }

  // â”€â”€ Boot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  tick();
  setInterval(tick,1000);
  pollStatus();
  setInterval(pollStatus,30000);
  // Auto-refresh tasks panel every 5s when visible
  setInterval(()=>{
    const panel=document.getElementById("tasks-panel");
    if(panel&&panel.classList.contains("active"))loadTasks();
  },5000);
})();
</script>
</body>
</html>
"""

# Replace version/owner placeholders at import time (not per-request)
_DASHBOARD_HTML = _DASHBOARD_HTML.replace("__VER__", _VERSION).replace("__OWNER__", _OWNER)


# â”€â”€ FastAPI routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/", response_class=HTMLResponse)
async def dashboard():
    return _DASHBOARD_HTML


@router.post("/chat")
async def web_chat(body: dict):
    user_message = (body.get("message") or "").strip()
    history = body.get("history") or []
    if not user_message:
        return {"error": "Empty message"}
    try:
        from core.inference.ollama_safe import chat
        from core.loop.context_engine import ContextEngine
        from core.memory.episodic import EpisodicMemory

        hydration = ContextEngine().session_hydration_prompt()
        messages = [{"role": "system", "content": hydration}]
        messages += history[-10:]
        messages.append({"role": "user", "content": user_message})

        response = chat(
            model=CONFIG["models"]["focus"],
            messages=messages,
            timeout=120.0,
            caller_id="web_ui_chat",
        ) or "No response from model."

        try:
            EpisodicMemory().store(
                event_type="web_chat",
                content=f"User: {user_message}\nVECTOR: {response[:500]}",
                tags=["chat", "web"],
                source="web_ui",
            )
        except Exception as e:
            logger.warning("[VECTOR][web_ui] failed to store episodic memory: {}", e)

        return {"response": response}
    except Exception as e:
        logger.error(f"[VECTOR][web_ui] chat: {e}")
        return {"error": str(e)}


@router.websocket("/ws/chat")
async def web_chat_ws(websocket: WebSocket):
    # auth_middleware is registered via app.middleware("http") -- Starlette's
    # HTTP-scope middleware does NOT run for websocket-scope connections, so
    # this endpoint was reachable with zero authentication regardless of
    # VECTOR_API_KEY being set, identical to the /notifications/ws gap
    # already fixed this cycle (core/api/routers/websocket.py's
    # require_auth_handshake(), same WS_API_KEY).
    await websocket.accept()
    from core.api.routers.websocket import require_auth_handshake
    if not await require_auth_handshake(websocket):
        logger.warning("[VECTOR][web_ui] ws chat connection rejected -- auth handshake failed")
        return
    try:
        data = await websocket.receive_json()
        user_message = (data.get("message") or "").strip()
        history = data.get("history") or []
        if not user_message:
            await websocket.send_json({"type": "error", "message": "Empty message"})
            return

        from core.inference.ollama_safe import chat_stream
        from core.loop.context_engine import ContextEngine
        from core.memory.episodic import EpisodicMemory

        hydration = ContextEngine().session_hydration_prompt()
        messages = [{"role": "system", "content": hydration}]
        messages += history[-10:]
        messages.append({"role": "user", "content": user_message})

        full = ""
        for token in chat_stream(model=CONFIG["models"]["focus"], messages=messages,
                                 caller_id="web_ui_ws_chat"):
            if token:
                full += token
                await websocket.send_json({"type": "token", "text": token})

        if not full:
            full = "No response from model."
        await websocket.send_json({"type": "done", "full": full})

        try:
            EpisodicMemory().store(
                event_type="web_chat",
                content=f"User: {user_message}\nVECTOR: {full[:500]}",
                tags=["chat", "web"],
                source="web_ui_ws",
            )
        except Exception as e:
            logger.warning("[VECTOR][web_ui] failed to store episodic memory: {}", e)
    except WebSocketDisconnect:
        logger.debug("[VECTOR][web_ui] ws chat client disconnected")
    except Exception as e:
        logger.error(f"[VECTOR][web_ui] ws chat: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception as e2:
            logger.warning("[VECTOR][web_ui] failed to send error to disconnected client: {}", e2)


@router.get("/search")
async def web_search(q: str = "", limit: int = 8):
    try:
        from districts.research.research_hub import ResearchHub
        results = await ResearchHub().search_web(q, max_results=limit)
        return {"results": results}
    except Exception as e:
        return {"results": [], "error": str(e)}


@router.get("/hn")
async def web_hn(limit: int = 15):
    try:
        from districts.research.research_hub import ResearchHub
        results = await ResearchHub().get_hn_top(limit=limit)
        return {"results": results}
    except Exception as e:
        return {"results": [], "error": str(e)}


@router.get("/github")
async def web_github(lang: str = "python", limit: int = 10):
    try:
        from districts.research.research_hub import ResearchHub
        results = await ResearchHub().get_github_trending(lang, limit=limit)
        return {"results": results}
    except Exception as e:
        return {"results": [], "error": str(e)}


@router.get("/devto")
async def web_devto(tag: str = "machinelearning", limit: int = 10):
    try:
        from districts.research.research_hub import ResearchHub
        results = await ResearchHub().get_devto_posts(tag, limit=limit)
        return {"results": results}
    except Exception as e:
        return {"results": [], "error": str(e)}


@router.get("/arxiv")
async def web_arxiv(q: str = "large language model", limit: int = 5, category: str = "cs.AI"):
    try:
        from districts.research.research_hub import ResearchHub
        results = await ResearchHub().search_arxiv(q, max_results=limit, category=category)
        return {"results": results}
    except Exception as e:
        return {"results": [], "error": str(e)}


@router.get("/goals")
async def web_goals():
    try:
        from core.brain.goal_system import GoalSystem
        goals = GoalSystem().generate_immediate_actions()
        return {"goals": goals}
    except Exception as e:
        return {"goals": [], "error": str(e)}


@router.get("/memory")
async def web_memory(q: str = "", limit: int = 20):
    try:
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        results = mem.recall(q or "", limit=limit)
        return {"memories": results}
    except Exception as e:
        return {"memories": [], "error": str(e)}


@router.get("/karpathy")
async def web_karpathy():
    try:
        from districts.karpathy_lab.code_typer import CodeTyper
        typer = CodeTyper()
        return {"streak": typer.get_streak(), "today": typer.get_today_summary()}
    except Exception as e:
        return {"streak": 0, "today": str(e)}


@router.get("/agents")
async def web_agents():
    try:
        from core.city.agent_registry import get_registry
        agents = get_registry().list_all()
        return {"agents": [
            {"name": a.get("name", "?"), "hp": a.get("health_points", 0),
             "district": a.get("district", "?"), "generation": a.get("generation", 1)}
            for a in agents
        ]}
    except Exception as e:
        return {"agents": [], "error": str(e)}


@router.get("/tasks")
async def web_tasks():
    try:
        from core.loop.task_queue import TaskQueue
        return TaskQueue.get().summary()
    except Exception as e:
        return {"running": 0, "queued": 0, "completed_today": 0, "failed_today": 0,
                "tasks": [], "recent": [], "error": str(e)}


@router.post("/tasks/submit")
async def web_tasks_submit(req: dict):
    try:
        from core.loop.task_queue import TaskQueue, Priority
        from core.inference.ollama_safe import chat
        from core.loop.context_engine import ContextEngine

        name     = str(req.get("name", "bg-task"))[:60]
        query    = str(req.get("query", ""))
        priority = Priority[str(req.get("priority", "LOW")).upper()]

        async def _work():
            hydration = ContextEngine().session_hydration_prompt()
            return chat(
                model="vector-deep",
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user",   "content": query},
                ],
                timeout=600.0,
                caller_id="web_ui_task",
            )

        task_id = TaskQueue.get().submit(
            _work(), name=name, priority=priority,
            district="core", tags=["web", "bg"]
        )
        return {"task_id": task_id, "status": "queued"}
    except Exception as e:
        return {"error": str(e)}


@router.delete("/tasks/{task_id}")
async def web_tasks_cancel(task_id: str):
    try:
        from core.loop.task_queue import TaskQueue
        cancelled = TaskQueue.get().cancel(task_id)
        return {"cancelled": cancelled, "task_id": task_id}
    except Exception as e:
        return {"cancelled": False, "error": str(e)}
