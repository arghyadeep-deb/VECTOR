/* ============================================================================
   VECTOR · demo.js  — subsystem dock, Director (dev) panel, hotkeys,
   scripted auto-demo, and the backend-connect form.
   The HUD needs this file: it builds the subsystem dock and the hotkeys.
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  const runtimeState = {
    mode: 'demo',
    label: 'DEMO DATA',
    detail: 'No backend verified.',
    base: '',
    lastOk: '',
    lastError: ''
  };
  const ico = {
    mic:'<path d="M8 1a2 2 0 0 1 2 2v4a2 2 0 1 1-4 0V3a2 2 0 0 1 2-2z"/><path d="M3 7a5 5 0 0 0 10 0M8 12v3"/>',
    screen:'<rect x="1.5" y="2" width="13" height="9"/><path d="M6 14h4M8 11v3"/>',
    cam:'<rect x="1.5" y="3.5" width="9" height="8"/><path d="M11 6l3.5-2v7L11 9"/>',
    grid:'<rect x="1.5" y="1.5" width="13" height="13"/><path d="M1.5 6h13M1.5 10.5h13M6 1.5v13M10.5 1.5v13"/>',
    music:'<path d="M5 12V3l8-1.5V11"/><circle cx="3.4" cy="12" r="1.8"/><circle cx="11.4" cy="11" r="1.8"/>',
    hand:'<path d="M5 8V4.5a1 1 0 0 1 2 0V7m0-1V3.2a1 1 0 0 1 2 0V7m0-1.2a1 1 0 0 1 2 0V8c0 3-1.5 5.5-4 5.5S5 11.5 5 9.5V8"/>',
    sound:'<path d="M3 6h2l3-2.5v9L5 10H3z"/><path d="M10 5.5a3 3 0 0 1 0 5M11.6 3.6a5.5 5.5 0 0 1 0 8.8"/>',
    vstudio:'<path d="M8 1a2 2 0 0 1 2 2v4a2 2 0 1 1-4 0V3a2 2 0 0 1 2-2z"/><path d="M3 7a5 5 0 0 0 10 0M8 12v3"/><circle cx="13" cy="3" r="1.5"/>',
    codegraph:'<circle cx="3" cy="4" r="1.8"/><circle cx="12" cy="3" r="1.8"/><circle cx="8" cy="9" r="1.8"/><circle cx="13" cy="12" r="1.8"/><path d="M4.5 4.5 7 8M10.5 4 8.5 8M9.5 9.5 11.5 11"/>',
    approvals:'<path d="M3 8h10M8 3v10"/><circle cx="8" cy="8" r="6.5" stroke-dasharray="3 2"/><path d="M5.5 8.5l2 2 3.5-4"/>',
    librechat:'<rect x="2" y="3" width="12" height="9" rx="1"/><path d="M5 14h6M8 12v2"/><path d="M5 7h6M5 9.5h4"/>',
    openwebui:'<circle cx="8" cy="8" r="6.5"/><path d="M8 1.5v13M1.5 8h13M3 4a8 8 0 0 1 10 0M3 12a8 8 0 0 0 10 0"/>',
    finance:'<path d="M2 12l4-4 3 3 5-6"/><circle cx="13" cy="4" r="1.5"/><path d="M1.5 14.5h13"/>',
    cscheduler:'<rect x="2" y="3" width="12" height="11" rx="1"/><path d="M5 1.5v3M11 1.5v3M2 7h12"/><circle cx="11" cy="11" r="2.5"/><path d="M11 9.5v1.5l1 1"/>',
    answerengine:'<circle cx="8" cy="7" r="5.5"/><path d="M8 4.5v2.5l1.5 1.5M8 14v-1.5"/>',
    goalplanner:'<circle cx="8" cy="3" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="8" cy="13" r="1.5"/><path d="M9.5 3h4M9.5 8h4M9.5 13h4"/>',
    missioncontrol:'<path d="M2 3h12v10H2z"/><path d="M4 6h4M4 8.5h6M4 11h3"/><circle cx="12" cy="6" r="1.3"/><path d="M11 10l1 1 2-2"/>'
    ,features:'<rect x="2" y="2" width="5" height="5"/><rect x="9" y="2" width="5" height="5"/><rect x="2" y="9" width="5" height="5"/><rect x="9" y="9" width="5" height="5"/><path d="M7 4.5h2M7 11.5h2M4.5 7v2M11.5 7v2"/>'
  };
  const svg = p => `<svg viewBox="0 0 16 16">${p}</svg>`;

  // ---- subsystem dock (bottom centre, like reference) --------------------
  function buildDock(){
    const dock=document.getElementById('dock');
    const items=[
      ['mic','VOICE · say “Hey VECTOR”', toggleVoice, false],
      ['sep'],
      ['screen','WORKSPACE', ()=>V.toggleWorkspace(), false],
      ['sep'],
      ['cam','VISION', ()=>{ V.vision.toggle(); setOn('cam', V.vision.on); }, false],
      ['sep'],
      ['grid','SITUATION ROOM', ()=>V.situationRoom(), false],
      ['sep'],
      ['features','BACKEND FEATURES', ()=>V.openWidget('features'), false],
      ['sep'],
      ['missioncontrol','MISSION CONTROL', ()=>V.openWidget('missioncontrol'), false],
      ['sep'],
      ['music','MUSIC', ()=>V.openWidget('music'), false],
      ['sep'],
      ['vstudio','VOICE STUDIO · script → my voice', ()=>V.openWidget('voicestudio'), false],
      ['sep'],
      ['codegraph','CODE GRAPH · explore the codebase', ()=>V.openWidget('codegraph'), false],
      ['sep'],
      ['answerengine','ANSWER ENGINE · search anything', ()=>V.openWidget('answerengine'), false],
      ['sep'],
      ['goalplanner','GOAL PLANNER · LONG/MID/SHORT horizons', ()=>V.openWidget('goalplanner'), false],
      ['sep'],
      ['hand','POINTER', toggleCursor, false],
      ['sep'],
      ['sound','SOUND', toggleSound, true]
    ];
    items.forEach(it=>{
      if(it[0]==='sep'){ dock.appendChild(Object.assign(document.createElement('div'),{className:'sep'})); return; }
      const b=document.createElement('button'); b.className='d-btn'+(it[3]?' on':''); b.title=it[1];
      b.setAttribute('aria-label', it[1]);
      b.innerHTML=svg(ico[it[0]]); b.dataset.key=it[0];
      b.addEventListener('click',e=>{ e.stopPropagation(); it[2](); });
      dock.appendChild(b);
    });
    // reflect state on the dock
    V.on('state',({to})=>{ setOn('mic', (to==='listening') || (global.VectorSpeech && global.VectorSpeech.active)); });
    V.on('workspace',({open})=>setOn('screen',open));
    V.on('vision',({open})=>setOn('cam',open));
  }
  function toggleVoice(){
    if(global.VectorSpeech){ const on=global.VectorSpeech.toggle(); setOn('mic',on); }
    else { V.state==='listening'?V.idle():V.listen(); }
  }
  function toggleSound(){
    if(!global.VectorAudio) return;
    const on=!global.VectorAudio.enabled; global.VectorAudio.setEnabled(on); setOn('sound',on);
  }
  function setOn(key,on){ const b=document.querySelector(`#dock .d-btn[data-key="${key}"]`); if(b) b.classList.toggle('on',on); }

  function runtimeLabel(state){
    if(state.mode === 'live') return '● LIVE · '+(state.base || state.detail || 'backend verified');
    if(state.mode === 'connecting') return 'CONNECTING · '+(state.base || 'backend');
    if(state.mode === 'degraded') return 'DEGRADED · '+(state.detail || state.lastError || 'backend unavailable');
    return 'DEMO MODE · '+(state.detail || 'seed data only');
  }

  function runtimeColor(mode){
    if(mode === 'live') return 'var(--ok)';
    if(mode === 'connecting') return 'var(--warn)';
    if(mode === 'degraded') return 'var(--danger)';
    return 'var(--txt-faint)';
  }

  function updateRuntimeBadge(){
    const stat=document.getElementById('d-stat');
    if(stat){
      stat.textContent=runtimeLabel(runtimeState);
      stat.style.color=runtimeColor(runtimeState.mode);
      stat.dataset.mode=runtimeState.mode;
    }
    const stage=document.getElementById('stage');
    if(stage){
      stage.dataset.runtimeMode=runtimeState.mode;
      stage.dataset.runtimeDetail=runtimeState.detail || runtimeState.lastError || '';
    }
  }

  function setRuntimeMode(mode, detail){
    runtimeState.mode=mode || 'demo';
    runtimeState.detail=detail || runtimeState.detail || '';
    runtimeState.base=(V.config && V.config.base) || runtimeState.base || '';
    if(mode === 'live') runtimeState.lastOk=new Date().toISOString();
    if(mode === 'degraded') runtimeState.lastError=detail || runtimeState.lastError || 'backend unavailable';
    updateRuntimeBadge();
    V.emit('runtime:mode', Object.assign({}, runtimeState));
    return Object.assign({}, runtimeState);
  }
  V.setRuntimeMode=setRuntimeMode;

  // ---- "backend offline, retrying" screen ---------------------------------
  // The HUD keeps polling and the sockets reconnect with backoff, so a dropped backend recovers on its own -- this
  // just says so. Shown only when a backend is configured AND has been unreachable for OFFLINE_GRACE_MS (so a normal
  // restart or a single slow poll never flashes it); it hides itself the moment the mode goes live again.
  const OFFLINE_GRACE_MS = 6000;
  let offlineTimer = null;
  let offlineTicker = null;
  // Set by an HTTP 401/403 poll failure, cleared by a verified-live poll. Tracked apart from runtimeState.lastError
  // because optional websockets (camera, gesture) also report 'degraded' and overwrite that text every few seconds.
  let authRejected = false;

  function offlineScreen(){
    let el=document.getElementById('ve-offline-screen');
    if(el) return el;
    el=document.createElement('div');
    el.id='ve-offline-screen';
    el.setAttribute('role','alert');
    el.hidden=true;
    const card=document.createElement('div'); card.className='ve-offline-card';
    const h=document.createElement('div'); h.className='ve-offline-title'; h.id='ve-offline-title'; h.textContent='BACKEND OFFLINE';
    const m=document.createElement('div'); m.className='ve-offline-msg'; m.id='ve-offline-msg';
    const t=document.createElement('div'); t.className='ve-offline-since'; t.id='ve-offline-since';
    const b=document.createElement('button'); b.type='button'; b.className='ve-offline-retry'; b.textContent='RETRY NOW';
    b.addEventListener('click',async e=>{
      e.stopPropagation(); b.disabled=true;
      try{ await V.http('/status'); setRuntimeMode('live', V.config.base || 'backend verified'); }
      catch(_){ m.textContent='Still unreachable · retrying automatically'; }
      finally{ b.disabled=false; }
    });
    card.append(h,m,t,b); el.append(card);
    document.body.appendChild(el);
    return el;
  }

  function showOffline(){
    const el=offlineScreen();
    const since=runtimeState.lastOk ? new Date(runtimeState.lastOk).getTime() : null;
    const paint=()=>{
      const msg=document.getElementById('ve-offline-msg');
      // A 401/403 means the backend is up but refuses this HUD's key (e.g. it was rotated while this page stayed open,
      // or a phone bookmark still carries the old one). Say that, instead of implying the backend is down.
      const rejected=authRejected;
      const title=document.getElementById('ve-offline-title');
      if(title) title.textContent = rejected ? 'ACCESS KEY REJECTED' : 'BACKEND OFFLINE';
      if(msg) msg.textContent = rejected
        ? 'The backend is running but rejected the API key this HUD is using. Reopen the HUD from the desktop shortcut, or from a link that carries the current key.'
        : (runtimeState.lastError || 'backend unavailable')+' · retrying automatically';
      const sinceEl=document.getElementById('ve-offline-since');
      if(sinceEl){
        if(since==null) sinceEl.textContent='never reached since this page opened';
        else{ const s=Math.max(0,Math.floor((Date.now()-since)/1000));
          sinceEl.textContent='last connected '+(s<60?s+'s':s<3600?Math.floor(s/60)+'m':Math.floor(s/3600)+'h')+' ago'; }
      }
    };
    paint(); el.hidden=false;
    if(!offlineTicker) offlineTicker=setInterval(paint,1000);
  }

  function hideOffline(){
    const el=document.getElementById('ve-offline-screen');
    if(el) el.hidden=true;
    if(offlineTicker){ clearInterval(offlineTicker); offlineTicker=null; }
  }

  V.on('runtime:mode', st=>{
    const backendConfigured=!!(V.config && V.config.base);
    // A websocket that cannot connect (no camera, an unsupported gesture backend) reports 'degraded' too; that says
    // nothing about the HTTP backend, so it never starts the offline screen. Only failed HTTP polls do.
    const wsOnly=/^ws /.test(st.detail || '');
    if(st.mode==='degraded' && /→ 40[13]/.test(st.detail || '')) authRejected=true;
    if(st.mode==='live') authRejected=false;
    if(st.mode==='degraded' && backendConfigured && !wsOnly){
      const shown=document.getElementById('ve-offline-screen');
      if(!offlineTimer && !(shown && !shown.hidden)){
        offlineTimer=setTimeout(()=>{ offlineTimer=null; showOffline(); }, OFFLINE_GRACE_MS);
      }
    } else if(st.mode==='live' || st.mode==='demo'){
      // Only a verified-live backend (or a deliberate disconnect) clears the screen. 'connecting' is NOT a recovery:
      // a socket that reopens while every HTTP poll still fails flips degraded <-> connecting every few seconds, and
      // treating that as recovery kept restarting the grace timer so the screen never appeared.
      if(offlineTimer){ clearTimeout(offlineTimer); offlineTimer=null; }
      hideOffline();
    }
  });
  V.getRuntimeMode=()=>Object.assign({}, runtimeState);
  function toggleCursor(){
    const C=global.VectorCursor;
    if(C.mode==='off'){ C.mouse(); setOn('hand',true); }
    else if(C.mode==='mouse'){ C.hand(); setOn('hand',true); }
    else { C.off(); setOn('hand',false); }
  }

  // ---- Director dev panel ------------------------------------------------
  function buildDirector(){
    const d=document.getElementById('director');
    d.innerHTML=`
      <div class="dtab" title="Director (backtick key)" role="button" tabindex="0" aria-label="Toggle Director dev panel">⌘</div>
      <div class="dh" role="button" tabindex="0" aria-label="Toggle Director dev panel"><span>DIRECTOR</span><b>dev · ~ toggles</b></div>
      <div class="dbody">
        <div class="dgrp"><div class="dlbl">VOICE FSM</div><div class="dbtns" id="g-fsm"></div></div>
        <div class="dgrp"><div class="dlbl">SECRET HUD · ⌃⇧V</div><div class="dbtns" id="g-hud"></div></div>
        <div class="dgrp"><div class="dlbl">WIDGETS</div><div class="dbtns" id="g-wid"></div></div>
        <div class="dgrp"><div class="dlbl">CURSOR</div><div class="dbtns" id="g-cur"></div></div>
        <div class="dgrp"><div class="dlbl">CONNECT BACKEND</div>
          <input class="di" id="d-base" placeholder="http://127.0.0.1:8000" />
          <input class="di" id="d-key" placeholder="VECTOR_API_KEY (optional)" />
          <div class="dbtns"><button class="db prim" id="d-conn">CONNECT</button>
            <button class="db" id="d-disc">DISCONNECT</button></div>
          <div class="dlbl" id="d-stat" data-mode="demo">DEMO MODE · seed data only</div>
        </div>
      </div>`;
    const mk=(host,label,fn,prim)=>{ const b=document.createElement('button');
      b.className='db'+(prim?' prim':''); b.textContent=label;
      b.addEventListener('click',e=>{ e.stopPropagation(); fn(); });
      document.getElementById(host).appendChild(b); };

    mk('g-fsm','▶ AUTO DEMO', autoDemo, true);
    mk('g-fsm','WAKE', ()=>V.wake());
    mk('g-fsm','LISTEN', ()=>V.listen());
    mk('g-fsm','PROCESS', ()=>V.process());
    mk('g-fsm','SPEAK', ()=>V.say('All systems nominal, sir. The workspace is yours.'));
    mk('g-fsm','LOCK', ()=>V.lock());
    mk('g-fsm','FORTRESS', ()=>{ V.fortress(); });

    mk('g-hud','ENGAGE', ()=>V.openWorkspace(), true);
    mk('g-hud','DISENGAGE', ()=>V.closeWorkspace());
    mk('g-hud','⌃⇧H TERMINAL', ()=>window.VectorTerminal&&window.VectorTerminal.toggle());
    mk('g-hud','VISION', ()=>V.vision.toggle());
    mk('g-hud','SITUATION', ()=>V.situationRoom());
    mk('g-hud','VOICE', ()=>{ if(global.VectorSpeech) global.VectorSpeech.toggle(); });

    [
      'chat','music','map','webcam','telemetry','market','goals','goalplanner',
      'districts','council','security','memory','approvals','finance',
      'contentscheduler','answerengine','voicestudio','codegraph',
      'features','missioncontrol','corepanel','agentspanel','brainpanel','knowledgepanel',
      'codeintel','vectorcodepanel','trading','backtest','hedgebot',
      'intelligencepanel','shadowbroker','mediastudio','comfyui',
      'hyperframes','contentpanel','designpanel','researchpanel','pccontrol',
      'camerapanel','healthpanel','learningpanel','workpanel','privacypanel',
      'analyticspanel','personalpanel','platformpanel','city3d'
    ]
      .forEach(id=>mk('g-wid', id.toUpperCase(), ()=>V.openWidget(id)));

    mk('g-cur','POINTER', ()=>{ global.VectorCursor.mouse(); setOn('hand',true); });
    mk('g-cur','HAND CAM', ()=>{ global.VectorCursor.hand(); setOn('hand',true); });
    mk('g-cur','OFF', ()=>{ global.VectorCursor.off(); setOn('hand',false); });

    const toggleDirector = ()=>d.classList.toggle('open');
    const directorKeyHandler = e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggleDirector(); } };
    d.querySelector('.dtab').addEventListener('click',e=>{ e.stopPropagation(); toggleDirector(); });
    d.querySelector('.dtab').addEventListener('keydown',directorKeyHandler);
    d.querySelector('.dh').addEventListener('click',e=>{ e.stopPropagation(); toggleDirector(); });
    d.querySelector('.dh').addEventListener('keydown',directorKeyHandler);

    document.getElementById('d-conn').addEventListener('click', async e=>{
      e.stopPropagation();
      const base=document.getElementById('d-base').value.trim()||'http://127.0.0.1:8000';
      const apiKey=document.getElementById('d-key').value.trim();
      setRuntimeMode('connecting', base);
      try{ await V.connect({ base, apiKey }); setRuntimeMode('connecting', 'waiting for backend health check · '+base); }
      catch(err){ setRuntimeMode('degraded', 'connect failed · demo seed data only'); }
    });
    document.getElementById('d-disc').addEventListener('click',e=>{ e.stopPropagation();
      V.disconnect(); setRuntimeMode('demo', 'manual disconnect · seed data only'); });

    V.on('ws:open',({name})=>{ if(runtimeState.mode !== 'live') setRuntimeMode('connecting', 'websocket '+name+' open · waiting for HTTP health'); });
    V.on('ws:close',({name})=>{ const s=document.getElementById('d-stat'); if(s && !V.config.base){ }});
    updateRuntimeBadge();
  }

  // ---- keyboard shortcuts ------------------------------------------------
  function hotkeys(){
    addEventListener('keydown',e=>{
      if(e.target.matches('input,textarea')) return;
      if(e.key==='`'){ document.getElementById('director').classList.toggle('open'); e.preventDefault(); }
      else if(e.ctrlKey && e.shiftKey && (e.key==='V'||e.key==='v')){ V.toggleWorkspace(); e.preventDefault(); }
      else if(e.code==='Space'){ V.state==='listening'?V.idle():V.listen(); e.preventDefault(); }
      else if(e.key==='Escape'){ if(V.isWorkspaceOpen) V.closeWorkspace(); else V.lock(); }
    });
  }

  // ---- scripted auto-demo (mimics the reels) -----------------------------
  let demoTimers=[];
  function autoDemo(){
    demoTimers.forEach(clearTimeout); demoTimers=[];
    const seq=[
      [0,    ()=>{ V.lock(); }],
      [600,  ()=>{ V.wake(); }],
      [1300, ()=>{ V.listen(); }],
      [1500, ()=>{ V.chat.push({role:'user', text:'Hey VECTOR, are you online?'}); }],
      [2600, ()=>{ V.process(); }],
      [3300, ()=>{ V.say('Good evening, sir. All systems nominal.'); }],
      [5200, ()=>{ V.listen(); V.chat.push({role:'user', text:'Play some music and show me my goals.'}); }],
      [6600, ()=>{ V.process(); }],
      [7300, ()=>{ V.openWidget('music'); V.say('Opening the music widget.'); }],
      [9200, ()=>{ V.openWorkspace(); }],
      [9600, ()=>{ V.say('Engaging the workspace. Here is your full status.'); }],
      [12000,()=>{ V.listen(); V.chat.push({role:'user', text:'Pull up the map of Bhubaneswar.'}); }],
      [13200,()=>{ V.process(); }],
      [13900,()=>{ V.showMap(); V.say('Tactical map online.'); }],
      [16200,()=>{ V.closeWorkspace(); }],
      [16700,()=>{ V.vision.open(); }],
      [17600,()=>{ V.say('Vision online. I have eyes on you, sir.'); }]
    ];
    seq.forEach(([t,fn])=>demoTimers.push(setTimeout(fn,t)));
  }

  // ---- init --------------------------------------------------------------
  function init(){ buildDock(); buildDirector(); hotkeys(); }
  if(document.readyState!=='loading') init(); else addEventListener('DOMContentLoaded', init);

  global.VectorDemo = { autoDemo };
})(window);
