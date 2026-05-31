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
    music:[40,70], chat:[2,30], webcam:[60,40]
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
    function submit(){ const t=input.value.trim(); if(!t) return; input.value='';
      V.ask(t); }
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
      <div class="row-kv" style="margin-top:8px"><span class="k">ACTIVE MODEL</span><span class="v">claude-sonnet-4.6</span></div>
      <div class="row-kv"><span class="k">LOOP TICK</span><span class="v" data-tick>0</span></div>
      <div class="row-kv"><span class="k">UPTIME</span><span class="v" data-up>00:00:00</span></div>`;
    const w = shell('telemetry','SYSTEM TELEMETRY', wrap, 'panel');
    animateTelemetry(w);
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
