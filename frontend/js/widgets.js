/* ============================================================================
   VECTOR · widgets.js  — the secret workspace: draggable panels + chat/music
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR, D = global.VECTOR_DATA;
  const ws = () => document.getElementById('workspace');
  const live = {};            // id -> element
  const chatMsgs = [];        // buffered conversation

  const el = (t, c, h) => { const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.innerHTML=h; return e; };
  const apiBase = () => (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';
  async function apiGet(path){
    if(V && V.http) return V.http(path);
    const r = await fetch(apiBase()+path);
    if(!r.ok) throw new Error(path+' -> '+r.status);
    return r.json();
  }
  async function apiPost(path, body){
    if(V && V.http) return V.http(path, { method:'POST', body:body||{} });
    const r = await fetch(apiBase()+path, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body||{})
    });
    if(!r.ok) throw new Error(path+' -> '+r.status);
    return r.json();
  }

  // default layout positions (left/top in %, of #workspace) -----------------
  const POS = {
    telemetry:[2,2], market:[64,2], districts:[2,32], goals:[72,30],
    memory:[2,64], council:[40,55], security:[40,4], map:[26,20],
    music:[40,70], chat:[2,30], webcam:[60,40],
    approvals:[66,55], librechat:[4,4], openwebui:[4,4],
    finance:[64,30], contentscheduler:[2,30], answerengine:[30,20], goalplanner:[4,55]
  };

  // ---- chrome wrapper -----------------------------------------------------
  function shell(id, title, bodyEl, extraClass){
    const w = el('div', 'widget '+(extraClass||''));
    w.dataset.id = id;
    const head = el('div','w-head',
      `<span class="dotled"></span><span class="w-title">${title}</span><span class="spacer"></span><span class="w-x">✕</span>`);
    head.querySelector('.w-x').addEventListener('click', e=>{ e.stopPropagation(); V.closeWidget(id); });
    const body = el('div','w-body'); body.appendChild(bodyEl);
    w.appendChild(head); w.appendChild(body);
    w.appendChild(el('div','w-corner tr')); w.appendChild(el('div','w-corner bl'));
    enableDrag(w, head);
    return w;
  }

  // ---- factories ----------------------------------------------------------
  const F = {};

  F.chat = function(){
    const wrap = el('div');
    const log = el('div','log');
    const row = el('div','row',
      `<input placeholder="enter message…" /><button class="send">SEND ↵</button>`);
    wrap.appendChild(log); wrap.appendChild(row);
    const input = row.querySelector('input'), send = row.querySelector('.send');
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    function localFallbackReply(text, reason){
      if(typeof V.setRuntimeMode === 'function') V.setRuntimeMode('degraded', reason || 'backend command failed');
      return 'LOCAL DEMO FALLBACK · '+localReply(text);
    }

    async function submitToBackend(text){
      try{
        const j = await apiPost('/command', { text });
        V.say((j && (j.response || j.text || j.result)) || 'Done, sir.');
      }catch(e){ V.say(localFallbackReply(text, 'chat /command failed')); }
    }

    function submit(){ const t=input.value.trim(); if(!t) return; input.value='';
      chatMsgs.push({ role:'user', text:t });
      appendMsg(log, { role:'user', text:t });
      if(API){ submitToBackend(t); } else { setTimeout(()=>V.say(localFallbackReply(t, 'chat using demo mode')), 650); }
    }
    send.addEventListener('click', submit);
    input.addEventListener('keydown', e=>{ if(e.key==='Enter') submit(); e.stopPropagation(); });
    const w = shell('chat','CONVERSATION', wrap, 'chat');
    w._log = log; renderChat(log);
    return w;
  };

  F.music = function(opts){
    const t = (opts&&opts.track) || D.TRACKS[0];
    const wrap = el('div');
    wrap.innerHTML =
      `<div class="top">
         <div class="art" style="background:${t.art}">IDLE</div>
         <div class="meta"><div class="t">${escapeHtml(t.title)}</div><div class="a">${escapeHtml(t.artist)}</div>
           <span class="badge">SPOTIFY</span></div></div>
       <div class="bar"><i style="width:${(t.pos/t.dur*100)}%"></i></div>
       <div class="time"><span>${fmt(t.pos)}</span><span>${fmt(t.dur)}</span></div>
       <div class="ctrl"><button>⏮</button><button class="pp">⏸</button><button>⏭</button><button>🔀</button></div>`;
    return shell('music','MUSIC', wrap, 'music');
  };

  F.map = function(opts){
    const wrap = el('div');
    const mapEl = el('div','leaflet');
    wrap.appendChild(mapEl);
    wrap.appendChild(el('div','mlabel', (opts&&opts.label)||D.MAP.label));
    const w = shell('map','TACTICAL MAP', wrap, 'map');
    setTimeout(()=>initLeaflet(mapEl, opts), 80);
    return w;
  };
  let _mapId=0;
  function initLeaflet(mapEl, opts){
    if(typeof L==='undefined'){
      mapEl.classList.add('map-abstract'); buildAbstractMap(mapEl); return;
    }
    try{
      const c=(opts&&opts.center)||D.MAP.center, z=(opts&&opts.zoom)||D.MAP.zoom;
      const m=L.map(mapEl,{ zoomControl:false, attributionControl:false, fadeAnimation:true }).setView(c, z);
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        { maxZoom:19, subdomains:'abcd' }).addTo(m);
      D.MAP.pins.forEach(p=>{
        const ll=[ c[0] + (0.5-p.y)*0.9, c[1] + (p.x-0.5)*1.7 ];
        const col = p.kind==='alert'?'#F59E0B':(p.kind==='home'?'#7fe6ff':'#00CFFF');
        L.circleMarker(ll, { radius:p.kind==='home'?7:5, color:col, weight:1.5,
          fillColor:col, fillOpacity:.55 }).addTo(m)
          .bindTooltip(p.name, { permanent:true, direction:'right', className:'lf-tip' });
      });
      setTimeout(()=>m.invalidateSize(), 120);
      mapEl._map=m;
    }catch(e){ mapEl.classList.add('map-abstract'); buildAbstractMap(mapEl); }
  }
  function buildAbstractMap(mapEl){
    const m=D.MAP;
    let roads='<svg class="roads" viewBox="0 0 100 100" preserveAspectRatio="none">';
    const P=m.pins;
    for(let i=0;i<P.length;i++) for(let j=i+1;j<P.length;j++){ if(Math.random()>0.55) continue;
      roads+=`<line x1="${P[i].x*100}" y1="${P[i].y*100}" x2="${P[j].x*100}" y2="${P[j].y*100}" stroke="rgba(0,207,255,.16)" stroke-width=".3"/>`; }
    roads+='</svg>'; mapEl.innerHTML=roads;
    P.forEach(p=>{ const pin=el('div','pin '+p.kind); pin.style.left=(p.x*100)+'%'; pin.style.top=(p.y*100)+'%';
      pin.innerHTML=`<div class="pulse"></div><div class="d"></div><div class="nm">${escapeHtml(p.name)}</div>`; mapEl.appendChild(pin); });
  }

  F.telemetry = function(){
    const wrap = el('div');
    wrap.innerHTML = `
      <div class="ve-source" data-source data-mode="simulated">SIMULATED · waiting for backend metrics</div>
      <div class="row-kv"><span class="k">CPU · RTX HOST</span><span class="v" data-cpu>—</span></div>
      <div class="meter"><i data-cpu-bar style="width:0"></i></div>
      <div class="row-kv" style="margin-top:6px"><span class="k">VRAM</span><span class="v" data-vram>—</span></div>
      <div class="meter"><i data-vram-bar style="width:0"></i></div>
      <div class="row-kv" style="margin-top:6px"><span class="k">GPU TEMP</span><span class="v" data-temp>—</span></div>
      <div class="meter warn"><i data-temp-bar style="width:0"></i></div>
      <div class="row-kv" style="margin-top:8px"><span class="k">ACTIVE MODEL</span><span class="v" data-model>claude-sonnet-4.6</span></div>
      <div class="row-kv"><span class="k">LOOP TICK</span><span class="v" data-tick>0</span></div>
      <div class="row-kv"><span class="k">UPTIME</span><span class="v" data-up>00:00:00</span></div>`;
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    const set=(sel,v)=>{ const e=wrap.querySelector(sel); if(e) e.textContent=v; };
    const bar=(sel,v)=>{ const e=wrap.querySelector(sel); if(e) e.style.width=v+'%'; };
    const source=(mode,msg)=>{ const e=wrap.querySelector('[data-source]'); if(e){ e.textContent=msg; e.dataset.mode=mode; } };

    function fmtUptime(s){ s=Math.floor(s||0);
      return [s/3600, s/60%60, s%60].map(n=>String(Math.floor(n)).padStart(2,'0')).join(':'); }

    async function loadTelemetry(){
      try{
        const j = await apiGet('/health/system');
        source('live', 'LIVE · backend metrics');
        const cpu = j.cpu_percent || 0;
        const vram = j.memory_percent || 0;
        const temp = j.gpu_temp || 0;
        set('[data-cpu]', cpu.toFixed(0)+'%');   bar('[data-cpu-bar]', cpu);
        set('[data-vram]', vram.toFixed(0)+'%');  bar('[data-vram-bar]', vram);
        set('[data-temp]', temp ? temp.toFixed(0)+'°C' : '—');
        bar('[data-temp-bar]', temp ? Math.max(0,(temp-40)/40*100) : 0);
        if(j.loop_tick != null) set('[data-tick]', j.loop_tick);
        if(j.uptime_seconds != null) set('[data-up]', fmtUptime(j.uptime_seconds));
        if(j.active_model) set('[data-model]', j.active_model);
      }catch(e){
        source('simulated', 'SIMULATED · backend metrics unavailable');
        if(typeof V.setRuntimeMode === 'function') V.setRuntimeMode('degraded', 'telemetry backend unavailable');
      }
    }

    const w = shell('telemetry','SYSTEM TELEMETRY', wrap, 'panel');
    loadTelemetry();
    animateTelemetry(w);   // simulated baseline; live data overwrites values when backend is up
    setInterval(()=>{ if(w.isConnected) loadTelemetry(); }, 3000);
    return w;
  };

  F.market = function(){
    const wrap = el('div');
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    // build demo SVG as initial placeholder
    function demoSvg(){
      const pts=[]; let y=60; for(let i=0;i<48;i++){ y+=(Math.random()-0.48)*10; y=Math.max(14,Math.min(96,y)); pts.push(y); }
      const path = pts.map((p,i)=>`${(i/(pts.length-1)*340).toFixed(1)},${p.toFixed(1)}`).join(' ');
      return `<svg viewBox="0 0 340 120" preserveAspectRatio="none">
        <defs><linearGradient id="mg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="rgba(0,207,255,.35)"/><stop offset="1" stop-color="rgba(0,207,255,0)"/>
        </linearGradient></defs>
        <polygon points="0,120 ${path} 340,120" fill="url(#mg)"/>
        <polyline points="${path}" fill="none" stroke="var(--accent)" stroke-width="1.3"/>
      </svg>`;
    }

    wrap.innerHTML =
      demoSvg() +
      `<div class="stat">
         <div><b class="mkt-name">NIFTY 50</b> <span class="mkt-price">—</span></div>
         <div class="mkt-change" style="color:var(--txt-mute)">— · —</div>
       </div>
       <div class="mkt-news" style="font-size:9px;color:var(--txt-mute);margin-top:6px;line-height:1.5"></div>`;

    async function loadMarket(){
      try{
        const j = await apiGet('/finance/ticker?symbol=NIFTY50');
        const priceEl = wrap.querySelector('.mkt-price');
        const changeEl = wrap.querySelector('.mkt-change');
        if(priceEl && j.price != null) priceEl.textContent = Number(j.price).toLocaleString('en-IN');
        if(changeEl && j.change_pct != null){
          const up = j.change_pct >= 0;
          changeEl.textContent = (up?'▲ ':'▼ ')+Math.abs(j.change_pct).toFixed(2)+'%'
            + (j.change != null ? '  +'+Number(j.change).toFixed(2) : '');
          changeEl.style.color = up ? 'var(--ok)' : 'var(--danger)';
        }
      }catch(e){ /* backend offline — keep demo */ }
    }

    async function loadHeadlines(){
      try{
        const j = await apiGet('/news/headlines?limit=3');
        const items = j.headlines || j.results || [];
        const newsEl = wrap.querySelector('.mkt-news');
        if(newsEl && items.length)
          newsEl.innerHTML = items.map(h=>`<div class="mkt-headline">· ${escapeHtml(h.title||h.text||h)}</div>`).join('');
      }catch(e){ /* offline */ }
    }

    const w = shell('market','MARKET · NSE', wrap, 'market');
    loadMarket();
    loadHeadlines();
    setInterval(()=>{ if(w.isConnected){ loadMarket(); loadHeadlines(); } }, 30000);
    return w;
  };

  F.goals = function(){
    const wrap = el('div');
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    function renderGoalsData(goalsObj){
      wrap.innerHTML = '';
      ['LONG','MID','SHORT'].forEach(h=>{
        const lbl = el('div', null, `<div style="font-size:8px;letter-spacing:.16em;color:var(--txt-faint);margin:6px 0 3px">${h} HORIZON</div>`);
        wrap.appendChild(lbl);
        const items = goalsObj[h] || [];
        if(!items.length){ wrap.appendChild(el('div',null,'<div style="font-size:9px;color:var(--txt-mute);padding:2px 0">—</div>')); return; }
        items.forEach(g=>{
          const p = g.progress != null ? Math.min(1, g.progress) : 0;
          const row = el('div', null,
            `<div class="row-kv"><span class="v">${g.title}</span><span class="k">${Math.round(p*100)}%</span></div>
             <div class="meter ${p<0.4?'dn':p<0.7?'warn':''}"><i style="width:${p*100}%"></i></div>`);
          wrap.appendChild(row);
        });
      });
    }

    async function loadGoals(){
      try{
        const j = await apiGet('/brain/goals');
        const goals = j.goals || (Array.isArray(j)?j:[]);
        const byHorizon = { LONG:[], MID:[], SHORT:[] };
        goals.forEach(g=>{
          const h = (g.horizon||'').toUpperCase();
          if(byHorizon[h]) byHorizon[h].push(g);
        });
        renderGoalsData(byHorizon);
      }catch(e){
        wrap.innerHTML = '<div class="ve-offline">◌ VECTOR offline</div>';
      }
    }

    const w = shell('goals','GOALS', wrap, 'panel');
    loadGoals();
    setInterval(()=>{ if(w.isConnected) loadGoals(); }, 30000);
    return w;
  };

  F.districts = function(){
    const wrap = el('div');
    const grid = el('div','grid');
    wrap.appendChild(grid);
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    function renderAgents(agents){
      grid.innerHTML = '';
      agents.slice(0,18).forEach(a=>{
        const hp = a.health_points != null ? a.health_points : (a.hp != null ? a.hp : 500);
        const pct = hp/1000*100;
        const cls = hp<=0?'ghost':'';
        const bar = hp<=0?'low':hp<400?'low':hp<700?'mid':'';
        const dist = (a.district||a.agent_type||'—').toUpperCase().slice(0,12);
        const gen = a.generation != null ? 'G'+a.generation : '';
        const tier = a.tier || a.model || '';
        grid.appendChild(el('div','agent '+cls,
          `<div class="an">${a.name||a.id}</div><div class="ad">${dist}</div>
           <div class="hpbar ${bar}"><i style="width:${pct}%"></i></div>
           <div class="hp"><span>HP ${hp}</span><span>${[gen,tier].filter(Boolean).join(' · ')}</span></div>`));
      });
    }

    async function loadDistricts(){
      try{
        const j = await apiGet('/agents');
        const agents = j.agents || j.data || (Array.isArray(j)?j:[]);
        if(agents.length) renderAgents(agents);
        const title = wrap.closest && wrap.closest('.widget')
          ? wrap.closest('.widget').querySelector('.w-title') : null;
        if(title) title.textContent = 'AGENT DISTRICTS · '+agents.length;
      }catch(e){
        grid.innerHTML = '<div class="ve-offline">◌ VECTOR offline</div>';
      }
    }

    const w = shell('districts','AGENT DISTRICTS · 33', wrap, 'agents');
    loadDistricts();
    setInterval(()=>{ if(w.isConnected) loadDistricts(); }, 10000);
    return w;
  };

  F.council = function(){
    const wrap = el('div');
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    function renderSessions(sessions){
      wrap.innerHTML = '';
      sessions.forEach(c=>{
        const rec = c.recommendation || c.decision || 'defer';
        const stakes = c.stakes || c.risk_level || 'medium';
        const conf = c.confidence != null ? Math.round(c.confidence*100) : '—';
        const when = c.when || c.timestamp || '';
        const q = c.question || c.topic || c.id || '';
        wrap.appendChild(el('div','csess',
          `<div class="q">${q}</div>
           <div class="meta">
             <span class="badge2 ${rec}">${rec.toUpperCase()}</span>
             <span class="badge2 ${stakes==='critical'?'crit':stakes}">${stakes.toUpperCase()}</span>
             <span class="k" style="margin-left:auto">${conf}% · ${when}</span>
           </div>`));
      });
    }

    async function loadCouncil(){
      try{
        // Canonical council history endpoint
        const j = await apiGet('/memory/council/history?limit=5');
        const sessions = j.sessions || j.data || (Array.isArray(j)?j:[]);
        if(sessions.length){ renderSessions(sessions); return; }
      }catch(e){ /* no council endpoint — fall through to HP-based view */ }
      // Fallback: show council-eligible agents (HP > 700) from /agents
      try{
        const j2 = await apiGet('/agents');
        const agents = j2.agents || (Array.isArray(j2)?j2:[]);
        const eligible = agents.filter(a=>(a.health_points||a.hp||0)>700);
        if(eligible.length){
          wrap.innerHTML = '';
          eligible.forEach(a=>{
            wrap.appendChild(el('div','csess',
              `<div class="q">${a.name||a.id} · ${(a.district||'—').toUpperCase()}</div>
               <div class="meta"><span class="badge2 proceed">COUNCIL ELIGIBLE</span>
                 <span class="k" style="margin-left:auto">HP ${a.health_points||a.hp}</span></div>`));
          });
        } else {
          wrap.innerHTML = '<div class="ve-offline">◌ VECTOR offline</div>';
        }
      }catch(e2){
        wrap.innerHTML = '<div class="ve-offline">◌ VECTOR offline</div>';
      }
    }

    const w = shell('council','LLM COUNCIL', wrap, 'council');
    loadCouncil();
    setInterval(()=>{ if(w.isConnected) loadCouncil(); }, 15000);
    return w;
  };

  F.security = function(){
    const wrap = el('div');
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    const header = el('div', null,
      `<div class="row-kv"><span class="k">THREAT LEVEL</span><span class="v sec-threat" style="color:var(--ok)">LOW</span></div>
       <div class="sec-lbl" style="font-size:8px;letter-spacing:.16em;color:var(--txt-faint);margin:8px 0 4px">RECENT EVENTS</div>`);
    wrap.appendChild(header);
    const evtList = el('div','sec-events');
    wrap.appendChild(evtList);

    async function loadSecurity(){
      try{
        const j = await apiGet('/security/status');
        const threatEl = wrap.querySelector('.sec-threat');
        if(threatEl){
          const level = (j.threat_level||'LOW').toUpperCase();
          threatEl.textContent = level;
          threatEl.style.color = level==='CRITICAL'?'var(--danger)':level==='HIGH'?'var(--warn)':level==='MEDIUM'?'var(--warn)':'var(--ok)';
        }
      }catch(e){
        const threatEl = wrap.querySelector('.sec-threat');
        if(threatEl){ threatEl.textContent = '—'; threatEl.style.color = 'var(--txt-faint)'; }
      }
      try{
        const j2 = await apiGet('/security/recent?limit=5');
        const events = j2.events || j2.results || (Array.isArray(j2)?j2:[]);
        if(events.length){
          evtList.innerHTML = '';
          events.forEach(ev=>{
            const level = (ev.level||ev.severity||'INFO').toUpperCase();
            const isRed = level==='CRITICAL'||level==='RED';
            const row = el('div','appr '+(isRed?'red':''),
              `<div class="at">${ev.event_type||ev.type||ev.action||'event'}
                 <span class="badge2 ${isRed?'crit':'high'}">${level}</span></div>
               <div class="ap">${ev.description||ev.detail||ev.params||''}</div>`);
            evtList.appendChild(row);
          });
        } else {
          evtList.innerHTML = '<div class="ve-offline">◌ VECTOR offline</div>';
        }
      }catch(e2){
        evtList.innerHTML = '<div class="ve-offline">◌ VECTOR offline</div>';
      }
    }

    const w = shell('security','PERMISSION GATE', wrap, 'security');
    loadSecurity();
    setInterval(()=>{ if(w.isConnected) loadSecurity(); }, 10000);
    return w;
  };

  F.memory = function(){
    const wrap = el('div');
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    function renderMemories(memories){
      wrap.innerHTML = '';
      memories.forEach(m=>{
        const imp = m.importance || m.event_type||'';
        const when = m.when || m.timestamp || (m.created_at ? new Date(m.created_at).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}) : '');
        const evType = m.event_type || m.type || 'event';
        const content = m.content || m.text || m.summary || '';
        wrap.appendChild(el('div','mevt imp-'+imp,
          `<span class="ew">${when}</span><div class="et">${evType}</div><div class="ec">${content}</div>`));
      });
    }

    async function loadMemory(){
      try{
        const j = await apiGet('/memory/recent?limit=20');
        const mems = j.memories || j.events || (Array.isArray(j)?j:[]);
        if(mems.length) renderMemories(mems);
        else wrap.innerHTML = '<div class="ve-offline">◌ VECTOR offline</div>';
      }catch(e){
        wrap.innerHTML = '<div class="ve-offline">◌ VECTOR offline</div>';
      }
    }

    const w = shell('memory','EPISODIC MEMORY', wrap, 'memory');
    loadMemory();
    setInterval(()=>{ if(w.isConnected) loadMemory(); }, 8000);
    return w;
  };

  F.webcam = function(){
    const wrap = el('div');
    const feed = el('div','feed', `<div class="off">CAMERA · LOCAL PREVIEW STANDBY</div>`);
    wrap.appendChild(feed);
    const w = shell('webcam','VISION FEED', wrap, 'cam');
    // try to attach real webcam
    requestCam(feed);
    return w;
  };

  // Voice Studio — content script → audio in your cloned voice (voicebox absorption)
  F.voicestudio = function(){
    const wrap = el('div','vstudio');
    wrap.innerHTML = `
      <div class="vs-row">
        <label class="vs-lbl">VOICE PROFILE</label>
        <select class="vs-profile"><option value="owner">owner (default)</option></select>
        <button class="vs-refresh" title="reload profiles">⟳</button>
      </div>
      <textarea class="vs-script" placeholder="Paste your content script here, or pull one from the script generator…"></textarea>
      <div class="vs-row">
        <button class="vs-gen">▶ GENERATE IN MY VOICE</button>
        <span class="vs-status"></span>
      </div>
      <audio class="vs-audio" controls style="width:100%;display:none;margin-top:8px"></audio>
      <a class="vs-dl" style="display:none;margin-top:4px" download>⬇ download .wav</a>
    `;
    const sel = wrap.querySelector('.vs-profile');
    const ta  = wrap.querySelector('.vs-script');
    const gen = wrap.querySelector('.vs-gen');
    const stat= wrap.querySelector('.vs-status');
    const aud = wrap.querySelector('.vs-audio');
    const dl  = wrap.querySelector('.vs-dl');
    const refresh = wrap.querySelector('.vs-refresh');
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    async function loadProfiles(){
      try{
        const j = await apiGet('/voice/profiles');
        const profs = (j.profiles||[]).map(p=>p.name);
        if(profs.length){ sel.innerHTML = profs.map(n=>`<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join(''); }
      }catch(e){ /* keep default */ }
    }
    refresh.addEventListener('click', e=>{ e.stopPropagation(); loadProfiles(); });

    gen.addEventListener('click', async e=>{
      e.stopPropagation();
      const text = ta.value.trim();
      if(!text){ stat.textContent='enter a script first'; return; }
      stat.textContent='◌ synthesizing…'; gen.disabled=true;
      try{
        const j = await apiPost('/voice/studio/generate', { text, profile: sel.value });
        if(j.status==='ok' && j.audio_url){
          stat.textContent = '✓ done · engine: ' + (j.engine||'?');
          aud.src = API + j.audio_url; aud.style.display='block';
          dl.href = API + j.audio_url; dl.style.display='inline-block';
        } else {
          stat.textContent = '⚠ ' + (j.error || 'generation failed');
        }
      }catch(err){ stat.textContent='⚠ '+err.message; }
      finally{ gen.disabled=false; }
    });
    ta.addEventListener('keydown', e=>e.stopPropagation());

    const w = shell('voicestudio','VOICE STUDIO · MY VOICE', wrap, 'vstudio');
    loadProfiles();
    return w;
  };

  // Code Graph — interactive codebase dependency explorer (Understand-Anything absorption)
  F.codegraph = function(){
    const wrap = el('div','cgraph');
    wrap.innerHTML = `
      <div class="cg-row">
        <input class="cg-path" placeholder="path to scan (e.g. core/memory)" value="districts/coding"/>
        <button class="cg-scan">SCAN</button>
      </div>
      <div class="cg-row">
        <input class="cg-search" placeholder="highlight node…"/>
        <span class="cg-stat"></span>
      </div>
      <canvas class="cg-canvas" width="560" height="360"></canvas>
      <div class="cg-sel"></div>
    `;
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';
    const cv = wrap.querySelector('.cg-canvas'), ctx = cv.getContext('2d');
    const pathIn = wrap.querySelector('.cg-path');
    const search = wrap.querySelector('.cg-search');
    const stat = wrap.querySelector('.cg-stat');
    const selEl = wrap.querySelector('.cg-sel');
    let G = {nodes:[], edges:[]}, anim=null, hi='';

    function layout(){
      const W=cv.width, H=cv.height, n=G.nodes.length||1;
      G.nodes.forEach((nd,i)=>{ const a=i/n*Math.PI*2;
        nd.x = W/2 + Math.cos(a)*(80+Math.random()*120);
        nd.y = H/2 + Math.sin(a)*(60+Math.random()*100);
        nd.vx=0; nd.vy=0; });
    }
    function step(){
      const W=cv.width, H=cv.height;
      // repulsion
      for(let i=0;i<G.nodes.length;i++){ const a=G.nodes[i];
        for(let j=i+1;j<G.nodes.length;j++){ const b=G.nodes[j];
          let dx=a.x-b.x, dy=a.y-b.y, d2=dx*dx+dy*dy+0.01, f=900/d2;
          const dx2=dx*f, dy2=dy*f; a.vx+=dx2; a.vy+=dy2; b.vx-=dx2; b.vy-=dy2; } }
      // attraction along edges
      const idx={}; G.nodes.forEach(nd=>idx[nd.id]=nd);
      G.edges.forEach(e=>{ const a=idx[e.from], b=idx[e.to]; if(!a||!b) return;
        let dx=b.x-a.x, dy=b.y-a.y; a.vx+=dx*0.002; a.vy+=dy*0.002; b.vx-=dx*0.002; b.vy-=dy*0.002; });
      // integrate + center pull + bounds
      G.nodes.forEach(nd=>{ nd.vx+=(W/2-nd.x)*0.0008; nd.vy+=(H/2-nd.y)*0.0008;
        nd.x+=Math.max(-6,Math.min(6,nd.vx)); nd.y+=Math.max(-6,Math.min(6,nd.vy));
        nd.vx*=0.85; nd.vy*=0.85;
        nd.x=Math.max(14,Math.min(W-14,nd.x)); nd.y=Math.max(14,Math.min(H-14,nd.y)); });
    }
    function draw(){
      const W=cv.width,H=cv.height; ctx.clearRect(0,0,W,H);
      const idx={}; G.nodes.forEach(nd=>idx[nd.id]=nd);
      ctx.lineWidth=1; ctx.strokeStyle='rgba(0,207,255,.22)';
      G.edges.forEach(e=>{ const a=idx[e.from], b=idx[e.to]; if(!a||!b) return;
        ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke(); });
      G.nodes.forEach(nd=>{
        const isHi = hi && nd.id.toLowerCase().includes(hi);
        const r = 4 + Math.min(6, nd.imports||0);
        ctx.beginPath(); ctx.arc(nd.x,nd.y,r,0,Math.PI*2);
        ctx.fillStyle = nd.type==='entry' ? '#ffcf57' : (isHi ? '#eafcff' : '#00CFFF');
        ctx.shadowColor = isHi ? '#eafcff' : 'rgba(0,207,255,.6)'; ctx.shadowBlur = isHi?14:6;
        ctx.fill(); ctx.shadowBlur=0;
        if(isHi || nd.type==='entry'){ ctx.fillStyle='#bfefff'; ctx.font='9px monospace';
          ctx.fillText(nd.label, nd.x+r+2, nd.y+3); }
      });
    }
    function run(){ let t=0; cancelAnimationFrame(anim);
      (function loop(){ if(!cv.isConnected) return; if(t++<240) step(); draw(); anim=requestAnimationFrame(loop); })(); }

    async function scan(){
      const p = pathIn.value.trim() || 'core';
      stat.textContent='◌ scanning…';
      try{
        const j = await apiPost('/knowledge/graph', {project_path:p, max_nodes:200});
        if(j.status==='ok'){ G={nodes:j.nodes, edges:j.edges}; stat.textContent=`${j.node_count} nodes · ${j.edge_count} edges`;
          layout(); run(); }
        else stat.textContent='⚠ '+(j.detail||j.error||'scan failed');
      }catch(e){ stat.textContent='⚠ '+e.message; }
    }
    wrap.querySelector('.cg-scan').addEventListener('click', e=>{ e.stopPropagation(); scan(); });
    pathIn.addEventListener('keydown', e=>{ if(e.key==='Enter') scan(); e.stopPropagation(); });
    search.addEventListener('input', e=>{ hi = e.target.value.trim().toLowerCase(); });
    search.addEventListener('keydown', e=>e.stopPropagation());
    cv.addEventListener('click', ev=>{ const r=cv.getBoundingClientRect();
      const mx=ev.clientX-r.left, my=ev.clientY-r.top;
      const hit=G.nodes.find(nd=>Math.hypot(nd.x-mx,nd.y-my)<8);
      selEl.textContent = hit ? `${hit.id}  ·  imports:${hit.imports} exports:${hit.exports} ${hit.type==='entry'?'· ENTRY':''}` : ''; });

    const w = shell('codegraph','CODE GRAPH', wrap, 'cgraph');
    scan();
    return w;
  };

  // ── Approvals Panel (A16) — YELLOW/RED actions awaiting human sign-off ──────
  F.approvals = function(){
    const wrap = el('div','apv-wrap');
    const badge = el('div','apv-badge', '<span class="apv-count">0</span> PENDING');
    const list  = el('div','apv-list');
    wrap.appendChild(badge);
    wrap.appendChild(list);
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';
    let pollId = null;

    function renderApprovals(items){
      const count = badge.querySelector('.apv-count');
      if(count) count.textContent = items.length;
      list.innerHTML = '';
      if(!items.length){
        list.innerHTML = '<div class="apv-empty">NO PENDING APPROVALS</div>';
        return;
      }
      items.forEach(item=>{
        const isRed = (item.level||'').toUpperCase() === 'RED';
        const ts = item.timestamp ? new Date(item.timestamp).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '';
        const card = el('div','apv-card '+(isRed?'apv-red':'apv-yellow'));
        card.innerHTML =
          `<div class="apv-head">
             <span class="apv-type">${item.action_type||item.id}</span>
             <span class="badge2 ${isRed?'crit':'high'}">${(item.level||'?').toUpperCase()}</span>
             <span class="apv-ts">${ts}</span>
           </div>
           <div class="apv-desc">${item.proposed_by || ''}${item.params ? ' · '+JSON.stringify(item.params).slice(0,80) : ''}</div>
           <div class="apv-btns">
             <button class="apv-ok">APPROVE</button>
             <button class="apv-no">REJECT</button>
           </div>`;
        const id = item.id || item.action_type;
        card.querySelector('.apv-ok').addEventListener('click', async e=>{
          e.stopPropagation(); card.style.opacity='.4';
          try{
            await apiPost('/gateway/approve/'+encodeURIComponent(id), {});
            V.say('Approved — '+id+' executing.');
          }catch(err){ card.style.opacity='1'; }
          refresh();
        });
        card.querySelector('.apv-no').addEventListener('click', async e=>{
          e.stopPropagation(); card.style.opacity='.4';
          try{
            await apiPost('/gateway/reject/'+encodeURIComponent(id), {});
            V.say('Rejected — '+id+' blocked.');
          }catch(err){ card.style.opacity='1'; }
          refresh();
        });
        list.appendChild(card);
      });
    }

    async function refresh(){
      try{
        const j = await apiGet('/gateway/pending');
        renderApprovals(j.pending||[]);
      }catch(e){ /* backend offline — keep last render */ }
    }

    const w = shell('approvals','APPROVALS', wrap, 'apv-panel');
    refresh();
    // auto-poll every 5 s while the widget is in the DOM
    pollId = setInterval(()=>{ if(!w.isConnected){ clearInterval(pollId); return; } refresh(); }, 5000);
    return w;
  };

  // ── Chat (LibreChat iframe) ───────────────────────────────────────────────
  F.librechat = function(){
    const frame = el('iframe');
    frame.src = 'http://localhost:3080';
    frame.style.cssText = 'width:100%;height:100%;border:none;border-radius:4px;';
    frame.setAttribute('allow', 'microphone; camera');
    return shell('librechat','CHAT · LIBRECHAT', frame, 'iframe-panel');
  };

  // ── Knowledge (Open WebUI iframe) ────────────────────────────────────────
  F.openwebui = function(){
    const frame = el('iframe');
    frame.src = 'http://localhost:8080';
    frame.style.cssText = 'width:100%;height:100%;border:none;border-radius:4px;';
    frame.setAttribute('allow', 'microphone; camera');
    return shell('openwebui','KNOWLEDGE · OPEN WEBUI', frame, 'iframe-panel');
  };

  // ── ComfyUI (full node-editor web UI iframe) ─────────────────────────────
  // Bespoke iframe to the running ComfyUI server at :8188 — defined here so it
  // takes precedence over the generic feature-registry status panel (the
  // registry only fills F[id] when no bespoke renderer exists). This makes the
  // panel actually usable for image/video generation, like librechat/openwebui.
  F.comfyui = function(){
    const frame = el('iframe');
    frame.src = 'http://127.0.0.1:8188';
    frame.style.cssText = 'width:100%;height:100%;border:none;border-radius:4px;';
    return shell('comfyui','MEDIA · COMFYUI', frame, 'iframe-panel');
  };

  // ── Finance Panel ─────────────────────────────────────────────────────────
  F.finance = function(){
    const wrap = el('div','fin-wrap');
    wrap.innerHTML = `
      <div class="fin-summary">
        <div class="fin-kv"><span class="k">PORTFOLIO VALUE</span><span class="v fin-pv">—</span></div>
        <div class="fin-kv"><span class="k">DAY P&amp;L</span><span class="v fin-pl">—</span></div>
        <div class="fin-mkt">
          <span class="fin-ms" data-mkt="us">US ·</span>
          <span class="fin-ms" data-mkt="india">IN ·</span>
          <span class="fin-ms" data-mkt="crypto">CRYPTO ·</span>
        </div>
      </div>
      <div class="fin-lbl">POSITIONS</div>
      <div class="fin-positions"><div class="fin-empty">No positions loaded</div></div>
      <div class="fin-lbl" style="margin-top:8px">ALERTS</div>
      <div class="fin-alerts"><div class="fin-empty">No alerts</div></div>`;
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    async function loadPortfolio(){
      try{
        const j = await apiGet('/investment/portfolio');
        const pv = wrap.querySelector('.fin-pv');
        const pl = wrap.querySelector('.fin-pl');
        if(pv) pv.textContent = j.portfolio_value != null ? '₹'+Number(j.portfolio_value).toLocaleString() : '—';
        if(pl){
          const sign = j.day_pnl >= 0 ? '▲' : '▼';
          pl.textContent = (j.day_pnl != null ? sign+' ₹'+Math.abs(j.day_pnl).toLocaleString() : '—');
          pl.style.color = j.day_pnl >= 0 ? 'var(--ok)' : 'var(--danger)';
        }
        const posEl = wrap.querySelector('.fin-positions');
        if(posEl && j.positions && j.positions.length){
          posEl.innerHTML = j.positions.map(p=>
            `<div class="fin-pos"><span>${p.symbol}</span><span>${p.qty}</span><span style="color:${(p.pnl||0)>=0?'var(--ok)':'var(--danger)'}">${(p.pnl||0)>=0?'▲':'▼'}${Math.abs(p.pnl||0).toFixed(2)}</span></div>`
          ).join('');
        }
        const altEl = wrap.querySelector('.fin-alerts');
        if(altEl && j.alerts && j.alerts.length){
          altEl.innerHTML = j.alerts.map(a=>`<div class="fin-alert-row">${a}</div>`).join('');
        }
      }catch(e){ /* backend offline */ }
    }

    async function loadMarketStatus(){
      try{
        const j = await apiGet('/investment/market-status');
        ['us','india','crypto'].forEach(k=>{
          const el2 = wrap.querySelector(`[data-mkt="${k}"]`);
          if(!el2) return;
          const info = j[k]||{};
          el2.textContent = (info.label||k.toUpperCase())+' · '+(info.open?'OPEN':'CLOSED');
          el2.style.color = info.open ? 'var(--ok)' : 'var(--txt-mute)';
        });
      }catch(e){ /* backend offline */ }
    }

    const w = shell('finance','FINANCE · PORTFOLIO', wrap, 'fin-panel');
    loadPortfolio();
    loadMarketStatus();
    return w;
  };

  // ── Content Scheduler Panel ────────────────────────────────────────────────
  F.contentscheduler = function(){
    const wrap = el('div','csch-wrap');
    wrap.innerHTML = `
      <div class="csch-tabs">
        <button class="csch-tab on" data-tab="queue">QUEUE</button>
        <button class="csch-tab" data-tab="compose">COMPOSE</button>
        <button class="csch-tab" data-tab="analytics">ANALYTICS</button>
      </div>
      <div class="csch-pane" id="csch-queue">
        <div class="csch-list"></div>
        <button class="csch-run">▶ RUN ALL PENDING</button>
      </div>
      <div class="csch-pane" id="csch-compose" style="display:none">
        <input class="csch-title" placeholder="Post title…"/>
        <textarea class="csch-content" placeholder="Content…"></textarea>
        <div class="csch-platforms">
          <label><input type="checkbox" value="twitter"> Twitter</label>
          <label><input type="checkbox" value="linkedin"> LinkedIn</label>
          <label><input type="checkbox" value="devto"> Dev.to</label>
          <label><input type="checkbox" value="hashnode"> Hashnode</label>
          <label><input type="checkbox" value="medium"> Medium</label>
        </div>
        <button class="csch-submit">SCHEDULE POST</button>
        <div class="csch-status"></div>
      </div>
      <div class="csch-pane" id="csch-analytics" style="display:none">
        <div class="csch-anl-list"></div>
      </div>`;
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    // Tab switching
    wrap.querySelectorAll('.csch-tab').forEach(btn=>{
      btn.addEventListener('click', e=>{
        e.stopPropagation();
        wrap.querySelectorAll('.csch-tab').forEach(b=>b.classList.remove('on'));
        btn.classList.add('on');
        wrap.querySelectorAll('.csch-pane').forEach(p=>p.style.display='none');
        const pane = wrap.querySelector('#csch-'+btn.dataset.tab);
        if(pane) pane.style.display='block';
      });
    });

    // Stop keydown propagation inside form fields
    wrap.querySelectorAll('input,textarea').forEach(f=>f.addEventListener('keydown',e=>e.stopPropagation()));

    async function loadQueue(){
      try{
        const j = await apiGet('/content/scheduled');
        const listEl = wrap.querySelector('.csch-list');
        if(!listEl) return;
        const entries = Object.entries(j).filter(([k])=>k!=='error');
        if(!entries.length){ listEl.innerHTML='<div class="fin-empty">Queue empty</div>'; return; }
        listEl.innerHTML = entries.map(([status,count])=>
          `<div class="csch-row"><span class="csch-status-label ${status}">${status.toUpperCase()}</span><span class="csch-cnt">${count}</span></div>`
        ).join('');
      }catch(e){ /* offline */ }
    }

    wrap.querySelector('.csch-run').addEventListener('click', async e=>{
      e.stopPropagation();
      try{ await apiPost('/content/run', {}); loadQueue(); }catch(err){}
    });

    wrap.querySelector('.csch-submit').addEventListener('click', async e=>{
      e.stopPropagation();
      const title   = wrap.querySelector('.csch-title').value.trim();
      const content = wrap.querySelector('.csch-content').value.trim();
      const platforms = [...wrap.querySelectorAll('.csch-platforms input:checked')].map(i=>i.value);
      const stat = wrap.querySelector('.csch-status');
      if(!title || !content || !platforms.length){ stat.textContent='Fill title, content, and pick a platform.'; return; }
      stat.textContent = '◌ scheduling…';
      try{
        const j = await apiPost('/content/schedule', {title, content, platforms});
        stat.textContent = j.status==='ok' ? '✓ scheduled!' : '⚠ '+JSON.stringify(j);
        loadQueue();
      }catch(err){ stat.textContent='⚠ '+err.message; }
    });

    const w = shell('contentscheduler','CONTENT SCHEDULER', wrap, 'csch-panel');
    loadQueue();
    return w;
  };

  // ── Answer Engine Panel (Vane / SearXNG) ─────────────────────────────────
  F.answerengine = function(){
    const wrap = el('div','ae-wrap');
    wrap.innerHTML = `
      <div class="ae-search">
        <input class="ae-input" placeholder="Ask anything…"/>
        <button class="ae-btn">SEARCH</button>
      </div>
      <div class="ae-results"></div>`;
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';
    const input = wrap.querySelector('.ae-input');
    const results = wrap.querySelector('.ae-results');
    wrap.querySelector('.ae-btn').addEventListener('click', async e=>{
      e.stopPropagation();
      const q = input.value.trim();
      if(!q) return;
      results.innerHTML = '<div class="ae-loading">◌ Searching…</div>';
      try {
        const j = await apiGet('/research/search?query='+encodeURIComponent(q));
        const items = j.results || [];
        results.innerHTML = items.length ? items.map(i=>
          `<div class="ae-item">
             <a href="${i.url||'#'}" class="ae-title" target="_blank">${i.title||'Result'}</a>
             <div class="ae-snippet">${i.snippet||i.content||''}</div>
           </div>`).join('') : '<div class="ae-empty">No results</div>';
      } catch(e) { results.innerHTML = '<div class="ae-empty">Search unavailable</div>'; }
    });
    input.addEventListener('keydown', e=>{ if(e.key==='Enter'){e.stopPropagation();wrap.querySelector('.ae-btn').click();} });
    return shell('answerengine','ANSWER ENGINE', wrap, 'ae-panel');
  };

  // ── GOAP Goal Planner (ruflo) ─────────────────────────────────────────────
  F.goalplanner = function(){
    const wrap = el('div','gp-wrap');
    wrap.innerHTML = `
      <div class="gp-horizons">
        <div class="gp-h"><div class="gp-hlabel">LONG</div><div class="gp-list" id="gp-long"></div></div>
        <div class="gp-h"><div class="gp-hlabel">MID</div><div class="gp-list" id="gp-mid"></div></div>
        <div class="gp-h"><div class="gp-hlabel">SHORT</div><div class="gp-list" id="gp-short"></div></div>
      </div>`;
    const API = (global.VECTOR_CFG && global.VECTOR_CFG.api) || '';

    function pct(p){ return Math.max(0,Math.min(100,Math.round((p||0)*100))); }

    async function loadGoals(){
      try{
        const j = await apiGet('/brain/goals');
        const goals = j.goals || (Array.isArray(j)?j:[]);
        ['long','mid','short'].forEach(h=>{
          const listEl = wrap.querySelector('#gp-'+h);
          if(!listEl) return;
          const hGoals = goals.filter(g=>(g.horizon||'').toLowerCase()===h);
          if(!hGoals.length){ listEl.innerHTML='<div class="gp-empty">—</div>'; return; }
          listEl.innerHTML = hGoals.map(g=>{
            const p = pct(g.progress);
            const pri = (g.priority||0) >= 8 ? 'crit' : (g.priority||0) >= 5 ? 'high' : 'med';
            return `<div class="gp-goal">
              <div class="gp-gtitle"><span class="badge2 ${pri}">${g.priority||0}</span>${g.title||g.id}</div>
              <div class="gp-bar"><div class="gp-fill" style="width:${p}%"></div></div>
              <div class="gp-meta">${p}% · ${(g.tags||[]).slice(0,2).join(' · ')}</div>
            </div>`;
          }).join('');
        });
      }catch(e){ /* offline */ }
    }

    const w = shell('goalplanner','GOAL PLANNER · HORIZONS', wrap, 'gp-panel');
    loadGoals();
    setInterval(()=>{ if(w.isConnected) loadGoals(); }, 30000);
    return w;
  };

  // Backend feature launcher: keeps mounted API domains openable without
  // pretending every domain already has a bespoke HUD design.
  const FEATURE_REGISTRY = [
    { id:'features', title:'BACKEND FEATURES', summary:'Mounted main-API feature map and launch surface.', health:'/world/snapshot', endpoints:['/world/snapshot','/status','/system','/health','/health/production-readiness','/tools/registry','/providers/routes'] },
    { id:'missioncontrol', title:'MISSION CONTROL', summary:'Create, decompose, review, run, recover, and inspect gateway-safe missions.', health:'/missions', endpoints:['/missions','/missions/jobs','/missions/{id}/timeline','/missions/{id}/artifacts','/missions/{id}/retry','/missions/{id}/rollback','/missions/decompose','/missions/advise','/missions/plan','/missions/run','/missions/run-async'] },
    { id:'corepanel', title:'CORE SYSTEMS', summary:'Core folder coverage: brain, loop, memory, inference, voice, sensing, media, research, safety, telemetry, trading, and platform internals.', health:'/world/snapshot', endpoints:['/world/snapshot','/status','/system','/health','/loop/status','/brain/goals','/memory/recent','/inference/stats','/voice/status','/sensing/status','/media/models','/research/status','/security/status','/tools/registry','/providers/routes','/metering/status','/scheduler/jobs','/sandbox/status','/mcp/status','/network/peers','/investment/market-status'] },
    { id:'agentspanel', title:'AGENTS + A2A', summary:'Agent roster, awards, district invocation, and A2A sessions.', health:'/agents', endpoints:['/agents','/a2a/agents','/a2a/events','/city/districts','/city/dispatch'] },
    { id:'brainpanel', title:'BRAIN + REASONING', summary:'Goals, hypotheses, epistemic state, reasoning chains, and person models.', health:'/brain/epistemic/summary', endpoints:['/brain/goals','/brain/hypothesis/active','/brain/epistemic/summary','/brain/reasoning/chains','/brain/persons'] },
    { id:'knowledgepanel', title:'KNOWLEDGE GRAPH', summary:'Domain scan, wiki/graph merge, graph generation, and knowledge status.', health:'/knowledge/status', endpoints:['/knowledge/status','/knowledge/scan-domain','/knowledge/parse-wiki','/knowledge/merge-graph','/knowledge/graph'] },
    { id:'codeintel', title:'CODE INTEL', summary:'Repository search, index, symbol graph, impact, flow, context, and project health.', health:'/code-intel/status', endpoints:['/code-intel/status','/code-intel/health','/code-intel/projects','/code-intel/symbols','/code-intel/graph/circular'] },
    { id:'vectorcodepanel', title:'VECTORCODE', summary:'VectorCode launch and status bridge.', health:'/vectorcode/status', endpoints:['/vectorcode/status','/vectorcode/launch'] },
    { id:'trading', title:'INVESTMENT + TRADING', summary:'Investment analysis, DCF, alpha, hedge, portfolio, and market status.', health:'/investment/market-status', endpoints:['/investment/market-status','/investment/portfolio','/investment/research/skills','/investment/analyze','/investment/dcf','/investment/alpha','/investment/hedge'] },
    { id:'backtest', title:'BACKTEST', summary:'Main API backtest request surface. Deep swarm sessions live in the side backtest server.', health:'/investment/market-status', endpoints:['/investment/backtest','/investment/portfolio','/investment/market-status'] },
    { id:'hedgebot', title:'HEDGEBOT', summary:'Hedge intelligence status and hedge request endpoint.', health:'/investment/hedge/status', endpoints:['/investment/hedge/status','/investment/hedge','/investment/geopolitics'] },
    { id:'intelligencepanel', title:'INTELLIGENCE', summary:'Flights, vessels, satellites, conflicts, fires, outages, CCTV, reports, and pins.', health:'/intelligence/status', endpoints:['/intelligence/status','/intelligence/all','/intelligence/summary','/intelligence/report','/intelligence/flights','/intelligence/vessels','/intelligence/satellites','/intelligence/conflicts','/intelligence/pins'] },
    { id:'shadowbroker', title:'SHADOWBROKER', summary:'Geocode, layers, summary, pins, commands, SSE, and health.', health:'/sb/health', endpoints:['/sb/health','/sb/summary','/sb/layer/{name}','/sb/pins','/sb/cmd','/sb/sse'] },
    { id:'mediastudio', title:'MEDIA STUDIO', summary:'Main API media model catalog. Generation/status lives in the Studio side server.', health:'/media/models', endpoints:['/media/models','studio:/api/media/status','studio:/api/media/generate','studio:/api/media/models','studio:/api/workflows'] },
    { id:'comfyui', title:'COMFYUI', summary:'Local image/video generation adapter. Requires local ComfyUI; full controls are Studio-side today.', health:'/media/models', endpoints:['/media/models','studio:/api/media/status','comfyui:http://127.0.0.1:8188'] },
    { id:'hyperframes', title:'HYPERFRAMES', summary:'Video render sidecar used by composer fallback path. Main API exposes composition list only.', health:'/video/compositions', endpoints:['/video/compositions','sidecar:http://127.0.0.1:7421/render','studio:/render'] },
    { id:'contentpanel', title:'CONTENT OPS', summary:'Scheduled content queue, scheduling, run trigger, ads, SEO, and news operations.', health:'/content/scheduled', endpoints:['/content/scheduled','/content/schedule','/content/run','/ads/references','/seo/status','/news/daily-brief'] },
    { id:'designpanel', title:'DESIGN', summary:'Component specs, image prompts, UX research, and design tokens.', health:'/media/models', endpoints:['/design/component-spec','/design/image-prompt','/design/ux-research','/design/tokens'] },
    { id:'researchpanel', title:'RESEARCH', summary:'Search, news, papers, Reddit, and research status.', health:'/research/status', endpoints:['/research/status','/research/search?query=vector','/research/news','/research/papers','/research/reddit'] },
    { id:'pccontrol', title:'PC CONTROL', summary:'Local PC screenshot, type, click, and app launch gates. Phone endpoints are excluded.', health:'/sensing/status', endpoints:['/control/pc/screenshot','/control/pc/type','/control/pc/click','/control/pc/launch-app','/sensing/status','/sensing/screen'] },
    { id:'camerapanel', title:'CAMERA', summary:'Camera start/stop/status and visual sensing.', health:'/camera/status', endpoints:['/camera/status','/camera/start','/camera/stop','/sensing/health'] },
    { id:'healthpanel', title:'HEALTH', summary:'Fatigue, sleep, biometrics, exercise, and health/system status.', health:'/health/status', endpoints:['/health/status','/health/system','/health/production-readiness','/health/check-fatigue','/health/biometrics','/health/sleep','/health/exercise'] },
    { id:'learningpanel', title:'LEARNING', summary:'Video ingest, course tracking, concept extraction, quiz generation, languages, and skills.', health:'/skills/map', endpoints:['/skills/map','/learning/ingest-video','/learning/track-course','/learning/extract-concepts','/learning/quiz-generate','/languages/{lang}/study-guide'] },
    { id:'workpanel', title:'WORKFLOW + PROJECTS', summary:'Projects, tasks, scheduler jobs, queues, ops incidents, and chief briefs.', health:'/scheduler/jobs', endpoints:['/projects/list','/tasks/','/scheduler/jobs','/queue/retry/stats','/ops/slo-check','/chief/morning-brief'] },
    { id:'privacypanel', title:'PRIVACY + KEYS', summary:'Privacy scans, redaction, audit flow, key status, rotation, revocation, and OAuth integrations.', health:'/keys/status', endpoints:['/privacy/scan-sharing','/privacy/gdpr-check','/privacy/redact','/privacy/audit-flow','/keys/status','/oauth/integrations'] },
    { id:'analyticspanel', title:'ANALYTICS', summary:'Pipeline health, ETL runs, reports, and benchmarks.', health:'/analytics/pipeline-health', endpoints:['/analytics/pipeline-health','/analytics/etl-run','/analytics/report','/analytics/benchmark'] },
    { id:'personalpanel', title:'PERSONAL OS', summary:'Relationships, calls, reflection, patterns, interviews, startups, and simulations.', health:'/relationships/contacts', endpoints:['/relationships/contacts','/calls/contacts','/reflection/daily-review','/patterns/habits','/interview/start','/startups/validate-idea','/simulation/status'] },
    { id:'platformpanel', title:'PLATFORM', summary:'Collections, governance, migration, mining, scraper, sandbox, network, MCP, and mission execution.', health:'/mcp/status', endpoints:['/api/collections','/governance/autopilot/status','/migration/sources','/mining/status','/scraper/status','/sandbox/status','/network/peers','/mcp/status','/health/production-readiness','/missions','/missions/jobs','/missions/{id}/timeline','/missions/{id}/artifacts','/missions/{id}/retry','/missions/{id}/rollback','/missions/decompose','/missions/advise','/missions/plan','/missions/run','/missions/run-async'] }
  ];

  const FEATURE_BLUEPRINTS = {
    corepanel: { mode:'command core', focus:['runtime','brain','memory','safety'], widgets:['telemetry','brainpanel','memory','security'], reads:['/world/snapshot','/status','/system','/loop/status'] },
    agentspanel: { mode:'coordination', focus:['roster','A2A','districts','dispatch'], widgets:['districts','council','city3d'], reads:['/agents','/a2a/agents','/a2a/events','/city/districts'] },
    brainpanel: { mode:'reasoning', focus:['goals','hypotheses','epistemic state','persons'], widgets:['goals','goalplanner','council'], reads:['/brain/goals','/brain/hypothesis/active','/brain/epistemic/summary','/brain/reasoning/chains'] },
    knowledgepanel: { mode:'knowledge ops', focus:['status','domain scan','wiki parse','graph merge'], widgets:['codegraph','memory'], reads:['/knowledge/status'] },
    codeintel: { mode:'engineering intel', focus:['project health','symbols','context','circular graph'], widgets:['codegraph','vectorcodepanel'], reads:['/code-intel/status','/code-intel/health','/code-intel/projects','/code-intel/symbols'] },
    vectorcodepanel: { mode:'coding bridge', focus:['status','launch','sessions','tooling'], widgets:['codegraph','codeintel'], reads:['/vectorcode/status'] },
    trading: { mode:'market desk', focus:['market status','portfolio','research skills','analysis'], widgets:['finance','market','backtest','hedgebot'], reads:['/investment/market-status','/investment/portfolio','/investment/research/skills'] },
    backtest: { mode:'strategy lab', focus:['request surface','portfolio context','market state','side swarm'], widgets:['trading','hedgebot'], reads:['/investment/market-status','/investment/portfolio'] },
    hedgebot: { mode:'hedge desk', focus:['hedge status','geopolitics','risk','request queue'], widgets:['trading','market'], reads:['/investment/hedge/status','/investment/market-status'] },
    intelligencepanel: { mode:'signal room', focus:['summary','flights','vessels','conflicts'], widgets:['map','shadowbroker'], reads:['/intelligence/status','/intelligence/summary','/intelligence/all','/intelligence/flights'] },
    shadowbroker: { mode:'sidecar intel', focus:['health','summary','pins','layers'], widgets:['intelligencepanel','map'], reads:['/sb/health','/sb/summary','/sb/pins'] },
    mediastudio: { mode:'studio catalog', focus:['models','generation sidecar','workflows','status'], widgets:['comfyui','hyperframes','voicestudio'], reads:['/media/models'] },
    comfyui: { mode:'local generation', focus:['model catalog','ComfyUI sidecar','workflow queue','upload path'], widgets:['mediastudio','hyperframes'], reads:['/media/models'] },
    hyperframes: { mode:'video render', focus:['composition list','render sidecar','composer fallback','exports'], widgets:['mediastudio','comfyui'], reads:['/video/compositions'] },
    contentpanel: { mode:'growth ops', focus:['queue','schedule','ads','SEO'], widgets:['contentscheduler','researchpanel'], reads:['/content/scheduled','/ads/references','/seo/status','/news/daily-brief'] },
    designpanel: { mode:'design lab', focus:['component specs','image prompts','UX research','tokens'], widgets:['mediastudio','contentpanel'], reads:['/media/models'] },
    researchpanel: { mode:'research desk', focus:['status','search','news','papers'], widgets:['answerengine','knowledgepanel'], reads:['/research/status','/research/search?query=vector','/research/news','/research/papers'] },
    pccontrol: { mode:'local control', focus:['YELLOW gate','screenshot','type','click'], widgets:['security','approvals','webcam'], reads:['/sensing/status','/sensing/screen','/gateway/pending'] },
    camerapanel: { mode:'vision control', focus:['status','start','stop','sensing health'], widgets:['webcam','pccontrol'], reads:['/camera/status','/sensing/health'] },
    healthpanel: { mode:'body systems', focus:['fatigue','biometrics','sleep','exercise'], widgets:['telemetry','personalpanel'], reads:['/health/status','/health/system','/health/biometrics','/health/sleep'] },
    learningpanel: { mode:'learning stack', focus:['skills map','video ingest','courses','quiz'], widgets:['goalplanner','personalpanel'], reads:['/skills/map'] },
    workpanel: { mode:'operations', focus:['projects','tasks','scheduler','queue'], widgets:['goals','goalplanner','analyticspanel'], reads:['/projects/list','/tasks/','/scheduler/jobs','/queue/retry/stats'] },
    privacypanel: { mode:'trust boundary', focus:['privacy scan','redaction','key status','OAuth'], widgets:['security','approvals'], reads:['/keys/status','/oauth/integrations'] },
    analyticspanel: { mode:'data ops', focus:['pipeline','ETL','reports','benchmarks'], widgets:['telemetry','workpanel'], reads:['/analytics/pipeline-health'] },
    personalpanel: { mode:'personal OS', focus:['relationships','calls','reflection','patterns'], widgets:['memory','goals','healthpanel'], reads:['/relationships/contacts','/calls/contacts','/patterns/habits','/simulation/status'] },
    missioncontrol: { mode:'mission ops', focus:['objective','decompose','review','run'], widgets:['security','approvals','platformpanel'], reads:['/missions'] },
    platformpanel: { mode:'platform control', focus:['collections','governance','sandbox','missions'], widgets:['missioncontrol','security','telemetry','workpanel'], reads:['/api/collections','/governance/autopilot/status','/sandbox/status','/mcp/status','/missions'] }
  };

  function renderJsonPreview(data){
    const raw = JSON.stringify(data, null, 2);
    return escapeHtml(raw.length > 1400 ? raw.slice(0, 1400)+'\n...' : raw);
  }

  function previewValue(data){
    if(Array.isArray(data)) return data.length + ' items';
    if(!data || typeof data !== 'object') return data == null ? 'ok' : String(data).slice(0, 24);
    const keys = Object.keys(data);
    for(const k of ['status','state','health','threat_level','count','total','uptime_seconds']){
      if(data[k] != null) return String(data[k]).slice(0, 28);
    }
    for(const k of keys){
      const v = data[k];
      if(Array.isArray(v)) return `${k}: ${v.length}`;
      if(v && typeof v === 'object') return `${k}: ${Object.keys(v).length}`;
      if(v != null) return `${k}: ${String(v).slice(0, 18)}`;
    }
    return keys.length + ' keys';
  }

  function endpointMeta(path){
    const side = /^(studio:|sidecar:|comfyui:)/.test(path);
    const label = side ? path.replace(/^(studio:|sidecar:|comfyui:)/, '') : path;
    const safePrefixes = [
      '/world/snapshot','/status','/system','/health','/agents','/a2a/agents','/a2a/events',
      '/city/districts','/brain/goals','/brain/hypothesis/active','/brain/epistemic',
      '/brain/reasoning','/brain/persons','/knowledge/status','/code-intel/status',
      '/code-intel/health','/code-intel/projects','/code-intel/symbols',
      '/code-intel/graph/circular','/vectorcode/status','/investment/market-status',
      '/investment/portfolio','/investment/research/skills','/investment/hedge/status',
      '/intelligence','/sb/health','/sb/summary','/sb/pins','/media/models',
      '/video/compositions','/content/scheduled','/ads/references','/seo/status',
      '/news/daily-brief','/research','/sensing','/camera/status','/skills/map',
      '/relationships/contacts','/calls/contacts','/patterns/habits','/simulation/status',
      '/scheduler/jobs','/projects/list','/tasks/','/queue/retry/stats','/ops/slo-check',
      '/keys/status','/oauth/integrations','/analytics/pipeline-health',
      '/api/collections','/governance/autopilot/status','/migration/sources','/mining/status',
      '/scraper/status','/sandbox/status','/network/peers','/mcp/status','/tools/registry',
      '/providers/routes','/missions'
    ];
    const readable = !side && safePrefixes.some(prefix => path === prefix || path.startsWith(prefix+'/') || path.startsWith(prefix+'?'));
    return { label, readable, tag: side ? 'SIDE' : (readable ? 'GET' : 'ACTION') };
  }

  function missionStatusClass(status){
    status = String(status || '').toLowerCase();
    if(status === 'completed' || status === 'executed') return 'ok';
    if(status === 'blocked' || status === 'failed') return 'bad';
    if(status === 'running') return 'run';
    return 'plan';
  }

  function renderMissionSteps(steps){
    if(!steps || !steps.length) return '<div class="mc-empty">No steps planned.</div>';
    return steps.map((step, idx)=>`
      <div class="mc-step ${missionStatusClass(step.status)}">
        <div class="mc-step-head">
          <span>${escapeHtml(step.id || ('step-'+(idx+1)))}</span>
          <b>${escapeHtml(step.status || 'planned')}</b>
        </div>
        <div class="mc-action">${escapeHtml(step.action_type || 'respond')}</div>
        <div class="mc-meta">
          <span>${escapeHtml(step.source || 'explicit')}</span>
          <span>${Math.round(Number(step.confidence == null ? 1 : step.confidence) * 100)}%</span>
          ${step.requires_review ? '<span class="mc-review">REVIEW</span>' : ''}
        </div>
        <pre>${renderJsonPreview(step.params || {})}</pre>
      </div>`).join('');
  }

  function renderMissionList(missions){
    if(!missions || !missions.length) return '<div class="mc-empty">No missions yet.</div>';
    return missions.slice(0, 10).map(m=>`
      <button class="mc-mission ${missionStatusClass(m.status)}" data-id="${escapeHtml(m.id)}">
        <span>${escapeHtml(m.objective || m.id)}</span>
        <b>${escapeHtml(m.status || 'planned')}</b>
      </button>`).join('');
  }

  function renderMissionEvents(events){
    if(!events || !events.length) return '<div class="mc-empty">No timeline yet.</div>';
    return events.slice(-12).reverse().map(ev=>`
      <div class="mc-event">
        <div><b>${escapeHtml(ev.type || 'event')}</b><span>${escapeHtml((ev.timestamp || '').slice(11,19))}</span></div>
        <p>${escapeHtml(ev.message || '')}</p>
      </div>`).join('');
  }

  function renderMissionArtifacts(artifacts){
    if(!artifacts || !artifacts.length) return '<div class="mc-empty">No artifacts yet.</div>';
    return artifacts.slice(-8).reverse().map(a=>`
      <div class="mc-artifact">
        <div><b>${escapeHtml(a.title || 'Artifact')}</b><span>${escapeHtml(a.type || 'result')}</span></div>
        <pre>${renderJsonPreview(a.content || {})}</pre>
      </div>`).join('');
  }

  function actionTypeFromEndpoint(path){
    const known = {
      '/control/pc/screenshot':'pc_screenshot',
      '/control/pc/type':'pc_type',
      '/control/pc/click':'pc_click',
      '/control/pc/launch-app':'pc_launch_app',
      '/camera/start':'camera_start',
      '/camera/stop':'camera_stop',
      '/content/run':'content_run',
      '/privacy/redact':'privacy_redact',
      '/keys/rotate':'key_rotate',
      '/keys/revoke':'key_revoke'
    };
    if(known[path]) return known[path];
    return String(path || '')
      .replace(/\?.*$/, '')
      .replace(/^\//, '')
      .replace(/\{([^}]+)\}/g, '$1')
      .replace(/[^a-zA-Z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .toLowerCase() || 'unknown_action';
  }

  function makeFeaturePanel(cfg){
    const blueprint = FEATURE_BLUEPRINTS[cfg.id] || {
      mode:'main API',
      focus:['status','readouts','actions','links'],
      widgets:[],
      reads:(cfg.endpoints || []).filter(p=>endpointMeta(p).readable).slice(0, 4)
    };
    const readableEndpoints = (cfg.endpoints || []).filter(p=>endpointMeta(p).readable);
    const actionEndpoints = (cfg.endpoints || []).filter(p=>!endpointMeta(p).readable);
    const wrap = el('div','feature-wrap');
    wrap.innerHTML = `
      <div class="feature-hero">
        <div>
          <div class="feature-mode">${escapeHtml(blueprint.mode)}</div>
          <div class="feature-summary">${escapeHtml(cfg.summary)}</div>
        </div>
        <div class="feature-status">checking ${escapeHtml(cfg.health || cfg.endpoints[0] || '/status')}...</div>
      </div>
      <div class="feature-focus">${(blueprint.focus || []).map(x=>`<span>${escapeHtml(x)}</span>`).join('')}</div>
      <div class="feature-layout">
        <section class="feature-card-panel">
          <div class="feature-section-title">Live Readouts</div>
          <div class="feature-kpis"></div>
        </section>
        <section class="feature-card-panel">
          <div class="feature-section-title">Open Tools</div>
          <div class="feature-tools"></div>
        </section>
        <section class="feature-card-panel">
          <div class="feature-section-title">Endpoint Surface</div>
          <div class="feature-list"></div>
        </section>
        <section class="feature-card-panel">
          <div class="feature-section-title">Action Rail</div>
          <div class="feature-actions"></div>
        </section>
      </div>
      <pre class="feature-json"></pre>`;
    const status = wrap.querySelector('.feature-status');
    const list = wrap.querySelector('.feature-list');
    const json = wrap.querySelector('.feature-json');
    const kpis = wrap.querySelector('.feature-kpis');
    const tools = wrap.querySelector('.feature-tools');
    const actions = wrap.querySelector('.feature-actions');

    kpis.innerHTML = (blueprint.reads || readableEndpoints).slice(0, 6).map(path =>
      `<button class="feature-kpi" data-path="${escapeHtml(path)}"><span>${escapeHtml(path)}</span><b>...</b></button>`
    ).join('') || '<div class="feature-empty">No safe readouts exposed.</div>';

    tools.innerHTML = (blueprint.widgets || []).map(id =>
      `<button class="feature-tool" data-widget="${escapeHtml(id)}">${escapeHtml(id)}</button>`
    ).join('') || '<div class="feature-empty">No linked widget.</div>';

    list.innerHTML = readableEndpoints.map(path => {
      const meta = endpointMeta(path);
      return `<button class="feature-endpoint" data-path="${escapeHtml(path)}"><span>${meta.tag}</span> ${escapeHtml(meta.label)}</button>`;
    }).join('') || '<div class="feature-empty">No direct main-API reads.</div>';

    actions.innerHTML = actionEndpoints.map(path => {
      const meta = endpointMeta(path);
      return `<button class="feature-action" data-path="${escapeHtml(path)}"><span>${meta.tag}</span> ${escapeHtml(meta.label)}</button>`;
    }).join('') || '<div class="feature-empty">No gated actions listed.</div>';

    async function check(){
      if(!cfg.health || /^(studio:|sidecar:|comfyui:)/.test(cfg.health)){
        status.textContent = 'side system: status is outside the main API';
        return;
      }
      try{
        const data = await apiGet(cfg.health);
        status.textContent = 'online: '+cfg.health;
        json.textContent = renderJsonPreview(data);
      }catch(e){
        status.textContent = 'unavailable: '+cfg.health;
        json.textContent = e.message || String(e);
      }
    }

    async function loadPath(path, label){
      try{
        status.textContent = 'loading '+(label || path);
        const data = await apiGet(path);
        status.textContent = 'loaded '+path;
        json.textContent = renderJsonPreview(data);
        return data;
      }catch(err){
        status.textContent = 'request failed: '+path;
        json.textContent = err.message || String(err);
        throw err;
      }
    }

    list.addEventListener('click', async e=>{
      const btn = e.target.closest('.feature-endpoint');
      if(!btn) return;
      await loadPath(btn.dataset.path).catch(()=>{});
    });

    kpis.addEventListener('click', async e=>{
      const btn = e.target.closest('.feature-kpi');
      if(!btn) return;
      await loadPath(btn.dataset.path).catch(()=>{});
    });

    tools.addEventListener('click', e=>{
      const btn = e.target.closest('.feature-tool');
      if(btn) V.openWidget(btn.dataset.widget);
    });

    actions.addEventListener('click', async e=>{
      const btn = e.target.closest('.feature-action');
      if(!btn) return;
      const path = btn.dataset.path;
      const actionType = actionTypeFromEndpoint(path);
      status.textContent = 'planning gated action: '+actionType;
      try{
        const data = await apiPost('/execute/plan', {
          action_type: actionType,
          params: { endpoint: path },
          proposed_by: 'hud.'+cfg.id
        });
        status.textContent = 'plan ready: '+actionType;
        json.textContent = renderJsonPreview(data);
      }catch(err){
        status.textContent = 'plan failed: '+actionType;
        json.textContent = err.message || String(err);
      }
    });

    async function hydrateReadouts(){
      const buttons = [...kpis.querySelectorAll('.feature-kpi')];
      for(const btn of buttons){
        try{
          const data = await apiGet(btn.dataset.path);
          const val = btn.querySelector('b');
          if(val) val.textContent = previewValue(data);
        }catch(err){
          const val = btn.querySelector('b');
          if(val) val.textContent = 'offline';
        }
      }
    }

    const w = shell(cfg.id, cfg.title, wrap, 'feature-panel');
    check();
    hydrateReadouts();
    return w;
  }

  F.missioncontrol = function(){
    const wrap = el('div','mc-wrap');
    wrap.innerHTML = `
      <div class="mc-top">
        <textarea class="mc-objective" spellcheck="false" placeholder="mission objective"></textarea>
        <div class="mc-actions">
          <button class="mc-btn primary" data-act="decompose">DECOMPOSE</button>
          <button class="mc-btn" data-act="advise">LLM PLAN</button>
          <button class="mc-btn" data-act="plan">PLAN</button>
          <button class="mc-btn" data-act="dry">DRY RUN</button>
          <button class="mc-btn danger" data-act="run">RUN</button>
          <button class="mc-btn" data-act="retry">RETRY</button>
          <button class="mc-btn danger" data-act="rollback">ROLLBACK</button>
          <button class="mc-btn" data-act="refresh">REFRESH</button>
        </div>
      </div>
      <div class="mc-grid">
        <section class="mc-pane">
          <div class="mc-title">Mission History</div>
          <div class="mc-list"></div>
        </section>
        <section class="mc-pane">
          <div class="mc-title">Review Steps</div>
          <div class="mc-status">idle</div>
          <div class="mc-steps"></div>
        </section>
        <section class="mc-pane">
          <div class="mc-title">Timeline</div>
          <div class="mc-events"></div>
        </section>
        <section class="mc-pane">
          <div class="mc-title">Artifacts</div>
          <div class="mc-artifacts"></div>
        </section>
      </div>
      <pre class="feature-json mc-json"></pre>`;
    const input = wrap.querySelector('.mc-objective');
    const list = wrap.querySelector('.mc-list');
    const stepsEl = wrap.querySelector('.mc-steps');
    const eventsEl = wrap.querySelector('.mc-events');
    const artifactsEl = wrap.querySelector('.mc-artifacts');
    const status = wrap.querySelector('.mc-status');
    const json = wrap.querySelector('.mc-json');
    let currentMission = null;
    let pollJobId = null;
    let pollTimer = null;

    async function loadMissions(){
      try{
        const data = await apiGet('/missions');
        list.innerHTML = renderMissionList(data.missions || []);
        if(!currentMission && data.missions && data.missions.length) selectMission(data.missions[0]);
        return data;
      }catch(err){
        list.innerHTML = '<div class="mc-empty">Missions unavailable.</div>';
        status.textContent = 'backend unavailable';
        json.textContent = err.message || String(err);
      }
    }

    function selectMission(mission){
      currentMission = mission;
      input.value = mission.objective || input.value;
      status.textContent = (mission.review_required ? 'review required: ' : '') + (mission.reason || mission.status || 'planned');
      stepsEl.innerHTML = renderMissionSteps(mission.steps || []);
      eventsEl.innerHTML = renderMissionEvents(mission.events || []);
      artifactsEl.innerHTML = renderMissionArtifacts(mission.artifacts || []);
      json.textContent = renderJsonPreview(mission);
    }

    async function postMission(path, extra){
      const objective = input.value.trim();
      if(!objective){
        status.textContent = 'objective required';
        return null;
      }
      status.textContent = 'posting '+path;
      const data = await apiPost(path, Object.assign({
        objective,
        decompose: true,
        proposed_by: 'hud.missioncontrol'
      }, extra || {}));
      const mission = data.mission || null;
      if(mission) selectMission(mission);
      else {
        status.textContent = data.status || 'decomposed';
        const decomposition = data.decomposition || {};
        stepsEl.innerHTML = renderMissionSteps(decomposition.steps || []);
        json.textContent = renderJsonPreview(data);
      }
      await loadMissions();
      return data;
    }

    function stopJobPoll(){
      if(pollTimer) clearInterval(pollTimer);
      pollTimer = null;
      pollJobId = null;
    }

    async function pollJob(jobId){
      if(!jobId) return;
      pollJobId = jobId;
      try{
        const data = await apiGet('/missions/jobs/'+encodeURIComponent(jobId));
        const job = data.job || {};
        if(data.mission) selectMission(data.mission);
        status.textContent = 'job '+job.id+' · '+job.status;
        json.textContent = renderJsonPreview(data);
        if(['completed','blocked','failed','cancelled'].includes(String(job.status || '').toLowerCase())){
          stopJobPoll();
          await loadMissions();
        }
      }catch(err){
        status.textContent = 'job poll failed';
        json.textContent = err.message || String(err);
        stopJobPoll();
      }
    }

    function startJobPoll(jobId){
      stopJobPoll();
      pollJobId = jobId;
      pollJob(jobId);
      pollTimer = setInterval(()=>{
        if(!wrap.isConnected){ stopJobPoll(); return; }
        pollJob(pollJobId);
      }, 1400);
    }

    async function runAsync(){
      const data = await postMission('/missions/run-async', { dry_run:false });
      const job = data && data.job;
      if(job && job.id) startJobPoll(job.id);
      return data;
    }

    async function recoverMission(kind){
      if(!currentMission || !currentMission.id){
        status.textContent = 'select a mission first';
        return null;
      }
      const path = '/missions/'+encodeURIComponent(currentMission.id)+'/'+kind;
      const body = kind === 'rollback'
        ? { reason:'Owner requested rollback review from Mission Control.' }
        : {};
      status.textContent = kind+' requested';
      const data = await apiPost(path, body);
      if(data.mission) selectMission(data.mission);
      await loadMissions();
      return data;
    }

    wrap.querySelector('.mc-actions').addEventListener('click', async e=>{
      const btn = e.target.closest('[data-act]');
      if(!btn) return;
      const act = btn.dataset.act;
      try{
        if(act === 'refresh') await loadMissions();
        if(act === 'decompose') await postMission('/missions/decompose');
        if(act === 'advise') await postMission('/missions/advise');
        if(act === 'plan') await postMission('/missions/plan');
        if(act === 'dry') await postMission('/missions/run', { dry_run:true });
        if(act === 'run') await runAsync();
        if(act === 'retry') await recoverMission('retry');
        if(act === 'rollback') await recoverMission('rollback');
      }catch(err){
        status.textContent = 'request failed';
        json.textContent = err.message || String(err);
      }
    });

    list.addEventListener('click', async e=>{
      const btn = e.target.closest('.mc-mission');
      if(!btn) return;
      try{
        const data = await apiGet('/missions/'+encodeURIComponent(btn.dataset.id));
        selectMission(data.mission);
      }catch(err){
        status.textContent = 'load failed';
        json.textContent = err.message || String(err);
      }
    });

    const w = shell('missioncontrol','MISSION CONTROL', wrap, 'mission-panel feature-panel');
    loadMissions();
    const cleanup = setInterval(()=>{ if(!w.isConnected){ clearInterval(cleanup); stopJobPoll(); } }, 2000);
    return w;
  };

  const CORE_GROUPS = [
    { title:'BRAIN + LOOP', copy:'Decision engine, context hydration, goals, autonomous loop, planner, nudges, task queue.', widgets:['brainpanel','goals','goalplanner'], endpoints:['/brain/goals','/brain/epistemic/summary','/brain/reasoning/chains','/loop/status','/tasks/'] },
    { title:'CITY + AGENTS', copy:'Governor, agent registry, A2A sessions, district dispatch, HP/evolution contracts.', widgets:['agentspanel','districts','council','city3d'], endpoints:['/agents','/a2a/agents','/city/districts','/city/evolution/generations'] },
    { title:'MEMORY + KNOWLEDGE', copy:'Episodic/semantic/policy memory, reasoning chains, Obsidian sync, graph merge.', widgets:['memory','knowledgepanel'], endpoints:['/memory/recent','/memory/goals','/memory/council/history','/knowledge/status'] },
    { title:'INFERENCE', copy:'Provider routing, model catalogs, smart routing, fallback chain, budget-aware inference.', widgets:['telemetry'], endpoints:['/inference/stats','/inference/models','/inference/providers','/providers/routes'] },
    { title:'VOICE', copy:'Wake word, STT/TTS, profiles, cloning, streamer, ambient listener, voice studio.', widgets:['voicestudio'], endpoints:['/voice/status','/voice/profiles','/voice/studio/generate'] },
    { title:'SENSING + CONTROL', copy:'Camera, screen observer, PC control, GUI/browser control, local sensing.', widgets:['camerapanel','webcam','pccontrol'], endpoints:['/sensing/status','/sensing/health','/camera/status','/control/pc/screenshot'] },
    { title:'SAFETY', copy:'Permission gateway, prompt-injection guard, SSRF guard, taint tracking, audit, keys.', widgets:['security','approvals','privacypanel'], endpoints:['/security/status','/gateway/pending','/audit/recent','/keys/status'] },
    { title:'RESEARCH + SCRAPER', copy:'Advanced search engine, citations, library tools, stealth browser, adaptive scraper.', widgets:['researchpanel','answerengine'], endpoints:['/research/status','/research/search?query=vector','/scraper/status'] },
    { title:'MEDIA + VIDEO', copy:'Generative studio, media model catalog, image/video providers, composer, Hyperframes sidecar.', widgets:['mediastudio','comfyui','hyperframes'], endpoints:['/media/models','/video/compositions'] },
    { title:'TRADING', copy:'Core trading agents, analysts, researchers, risk managers, market status bridge.', widgets:['trading','backtest','hedgebot'], endpoints:['/investment/market-status','/investment/portfolio','/finance/cost-tracker'] },
    { title:'TELEMETRY + RESILIENCE', copy:'GPU/energy metrics, metering, rate limits, circuit breakers, recovery playbooks.', widgets:['telemetry','platformpanel'], endpoints:['/system','/metering/status','/queue/retry/stats','/sandbox/status'] },
    { title:'PLATFORM', copy:'Collections, scheduler, MCP, network peers, sandbox, audit, mission execution, API middleware/runtime.', widgets:['missioncontrol','platformpanel','workpanel'], endpoints:['/api/collections','/scheduler/jobs','/mcp/status','/network/peers','/tools/registry','/missions'] }
  ];

  F.corepanel = function(){
    const wrap = el('div','core-wrap');
    wrap.innerHTML = `
      <div class="core-top">
        <div><span class="core-k">CORE MODULES</span><span class="core-v">${CORE_GROUPS.length}</span></div>
        <div><span class="core-k">MODE</span><span class="core-v">MAIN API</span></div>
        <div><span class="core-k">UI</span><span class="core-v">VANILLA HUD</span></div>
      </div>
      <div class="core-grid"></div>
      <pre class="feature-json core-json"></pre>`;
    const grid = wrap.querySelector('.core-grid');
    const json = wrap.querySelector('.core-json');
    grid.innerHTML = CORE_GROUPS.map((g, idx)=>`
      <div class="core-card" data-idx="${idx}">
        <div class="core-card-head">
          <span>${escapeHtml(g.title)}</span>
          <button class="core-open" data-widget="${escapeHtml(g.widgets[0])}">OPEN</button>
        </div>
        <div class="core-copy">${escapeHtml(g.copy)}</div>
        <div class="core-widgets">${g.widgets.map(w=>`<button data-widget="${escapeHtml(w)}">${escapeHtml(w)}</button>`).join('')}</div>
      </div>`).join('');
    grid.addEventListener('click', async e=>{
      const wbtn = e.target.closest('[data-widget]');
      if(wbtn){
        V.openWidget(wbtn.dataset.widget);
        return;
      }
      const card = e.target.closest('.core-card');
      if(!card) return;
      const group = CORE_GROUPS[Number(card.dataset.idx)];
      json.textContent = 'Checking '+group.title+'...\n'+group.endpoints.join('\n');
      const results = [];
      for(const path of group.endpoints){
        try{
          const data = await apiGet(path);
          results.push({ path, ok:true, preview:data });
        }catch(err){
          results.push({ path, ok:false, error:err.message || String(err) });
        }
      }
      json.textContent = renderJsonPreview(results);
    });
    return shell('corepanel','CORE SYSTEMS', wrap, 'core-panel feature-panel');
  };

  function registerFeaturePanels(){
    FEATURE_REGISTRY.forEach(cfg=>{
      if(cfg.id === 'features') return;
      if(!F[cfg.id]) F[cfg.id] = function(){ return makeFeaturePanel(cfg); };
    });
  }

  F.features = function(){
    const wrap = el('div','feature-index');
    wrap.innerHTML = FEATURE_REGISTRY.filter(f=>f.id !== 'features').map(f=>`
      <button class="feature-card" data-id="${escapeHtml(f.id)}">
        <span class="feature-card-title">${escapeHtml(f.title)}</span>
        <span class="feature-card-copy">${escapeHtml(f.summary)}</span>
      </button>`).join('');
    wrap.addEventListener('click', e=>{
      const card = e.target.closest('.feature-card');
      if(card) V.openWidget(card.dataset.id);
    });
    return shell('features','BACKEND FEATURES', wrap, 'feature-panel');
  };

  registerFeaturePanels();
  global.VectorFeatureRegistry = FEATURE_REGISTRY.slice();

  // ---- open / close -------------------------------------------------------
  function openWidget(id, opts){
    if(live[id]){ flash(live[id]); return live[id]; }
    const make = F[id]; if(!make){ console.warn('no widget', id); return; }
    const w = make(opts);
    const [l,t] = (opts&&opts.pos) || POS[id] || [30,30];
    w.style.left = l+'%'; w.style.top = t+'%';
    w.style.setProperty('--fl', (6+Math.random()*4).toFixed(1)+'s');
    w.style.setProperty('--fd', (-Math.random()*5).toFixed(1)+'s');
    ws().appendChild(w); live[id]=w;
    // targeting scan-lock flourish converges on the card, then it materialises
    requestAnimationFrame(()=>{
      const r=w.getBoundingClientRect();
      V.emit('widget:lock', { rect:{ left:r.left, top:r.top, width:r.width, height:r.height } });
      setTimeout(()=>w.classList.add('show'), 130);
    });
    return w;
  }
  function closeWidget(id){ const w=live[id]; if(!w) return; w.classList.remove('show');
    setTimeout(()=>{ w.remove(); delete live[id]; }, 200); }
  function flash(w){ w.classList.add('grabbed'); setTimeout(()=>w.classList.remove('grabbed'),300); }

  // ---- drag (mouse + programmatic for hand cursor) -----------------------
  let drag=null;
  function enableDrag(w, handle){
    handle.addEventListener('pointerdown', e=>{
      if(e.target.closest('.w-x')) return;
      const r=w.getBoundingClientRect(), pr=ws().getBoundingClientRect();
      drag={ w, dx:e.clientX-r.left, dy:e.clientY-r.top, pr };
      w.classList.add('grabbed'); bringFront(w); handle.setPointerCapture(e.pointerId);
    });
    handle.addEventListener('pointermove', e=>{ if(!drag||drag.w!==w) return; moveDragTo(e.clientX,e.clientY); });
    handle.addEventListener('pointerup', ()=>{ if(drag&&drag.w===w){ w.classList.remove('grabbed'); drag=null; } });
  }
  function moveDragTo(cx,cy){ if(!drag) return; const {w,dx,dy,pr}=drag;
    let x=cx-pr.left-dx, y=cy-pr.top-dy;
    x=Math.max(0,Math.min(pr.width-w.offsetWidth,x)); y=Math.max(0,Math.min(pr.height-w.offsetHeight,y));
    w.style.left=x+'px'; w.style.top=y+'px'; }
  let z=20; function bringFront(w){ w.style.zIndex=(++z); }

  // hand-cursor hooks: grab the widget under (clientX,clientY), move, release
  function grabAt(cx,cy){ const t=document.elementFromPoint(cx,cy); const w=t&&t.closest('.widget');
    if(!w) return false; const r=w.getBoundingClientRect(), pr=ws().getBoundingClientRect();
    drag={ w, dx:cx-r.left, dy:cy-r.top, pr }; w.classList.add('grabbed'); bringFront(w); return true; }
  function dragMove(cx,cy){ moveDragTo(cx,cy); }
  function release(){ if(drag){ drag.w.classList.remove('grabbed'); drag=null; } }

  // ---- chat + caption bindings (with streaming) --------------------------
  function typeInto(node, text, done){
    node.textContent=''; let i=0; const sp=node;
    clearInterval(node._tw);
    node._tw = setInterval(()=>{ sp.textContent = text.slice(0,++i);
      const log=sp.closest && sp.closest('.log'); if(log) log.scrollTop=log.scrollHeight;
      if(i>=text.length){ clearInterval(node._tw); done&&done(); } }, 22);
  }
  function renderChat(log){ log.innerHTML=''; chatMsgs.forEach(m=>appendMsg(log,m,true)); log.scrollTop=log.scrollHeight; }
  function appendMsg(log,m,instant){ const pfx = m.role==='user'?'$':'›';
    const row=el('div','msg '+m.role, `<span class="pfx">${pfx}</span><span class="tx"></span>`);
    log.appendChild(row); const tx=row.querySelector('.tx');
    if(m.role==='vector' && !instant) typeInto(tx, m.text); else tx.textContent=m.text;
    log.scrollTop=log.scrollHeight; }
  V.chat = { push(m){ chatMsgs.push(m); const w=live.chat; if(w){ appendMsg(w._log,m); w._log.scrollTop=w._log.scrollHeight; } } };
  V.music = { set(track){ if(live.music){ closeWidget('music'); openWidget('music',{track}); } else openWidget('music',{track}); } };
  const cap = document.getElementById('caption');
  V.caption = function(text){ if(!text){ cap.classList.remove('show'); clearInterval(cap._tw); return; }
    cap.classList.add('show'); typeInto(cap, text); };

  // ---- webcam HERO (full-bleed cam + orb docked corner) ------------------
  const heroVideo = document.getElementById('herocam');
  let visionOn=false, visionStream=null;
  function visionStatus(msg){
    let el=document.getElementById('hero-status');
    if(!el){ el=el=document.createElement('div'); el.id='hero-status';
      (document.getElementById('hero-hud')||document.getElementById('stage')).appendChild(el); }
    el.textContent=msg||''; el.style.display=msg?'block':'none';
  }
  async function visionOpen(){
    if(visionOn) return; visionOn=true;
    const s=document.getElementById('stage');
    if(s.classList.contains('locked')||s.classList.contains('boot')) V.wake();
    s.classList.add('vision','docked');
    V.emit('vision', { open:true });
    if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
      visionStatus('⚠ CAMERA API UNAVAILABLE · serve over http(s)://, not file://'); return; }
    visionStatus('◌ REQUESTING CAMERA ACCESS…');
    try{
      visionStream = await navigator.mediaDevices.getUserMedia({
        video:{ width:{ideal:1280}, height:{ideal:720}, facingMode:'user' }, audio:false });
      heroVideo.srcObject = visionStream;
      heroVideo.onloadedmetadata = ()=>{ heroVideo.play().catch(()=>{}); };
      await heroVideo.play().catch(()=>{});      // explicit play (autoplay can be blocked)
      visionStatus('');                          // live — hide the status
      if(global.VectorAudio) global.VectorAudio.blip(900,.08,'sine',.06);
    }catch(e){
      console.warn('[vision] camera error', e.name, e.message);
      const map={ NotAllowedError:'CAMERA BLOCKED · allow access in the address-bar icon, then retry',
        NotFoundError:'NO CAMERA FOUND', NotReadableError:'CAMERA IN USE BY ANOTHER APP',
        SecurityError:'CAMERA BLOCKED · needs https or localhost' };
      visionStatus('⚠ '+(map[e.name]||('CAMERA ERROR · '+e.name)));
      if(global.VectorAudio) global.VectorAudio.blip(300,.16,'sawtooth',.1);
    }
  }
  function visionClose(){ if(!visionOn) return; visionOn=false;
    const s=document.getElementById('stage'); s.classList.remove('vision');
    V.emit('vision', { open:false }); visionStatus('');
    if(!V.isWorkspaceOpen) s.classList.remove('docked');
    if(visionStream){ visionStream.getTracks().forEach(t=>t.stop()); visionStream=null; }
    heroVideo.srcObject=null; }
  V.vision = { open:visionOpen, close:visionClose, toggle(){ visionOn?visionClose():visionOpen(); }, get on(){ return visionOn; } };

  // ---- engage / disengage the command-driven workspace -------------------
  V.on('workspace', ({open})=>{
    if(!open){ Object.keys(live).forEach(id=>closeWidget(id)); }
  });
  V.on('widget:open', ({id,opts})=>openWidget(id,opts));
  V.on('widget:close', ({id})=>closeWidget(id));

  // ---- helpers ------------------------------------------------------------
  function fmt(s){ s=Math.floor(s); return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
  function escapeHtml(s){ return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  const PANEL_MATCHERS = [
    ['features', /\b(features?|backend features?|feature map|feature launcher|backend map)\b/],
    ['corepanel', /\b(core systems?|core panel|core folder|core modules?|vector core)\b/],
    ['agentspanel', /\b(agent system|agents panel|a2a|agent protocol|agent roster)\b/],
    ['brainpanel', /\b(brain panel|reasoning|hypotheses?|epistemic|person model)\b/],
    ['knowledgepanel', /\b(knowledge graph|knowledge panel|wiki merge|domain scan)\b/],
    ['codeintel', /\b(code intel|code intelligence|symbol graph|impact analysis|dependency graph)\b/],
    ['vectorcodepanel', /\b(vectorcode|vector code)\b/],
    ['trading', /\b(trading|investment|investments|dcf|alpha|portfolio intelligence)\b/],
    ['backtest', /\b(backtest|backtesting|back test)\b/],
    ['hedgebot', /\b(hedgebot|hedge bot|hedge intelligence)\b/],
    ['intelligencepanel', /\b(intelligence|flights?|vessels?|satellites?|conflicts?|outages?|cctv)\b/],
    ['shadowbroker', /\b(shadowbroker|shadow broker|sb panel|intel map)\b/],
    ['mediastudio', /\b(media studio|studio server|generative studio|image generation|video generation)\b/],
    ['comfyui', /\b(comfyui|comfy ui|stable diffusion)\b/],
    ['hyperframes', /\b(hyperframes?|video render|composer render)\b/],
    ['contentpanel', /\b(content ops|ads|seo|news ops|growth)\b/],
    ['designpanel', /\b(design panel|component spec|image prompt|ux research|design tokens)\b/],
    ['researchpanel', /\b(research panel|papers?|reddit research|research status)\b/],
    ['pccontrol', /\b(pc control|computer control|screenshot|type|click|launch app)\b/],
    ['camerapanel', /\b(camera status|camera controls|visual sensing)\b/],
    ['healthpanel', /\b(health panel|fatigue|biometrics|sleep|exercise)\b/],
    ['learningpanel', /\b(learning|course|quiz|languages?|skills map)\b/],
    ['workpanel', /\b(workflow|projects?|tasks?|ops|scheduler jobs?|queues?)\b/],
    ['privacypanel', /\b(privacy|keys?|oauth|redact|gdpr)\b/],
    ['analyticspanel', /\b(analytics|etl|pipeline health|benchmark)\b/],
    ['personalpanel', /\b(personal os|relationships?|calls?|reflection|patterns?|interview|startup|simulation)\b/],
    ['platformpanel', /\b(platform|collections?|governance|migration|mining|scraper|sandbox|mcp)\b/],
    ['city3d', /\b(city3d|city 3d|city view|district city|3d city)\b/],
    ['approvals', /\b(approval|approvals|pending approvals|permission queue)\b/],
    ['finance', /\b(finance|portfolio|investment panel|market status)\b/],
    ['contentscheduler', /\b(content scheduler|scheduler panel|schedule content|content queue)\b/],
    ['answerengine', /\b(answer engine|search panel|research search|web search)\b/],
    ['goalplanner', /\b(goal planner|planner|horizons)\b/],
    ['voicestudio', /\b(voice studio|voice clone|tts studio)\b/],
    ['codegraph', /\b(code graph|knowledge graph|graph panel)\b/],
    ['districts', /\b(district|districts|agent|agents)\b/],
    ['security', /\b(security|permission gate|threat)\b/],
    ['council', /\b(council|llm council)\b/],
    ['memory', /\b(memory|episodic|events?)\b/],
    ['telemetry', /\b(telemetry|system|cpu|ram|vram)\b/],
    ['market', /\b(market|stock|nifty|ticker)\b/],
    ['goals', /\b(goals?|objectives?)\b/],
    ['chat', /\b(chat|conversation)\b/],
    ['music', /\b(music|spotify|play)\b/],
    ['map', /\b(map|tactical map)\b/],
    ['webcam', /\b(webcam|camera panel)\b/],
  ];

  function requestedOpen(t){
    return /\b(open|show|bring up|pull up|launch|summon|display)\b/.test(t);
  }

  function localReply(t){ t=t.toLowerCase();
    if(/\b(situation|war ?room|everything|full picture|brief me)\b/.test(t)){ V.situationRoom(); return 'Workspace ready. Tell me which panel to open.'; }
    if(/\b(camera|vision|see me|eyes|look at me)\b/.test(t) && requestedOpen(t)){ V.vision.open(); return 'Vision online.'; }
    if(/\b(close|hide|stop).*(camera|vision)\b/.test(t)){ V.vision.close(); return 'Vision offline.'; }
    if(requestedOpen(t)){
      const match = PANEL_MATCHERS.find(([, rx])=>rx.test(t));
      if(match){
        if(match[0] === 'map') V.showMap();
        else V.openWidget(match[0]);
        return 'Opening '+match[0].replace(/([a-z])([A-Z])/g, '$1 $2')+'.';
      }
    }
    if(t.includes('workspace')||t.includes('hud')||t.includes('engage')) { V.openWorkspace(); return 'Workspace engaged.'; }
    if(t.includes('news')) return 'Three stories trending. A new open-weight model matches frontier reasoning at a fraction of the cost.';
    if(t.includes('time')||t.includes('clock')) return 'It is '+new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})+', sir.';
    if(/\b(hello|hi|hey|you there|online|awake)\b/.test(t)) return 'Online and listening, sir.';
    if(/\b(thank|thanks|cheers)\b/.test(t)) return 'Always, sir.';
    if(/\b(lock|sleep|standby|goodnight|good night)\b/.test(t)){ setTimeout(()=>V.lock(),1200); return 'Going to standby. Wake me anytime.'; }
    return 'Understood. Standing by.'; }

  // ---- situation room: the multi-feed "war room" arrangement ------------
  function situationRoom(){
    V.openWorkspace();
  }
  V.situationRoom = situationRoom;

  // ---- unified command handler (chat input, terminal, and voice all use it)
  function sayLocalFallback(text, reason, delay){
    if(typeof V.setRuntimeMode === 'function') V.setRuntimeMode('degraded', reason || 'backend command failed');
    setTimeout(()=>V.say('LOCAL DEMO FALLBACK · '+localReply(text)), delay == null ? 500 : delay);
  }

  V.ask = function(text){
    if(!text) return; text = String(text).trim(); if(!text) return;
    V.chat.push({ role:'user', text });
    V.emit('chat:submit', { text });
    V.process();
    if(V.config && V.config.base){
      // live backend: let /command drive the response
      V.command(text).then(r=>{ V.say((r && (r.response||r.text)) || 'Done, sir.'); })
        .catch(()=>{ sayLocalFallback(text, 'voice/chat /command failed', 500); });
    } else {
      sayLocalFallback(text, 'voice/chat using demo mode', 650);
    }
  };

  function animateTelemetry(w){
    let tick=0, t0=Date.now();
    const set=(sel,v)=>{ const e=w.querySelector(sel); if(e) e.textContent=v; };
    const bar=(sel,v)=>{ const e=w.querySelector(sel); if(e) e.style.width=v+'%'; };
    const id=setInterval(()=>{
      if(!w.isConnected){ clearInterval(id); return; }
      const cpu=22+Math.random()*30, vram=58+Math.random()*22, temp=54+Math.random()*16;
      set('[data-cpu]', cpu.toFixed(0)+'%'); bar('[data-cpu-bar]', cpu);
      set('[data-vram]', vram.toFixed(0)+'% · 16GB'); bar('[data-vram-bar]', vram);
      set('[data-temp]', temp.toFixed(0)+'°C'); bar('[data-temp-bar]', (temp-40)/40*100);
      set('[data-tick]', (tick+=Math.floor(Math.random()*3)+1));
      const up=Math.floor((Date.now()-t0)/1000)+3600;
      set('[data-up]', [up/3600,up/60%60,up%60].map(n=>String(Math.floor(n)).padStart(2,'0')).join(':'));
    },1000);
  }

  async function requestCam(feed){
    try{
      const stream = await navigator.mediaDevices.getUserMedia({ video:{ width:640,height:480 }, audio:false });
      const v=document.createElement('video'); v.autoplay=true; v.playsInline=true; v.muted=true; v.srcObject=stream;
      feed.innerHTML=''; feed.appendChild(v);
      const source=el('div','ve-source cam-source','SIMULATED · detector overlay only');
      source.dataset.mode='simulated';
      feed.appendChild(source);
      const det=el('div','det'); det.style.cssText='left:30%;top:24%;width:40%;height:54%';
      det.appendChild(el('span',null,'SIMULATED DETECTION · person')); feed.appendChild(det);
    }catch(e){
      feed.innerHTML = '<div class="off">CAMERA UNAVAILABLE · no local preview</div>';
      if(typeof V.setRuntimeMode === 'function') V.setRuntimeMode('degraded', 'camera preview unavailable');
    }
  }

  global.VectorWidgets = { openWidget, closeWidget, grabAt, dragMove, release };
})(window);
