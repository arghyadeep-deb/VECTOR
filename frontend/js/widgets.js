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

    async function submitToBackend(text){
      try{
        const r = await fetch(API+'/commands', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ text })
        });
        const j = await r.json();
        V.say((j && (j.response || j.text || j.result)) || 'Done, sir.');
      }catch(e){ V.say(localReply(text)); }
    }

    function submit(){ const t=input.value.trim(); if(!t) return; input.value='';
      chatMsgs.push({ role:'user', text:t });
      appendMsg(log, { role:'user', text:t });
      if(API){ submitToBackend(t); } else { setTimeout(()=>V.say(localReply(t)), 650); }
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
         <div class="meta"><div class="t">${t.title}</div><div class="a">${t.artist}</div>
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
      pin.innerHTML=`<div class="pulse"></div><div class="d"></div><div class="nm">${p.name}</div>`; mapEl.appendChild(pin); });
  }

  F.telemetry = function(){
    const wrap = el('div');
    wrap.innerHTML = `
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

    function fmtUptime(s){ s=Math.floor(s||0);
      return [s/3600, s/60%60, s%60].map(n=>String(Math.floor(n)).padStart(2,'0')).join(':'); }

    async function loadTelemetry(){
      try{
        const r = await fetch(API+'/health/system');
        const j = await r.json();
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
      }catch(e){ /* backend offline — animate demo */ }
    }

    const w = shell('telemetry','SYSTEM TELEMETRY', wrap, 'panel');
    loadTelemetry();
    animateTelemetry(w);   // demo animation keeps running; real data overlays it when backend is up
    setInterval(()=>{ if(w.isConnected) loadTelemetry(); }, 3000);
    return w;
  };

  F.market = function(){
    const wrap = el('div');
    const pts=[]; let y=60; for(let i=0;i<48;i++){ y+=(Math.random()-0.48)*10; y=Math.max(14,Math.min(96,y)); pts.push(y); }
    const path = pts.map((p,i)=>`${(i/(pts.length-1)*340).toFixed(1)},${p.toFixed(1)}`).join(' ');
    wrap.innerHTML = `
      <svg viewBox="0 0 340 120" preserveAspectRatio="none">
        <defs><linearGradient id="mg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="rgba(0,207,255,.35)"/><stop offset="1" stop-color="rgba(0,207,255,0)"/>
        </linearGradient></defs>
        <polygon points="0,120 ${path} 340,120" fill="url(#mg)"/>
        <polyline points="${path}" fill="none" stroke="var(--accent)" stroke-width="1.3"/>
      </svg>
      <div class="stat"><div><b>NIFTY 50</b> <span>24,318.40</span></div>
        <div style="color:var(--ok)"><b>▲ 0.62%</b> <span>+150.2</span></div></div>`;
    return shell('market','MARKET · NSE', wrap, 'market');
  };

  F.goals = function(){
    const wrap = el('div');
    ['LONG','MID','SHORT'].forEach(h=>{
      wrap.appendChild(el('div','dlbl', h+' HORIZON').cloneNode());
      const lbl = el('div', null, `<div style="font-size:8px;letter-spacing:.16em;color:var(--txt-faint);margin:6px 0 3px">${h} HORIZON</div>`);
      wrap.appendChild(lbl);
      D.GOALS[h].forEach(g=>{
        const row = el('div', null,
          `<div class="row-kv"><span class="v">${g.title}</span><span class="k">${Math.round(g.progress*100)}%</span></div>
           <div class="meter ${g.progress<0.4?'dn':g.progress<0.7?'warn':''}"><i style="width:${g.progress*100}%"></i></div>`);
        wrap.appendChild(row);
      });
    });
    return shell('goals','GOALS', wrap, 'panel');
  };

  F.districts = function(){
    const wrap = el('div');
    const grid = el('div','grid');
    D.agents.slice(0,18).forEach(a=>{
      const pct = a.health_points/1000*100;
      const cls = a.health_points<=0?'ghost':'';
      const bar = a.health_points<=0?'low':a.health_points<400?'low':a.health_points<700?'mid':'';
      grid.appendChild(el('div','agent '+cls,
        `<div class="an">${a.name}</div><div class="ad">${a.district.toUpperCase()}</div>
         <div class="hpbar ${bar}"><i style="width:${pct}%"></i></div>
         <div class="hp"><span>HP ${a.health_points}</span><span>G${a.generation} · ${a.tier}</span></div>`));
    });
    wrap.appendChild(grid);
    return shell('districts','AGENT DISTRICTS · 33', wrap, 'agents');
  };

  F.council = function(){
    const wrap = el('div');
    D.COUNCIL.forEach(c=>{
      wrap.appendChild(el('div','csess',
        `<div class="q">${c.question}</div>
         <div class="meta"><span class="badge2 ${c.recommendation}">${c.recommendation.toUpperCase()}</span>
           <span class="badge2 ${c.stakes==='critical'?'crit':c.stakes}">${c.stakes.toUpperCase()}</span>
           <span class="k" style="margin-left:auto">${Math.round(c.confidence*100)}% · ${c.when}</span></div>`));
    });
    return shell('council','LLM COUNCIL', wrap, 'council');
  };

  F.security = function(){
    const wrap = el('div');
    wrap.appendChild(el('div', null,
      `<div class="row-kv"><span class="k">THREAT LEVEL</span><span class="v" style="color:var(--ok)">LOW</span></div>
       <div style="font-size:8px;letter-spacing:.16em;color:var(--txt-faint);margin:8px 0 4px">PENDING APPROVALS · ${D.APPROVALS.length}</div>`));
    D.APPROVALS.forEach(a=>{
      const w = el('div','appr '+(a.level==='RED'?'red':''),
        `<div class="at">${a.action_type} <span class="badge2 ${a.level==='RED'?'crit':'high'}">${a.level}</span></div>
         <div class="ap">${a.params} · by ${a.proposed_by}</div>
         <div class="acts"><button class="ok2">APPROVE</button><button class="no2">DENY</button>
           <span class="exp">${a.expires}s</span></div>`);
      w.querySelector('.ok2').addEventListener('click',e=>{ e.stopPropagation(); w.style.opacity=.3;
        V.say('Approved. '+a.action_type+' executing, sir.'); });
      w.querySelector('.no2').addEventListener('click',e=>{ e.stopPropagation(); w.style.opacity=.3;
        V.say('Denied. '+a.action_type+' blocked.'); });
      wrap.appendChild(w);
    });
    return shell('security','PERMISSION GATE', wrap, 'security');
  };

  F.memory = function(){
    const wrap = el('div');
    D.MEMORY.forEach(m=>{
      wrap.appendChild(el('div','mevt imp-'+m.importance,
        `<span class="ew">${m.when}</span><div class="et">${m.event_type}</div><div class="ec">${m.content}</div>`));
    });
    return shell('memory','EPISODIC MEMORY', wrap, 'memory');
  };

  F.webcam = function(){
    const wrap = el('div');
    const feed = el('div','feed', `<div class="off">CAMERA · YOLO STANDBY</div>`);
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
        const r = await fetch(API + '/voice/profiles');
        const j = await r.json();
        const profs = (j.profiles||[]).map(p=>p.name);
        if(profs.length){ sel.innerHTML = profs.map(n=>`<option value="${n}">${n}</option>`).join(''); }
      }catch(e){ /* keep default */ }
    }
    refresh.addEventListener('click', e=>{ e.stopPropagation(); loadProfiles(); });

    gen.addEventListener('click', async e=>{
      e.stopPropagation();
      const text = ta.value.trim();
      if(!text){ stat.textContent='enter a script first'; return; }
      stat.textContent='◌ synthesizing…'; gen.disabled=true;
      try{
        const r = await fetch(API + '/voice/studio/generate', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ text, profile: sel.value })
        });
        const j = await r.json();
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
        const r = await fetch(API+'/knowledge/graph', { method:'POST',
          headers:{'Content-Type':'application/json'}, body: JSON.stringify({project_path:p, max_nodes:200}) });
        const j = await r.json();
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
            if (V.http) await V.http('/gateway/approve/'+encodeURIComponent(id), {method:'POST'});
            else await fetch(API+'/gateway/approve/'+encodeURIComponent(id), {method:'POST'});
            V.say('Approved — '+id+' executing.');
          }catch(err){ card.style.opacity='1'; }
          refresh();
        });
        card.querySelector('.apv-no').addEventListener('click', async e=>{
          e.stopPropagation(); card.style.opacity='.4';
          try{
            if (V.http) await V.http('/gateway/reject/'+encodeURIComponent(id), {method:'POST'});
            else await fetch(API+'/gateway/reject/'+encodeURIComponent(id), {method:'POST'});
            V.say('Rejected — '+id+' blocked.');
          }catch(err){ card.style.opacity='1'; }
          refresh();
        });
        list.appendChild(card);
      });
    }

    async function refresh(){
      try{
        const j = V.http
          ? await V.http('/gateway/pending')
          : await fetch(API+'/gateway/pending').then(r => r.json());
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
        const r = await fetch(API+'/investment/portfolio');
        const j = await r.json();
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
        const r = await fetch(API+'/investment/market-status');
        const j = await r.json();
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
        const r = await fetch(API+'/content/scheduled');
        const j = await r.json();
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
      try{ await fetch(API+'/content/run', {method:'POST'}); loadQueue(); }catch(err){}
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
        const r = await fetch(API+'/content/schedule', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({title, content, platforms})
        });
        const j = await r.json();
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
        const r = await fetch(API+'/research/search?q='+encodeURIComponent(q));
        const j = await r.json();
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
        const r = await fetch(API+'/goals');
        const j = await r.json();
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

  // ---- engage / disengage the curated workspace --------------------------
  const DEFAULT_SET = ['telemetry','market','districts','goals','memory','council'];
  V.on('workspace', ({open})=>{
    if(open){ DEFAULT_SET.forEach((id,i)=>setTimeout(()=>openWidget(id), i*80)); }
    else { Object.keys(live).forEach(id=>closeWidget(id)); }
  });
  V.on('widget:open', ({id,opts})=>openWidget(id,opts));
  V.on('widget:close', ({id})=>closeWidget(id));

  // ---- helpers ------------------------------------------------------------
  function fmt(s){ s=Math.floor(s); return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
  function escapeHtml(s){ return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
  function localReply(t){ t=t.toLowerCase();
    if(/\b(situation|war ?room|everything|full picture|brief me)\b/.test(t)){ V.situationRoom(); return 'Engaging the situation room, sir. Vision, markets and comms are live.'; }
    if(/\b(camera|vision|see me|eyes|look at me)\b/.test(t)){ V.vision.open(); return 'Vision online. I have eyes on you, sir.'; }
    if(/\b(close|hide|stop).*(camera|vision)\b/.test(t)){ V.vision.close(); return 'Vision offline.'; }
    if(t.includes('map')) { V.showMap(); return 'Pulling up the tactical map now, sir.'; }
    if(t.includes('music')||t.includes('play')||t.includes('spotify')){ V.openWidget('music'); return 'Opening the music widget.'; }
    if(t.includes('goal')) { V.openWidget('goals'); return 'Here are your goals. You are tracking six.'; }
    if(t.includes('security')||t.includes('approv')||t.includes('threat')) { V.openWidget('security'); return 'Threat level is low. Two approvals await your review, sir.'; }
    if(t.includes('district')||t.includes('agent')) { V.openWidget('districts'); return 'Thirty-three districts online. Most agents are healthy.'; }
    if(t.includes('council')) { V.openWidget('council'); return 'The council has three recent sessions logged.'; }
    if(t.includes('memory')||t.includes('event')) { V.openWidget('memory'); return 'Recent episodic memory is on screen.'; }
    if(t.includes('telemetry')||t.includes('system')||t.includes('cpu')) { V.openWidget('telemetry'); return 'System telemetry up. The host is running cool.'; }
    if(t.includes('market')||t.includes('stock')||t.includes('nifty')) { V.openWidget('market'); return 'Markets are up zero point six percent today.'; }
    if(t.includes('workspace')||t.includes('hud')||t.includes('engage')) { V.openWorkspace(); return 'Workspace engaged.'; }
    if(t.includes('news')) return 'Three stories trending. A new open-weight model matches frontier reasoning at a fraction of the cost.';
    if(t.includes('time')||t.includes('clock')) return 'It is '+new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'})+', sir.';
    if(/\b(hello|hi|hey|you there|online|awake)\b/.test(t)) return 'Online and listening, sir.';
    if(/\b(thank|thanks|cheers)\b/.test(t)) return 'Always, sir.';
    if(/\b(lock|sleep|standby|goodnight|good night)\b/.test(t)){ setTimeout(()=>V.lock(),1200); return 'Going to standby. Wake me anytime.'; }
    return 'Understood. Standing by.'; }

  // ---- situation room: the multi-feed "war room" arrangement ------------
  function situationRoom(){
    V.vision.open();                         // your face, full-bleed
    // float a few panels around the feed (upper area, sides) like the reels
    setTimeout(()=>{ openWidget('market',  { pos:[58,8]  }); }, 220);
    setTimeout(()=>{ openWidget('webcam',  { pos:[3,8]   }); }, 380);
    setTimeout(()=>{ openWidget('chat',    { pos:[3,52]  }); }, 540);
    setTimeout(()=>{ openWidget('security',{ pos:[60,46] }); }, 700);
  }
  V.situationRoom = situationRoom;

  // ---- unified command handler (chat input, terminal, and voice all use it)
  V.ask = function(text){
    if(!text) return; text = String(text).trim(); if(!text) return;
    V.chat.push({ role:'user', text });
    V.emit('chat:submit', { text });
    V.process();
    if(V.config && V.config.base){
      // live backend: let /command drive the response
      V.command(text).then(r=>{ V.say((r && (r.response||r.text)) || 'Done, sir.'); })
        .catch(()=>{ setTimeout(()=>V.say(localReply(text)), 500); });
    } else {
      setTimeout(()=>V.say(localReply(text)), 650);
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
      // mock YOLO box
      const det=el('div','det'); det.style.cssText='left:30%;top:24%;width:40%;height:54%';
      det.appendChild(el('span',null,'person · 0.97')); feed.appendChild(det);
    }catch(e){ /* keep CAMERA OFFLINE placeholder */ }
  }

  global.VectorWidgets = { openWidget, closeWidget, grabAt, dragMove, release };
})(window);
