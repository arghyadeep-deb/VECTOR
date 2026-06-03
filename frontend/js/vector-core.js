/* ============================================================================
   VECTOR · vector-core.js
   The control layer. One global `VECTOR` object drives the whole HUD.
   ----------------------------------------------------------------------------
   TWO WAYS TO DRIVE IT
   1.  Call the API directly:
         VECTOR.wake(); VECTOR.listen(); VECTOR.say('Good evening, sir.');
         VECTOR.openWorkspace(); VECTOR.openWidget('music', {...});
   2.  Point it at your FastAPI backend and let events drive it:
         VECTOR.connect({ base:'http://127.0.0.1:8000',
                          ws:'ws://127.0.0.1:8000', apiKey:'...' });
       It opens /ws, /ws/state, /gesture/ws, /camera/ws, /notifications/ws and
       maps your documented messages → UI (orb_state, state_event, transcript,
       response, audio, gesture frames, camera frames, hypotheses).
   ----------------------------------------------------------------------------
   FSM (spec §12):
     boot → idle → [wake] listening → processing → speaking → idle
     idle (60s) → locked ;  locked → [wake] idle ;  [threat] → fortress
     workspace = the *secret* heavy-work HUD (panel rings) — overlays idle/active
   ========================================================================== */
(function (global) {
  'use strict';

  const STAGE = () => document.getElementById('stage');
  const STATES = ['boot','locked','idle','listening','processing','speaking','fortress'];

  // ---- tiny event bus ----------------------------------------------------
  const bus = {};
  function on(ev, cb){ (bus[ev]||(bus[ev]=[])).push(cb); return ()=>off(ev,cb); }
  function off(ev, cb){ if(bus[ev]) bus[ev]=bus[ev].filter(f=>f!==cb); }
  function emit(ev, payload){ (bus[ev]||[]).forEach(f=>{ try{ f(payload); }catch(e){ console.warn(e);} });
    (bus['*']||[]).forEach(f=>f(ev,payload)); }

  // ---- state -------------------------------------------------------------
  let state = 'boot';
  let workspaceOpen = false;
  let idleTimer = null;
  const IDLE_LOCK_MS = 60000;

  function setStage(cls){
    const s = STAGE();
    STATES.forEach(x=>s.classList.remove(x));
    s.classList.add(cls);
    // "awake" => grid + tickers; not when locked/boot/fortress
    s.classList.toggle('awake', ['idle','listening','processing','speaking'].includes(cls));
  }

  function go(next){
    if(next===state) return;
    const prev = state; state = next;
    setStage(next);
    armIdleLock();
    emit('state', { from:prev, to:next });
  }

  function armIdleLock(){
    clearTimeout(idleTimer);
    if(state==='idle' && !workspaceOpen){
      idleTimer = setTimeout(()=>lock(), IDLE_LOCK_MS);
    }
  }

  // ---- public state transitions -----------------------------------------
  function boot(){
    setStage('boot');
    emit('boot');
    // boot overlay handled in boot.js; it calls VECTOR._afterBoot()
  }
  function _afterBoot(){ lock(); }

  function lock(){ workspaceOpen && closeWorkspace(); STAGE().classList.remove('docked','wsopen'); go('locked');
    api.orb.setSub('STANDBY'); }
  function wake(){ if(state==='fortress') return; go('idle'); api.orb.setSub('ONLINE'); emit('wake'); }
  function idle(){ go('idle'); }
  function listen(){ wakeIfNeeded(); STAGE().classList.toggle('docked', workspaceOpen); go('listening');
    api.orb.setSub('LISTENING'); }
  function process(){ wakeIfNeeded(); go('processing'); api.orb.setSub('PROCESSING'); }
  function fortress(){ workspaceOpen && closeWorkspace(); go('fortress'); }

  function say(text, opts){
    wakeIfNeeded();
    go('speaking'); api.orb.setSub('SPEAKING');
    if(text){ api.chat.push({ role:'vector', text }); api.caption(text); }
    emit('say', { text, opts });
    const ms = opts && opts.ms != null ? opts.ms
             : Math.min(7000, Math.max(1600, (text? text.length:20) * 55));
    clearTimeout(say._t);
    say._t = setTimeout(()=>{ if(state==='speaking'){ go('idle'); api.orb.setSub('ONLINE'); api.caption(''); } }, ms);
  }
  function wakeIfNeeded(){ if(state==='locked'||state==='boot'){ go('idle'); } }

  // ---- secret workspace --------------------------------------------------
  function openWorkspace(){ if(workspaceOpen) return; workspaceOpen=true;
    wakeIfNeeded(); STAGE().classList.add('docked','wsopen');
    if(['locked','boot'].includes(state)) go('idle');
    emit('workspace', { open:true }); }
  function closeWorkspace(){ if(!workspaceOpen) return; workspaceOpen=false;
    const s=STAGE(); s.classList.remove('wsopen');
    if(!s.classList.contains('vision')) s.classList.remove('docked');
    emit('workspace', { open:false }); armIdleLock(); }
  function toggleWorkspace(){ workspaceOpen ? closeWorkspace() : openWorkspace(); }

  // ---- widgets (implemented in widgets.js via events) --------------------
  function openWidget(id, opts){ wakeIfNeeded(); if(!workspaceOpen) openWorkspace();
    emit('widget:open', { id, opts:opts||{} }); }
  function closeWidget(id){ emit('widget:close', { id }); }
  function showMap(opts){ openWidget('map', opts||{}); }

  // ---- HTTP helper (auth per spec §2/§3) --------------------------------
  let CFG = { base:'', ws:'', apiKey:'', csrf:'' };
  async function http(path, { method='GET', body=null } = {}){
    const headers = { 'Content-Type':'application/json' };
    if(CFG.apiKey) headers['Authorization'] = 'Bearer ' + CFG.apiKey;
    if(method!=='GET' && CFG.csrf) headers['X-CSRF-Token'] = CFG.csrf;
    const res = await fetch(CFG.base + path, { method, headers, body: body? JSON.stringify(body):null });
    if(!res.ok) throw new Error(path+' → '+res.status);
    return res.json();
  }
  async function command(text, priority){ return http('/command', { method:'POST',
    body:{ text, source:'hud', priority: priority||'normal' } }); }

  // ---- WebSocket adapter (spec §7) --------------------------------------
  const sockets = {};
  function openWS(name, url, onMsg){
    try{
      const ws = new WebSocket(url);
      ws.onmessage = e => { let d; try{ d=JSON.parse(e.data); }catch(_){ return; } onMsg(d, ws); };
      ws.onclose  = () => emit('ws:close', { name });
      ws.onerror  = () => emit('ws:error', { name });
      ws.onopen   = () => emit('ws:open',  { name });
      sockets[name] = ws; return ws;
    }catch(e){ console.warn('[VECTOR] ws fail', name, e); }
  }

  async function connect(cfg){
    CFG = Object.assign(CFG, cfg);
    // CSRF for browser mutations
    try{ const c = await http('/csrf-token'); CFG.csrf = c.csrf_token; }catch(e){}
    const wsbase = CFG.ws || CFG.base.replace(/^http/,'ws');
    const tok = CFG.apiKey ? ('?token=Bearer+'+encodeURIComponent(CFG.apiKey)) : '';

    // /ws — command + status + orb_state
    openWS('main', wsbase+'/ws'+tok, d=>{
      if(d.type==='orb_state' && STATES.includes(d.state)) go(d.state);
      else if(d.type==='response'){ say(d.text); emit('response', d); }
      else if(d.type==='status'){ emit('status', d); }
      else if(d.type==='error'){ emit('error', d); }
    });
    // /ws/state — event bus bridge
    openWS('state', wsbase+'/ws/state', d=>{
      if(d.type==='state_event') emit('state_event', d);
      else if(d.type==='decision_made') emit('decision_made', d);
      else if(d.type==='hypothesis_surfaced') emit('hypothesis_surfaced', d);
    });
    // /ws/voice/stream — transcript/response/audio
    openWS('voice', wsbase+'/ws/voice/stream', d=>{
      if(d.type==='transcript'){ api.chat.push({ role:'user', text:d.text }); listen(); }
      else if(d.type==='response'){ say(d.text); }
      else if(d.type==='audio'){ emit('audio', d); }
      else if(d.type==='done'){ /* speaking timeout handles return to idle */ }
    });
    // /gesture/ws — hand landmarks
    openWS('gesture', wsbase+'/gesture/ws', d=>emit('gesture', d));
    // /camera/ws — jpeg frames + detections
    openWS('camera', wsbase+'/camera/ws', d=>emit('camera', d));
    // /notifications/ws — hypotheses
    openWS('notify', wsbase+'/notifications/ws', d=>emit('notify', d));

    emit('connected', CFG);
    return sockets;
  }
  function disconnect(){ Object.values(sockets).forEach(ws=>{ try{ws.close();}catch(_){}}); }

  // ---- caption strip + chat/music are bound by widgets.js ---------------
  function noop(){}
  const api = {
    // state
    boot, _afterBoot, lock, sleep:lock, wake, idle, listen, process, think:process, say, fortress,
    get state(){ return state; }, get isWorkspaceOpen(){ return workspaceOpen; },
    setState(s){ STATES.includes(s) ? go(s) : console.warn('unknown state', s); },
    // workspace + widgets
    openWorkspace, closeWorkspace, toggleWorkspace, engageHUD:openWorkspace, disengageHUD:closeWorkspace,
    openWidget, closeWidget, showMap,
    // backend
    connect, disconnect, http, command, get config(){ return CFG; },
    // events
    on, off, emit,
    // bound late by widgets.js / orb.js:
    orb:{ setLabel:noop, setSub:noop },
    chat:{ push:noop }, music:{ set:noop }, caption:noop,
    // user-activity ping (resets idle-lock)
    poke(){ if(state==='idle') armIdleLock(); }
  };

  global.VECTOR = api;
})(window);
