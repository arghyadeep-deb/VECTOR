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

  // Orb sub-label follows the real state, so it can never disagree with it
  // (it used to keep saying STANDBY after a click/workspace-open woke the HUD).
  const ORB_SUB = { boot:'STARTING', locked:'STANDBY', idle:'ONLINE', listening:'LISTENING',
                    processing:'PROCESSING', speaking:'SPEAKING', fortress:'LOCKDOWN' };

  function go(next){
    if(next===state) return;
    const prev = state; state = next;
    setStage(next);
    try{ if(api.orb && ORB_SUB[next]) api.orb.setSub(ORB_SUB[next]); }catch(e){}
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
    // armIdleLock() only otherwise runs inside go() — if state was already
    // 'idle' the line above is a no-op (go() short-circuits on same state),
    // so the idle-lock timer armed *before* the workspace opened would
    // survive and could still fire lock() (closing the workspace + hiding
    // whatever panel the user just opened) while they're actively looking
    // at it. Re-evaluate explicitly (77_FRONTEND_FINAL_ACCEPTANCE.md).
    armIdleLock();
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
  // Auth token is sent as the first JSON message after connection (not in URL)
  // to avoid leaking credentials to server logs, proxies, and browser history.
  //
  // Reconnect: on an unexpected close (laptop sleep/wake, Cloudflare tunnel
  // rotation, a brief network blip) each named socket retries on its own
  // exponential backoff (1s -> 30s cap, jittered) so /ws, /ws/voice/stream
  // and the gesture/camera feeds self-heal instead of staying dead until a
  // manual reconnect or page reload. A deliberate close (disconnect(), or a
  // socket being replaced by a fresh connect()) is flagged via ws._intentional
  // so it never triggers a retry. Exactly one reconnect timer is ever live
  // per socket name (cleared before every re-schedule / on success / on
  // teardown) and reconnects reuse the existing WebSocket instance/handler
  // pattern rather than adding new listeners, so nothing accumulates across
  // however many reconnects happen on this long-lived page.
  const sockets = {};
  const wsSpecs = {};           // name -> { url, onMsg, authToken } — replayed on reconnect
  const reconnectTimers = {};   // name -> setTimeout id
  const reconnectAttempts = {}; // name -> consecutive failed-reconnect count
  let teardownAll = false;      // set by disconnect(); suppresses every pending/future reconnect
  const RECONNECT_BASE_MS = 1000;
  const RECONNECT_MAX_MS = 30000;

  function clearReconnectTimer(name){
    if(reconnectTimers[name] != null){ clearTimeout(reconnectTimers[name]); delete reconnectTimers[name]; }
  }

  // Sockets for optional features. When one cannot connect (no camera, a gesture backend that cannot load) the HUD must not report
  // the whole backend as DEGRADED, and it must not retry forever: the boot status used to read "DEGRADED . ws gesture disconnected"
  // permanently and the backend log filled with ~900 rejected gesture connections.
  const OPTIONAL_WS = { voice:1, gesture:1, camera:1 };
  const OPTIONAL_WS_MAX_ATTEMPTS = 5;

  function scheduleReconnect(name){
    if(teardownAll || !wsSpecs[name]) return; // app-level disconnect, or never configured
    clearReconnectTimer(name);
    const attempt = (reconnectAttempts[name] || 0) + 1;
    reconnectAttempts[name] = attempt;
    if(OPTIONAL_WS[name] && attempt > OPTIONAL_WS_MAX_ATTEMPTS){
      emit('ws:gave-up', { name });
      return;
    }
    const backoff = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * Math.pow(2, attempt - 1));
    const delay = backoff * (0.5 + Math.random() * 0.5); // 50-100% jitter — avoid synchronized retries
    if(typeof api.setRuntimeMode === 'function' && !OPTIONAL_WS[name]){
      api.setRuntimeMode('degraded', 'ws ' + name + ' disconnected · retrying in ' + Math.round(delay / 1000) + 's');
    }
    reconnectTimers[name] = setTimeout(() => {
      delete reconnectTimers[name];
      if(teardownAll) return;
      const spec = wsSpecs[name];
      if(!spec) return;
      openWS(name, spec.url, spec.onMsg, spec.authToken);
    }, delay);
  }

  function openWS(name, url, onMsg, authToken){
    try{
      // Replacing an existing socket for this name (reconnect, or a fresh
      // connect() while one is still open): flag it intentional first so its
      // own onclose doesn't also schedule a competing reconnect.
      clearReconnectTimer(name);
      const prev = sockets[name];
      if(prev){ prev._intentional = true; try{ prev.close(); }catch(_){} }

      wsSpecs[name] = { url, onMsg, authToken };
      const ws = new WebSocket(url);
      ws.onmessage = e => { let d; try{ d=JSON.parse(e.data); }catch(_){ return; } onMsg(d, ws); };
      ws.onclose  = () => {
        emit('ws:close', { name });
        clearTimeout(ws._stableTimer);
        if(ws._intentional) return; // deliberate close — do not retry
        scheduleReconnect(name);
      };
      ws.onerror  = () => emit('ws:error', { name });
      ws.onopen   = () => {
        // Only forgive past failures once the socket has STAYED open for a while. Resetting on
        // every open made a server that accepts then immediately closes (e.g. /gesture/ws with a
        // broken mediapipe) reconnect once per second forever, defeating the backoff.
        clearTimeout(ws._stableTimer);
        ws._stableTimer = setTimeout(() => { reconnectAttempts[name] = 0; }, 10000);
        clearReconnectTimer(name);
        // Send auth handshake as first message if a token is configured
        if(authToken) ws.send(JSON.stringify({ auth: 'Bearer ' + authToken }));
        emit('ws:open', { name });
      };
      sockets[name] = ws; return ws;
    }catch(e){ console.warn('[VECTOR] ws fail', name, e); scheduleReconnect(name); }
  }

  async function connect(cfg){
    CFG = Object.assign(CFG, cfg);
    teardownAll = false; // re-arm reconnect in case a previous disconnect() ran
    // CSRF for browser mutations
    try{ const c = await http('/csrf-token'); CFG.csrf = c.csrf_token; }catch(e){}
    const wsbase = CFG.ws || CFG.base.replace(/^http/,'ws');
    const tok = CFG.apiKey || '';

    // /ws — command + status + orb_state
    openWS('main', wsbase+'/ws', d=>{
      if(d.type==='orb_state' && STATES.includes(d.state)) go(d.state);
      else if(d.type==='response'){ say(d.text); emit('response', d); }
      else if(d.type==='status'){ emit('status', d); }
      else if(d.type==='error'){ emit('error', d); }
    }, tok);
    // /ws/state — event bus bridge
    openWS('state', wsbase+'/ws/state', d=>{
      if(d.type==='state_event') emit('state_event', d);
      else if(d.type==='decision_made') emit('decision_made', d);
      else if(d.type==='hypothesis_surfaced') emit('hypothesis_surfaced', d);
    }, tok);
    // /ws/voice/stream — transcript/response/audio
    openWS('voice', wsbase+'/ws/voice/stream', d=>{
      if(d.type==='transcript'){ api.chat.push({ role:'user', text:d.text }); listen(); }
      else if(d.type==='response_partial'){
        // streaming path: live caption while the LLM is still generating
        if(state!=='speaking'){ go('speaking'); api.orb.setSub('SPEAKING'); }
        api.caption(d.text);
      }
      else if(d.type==='response'){ say(d.text); }
      else if(d.type==='audio'){ emit('audio', d); }
      else if(d.type==='done'){ /* speaking timeout handles return to idle */ }
    }, tok);
    // /gesture/ws — hand landmarks
    openWS('gesture', wsbase+'/gesture/ws', d=>emit('gesture', d), tok);
    // /camera/ws — jpeg frames + detections
    openWS('camera', wsbase+'/camera/ws', d=>emit('camera', d), tok);
    // /notifications/ws — hypotheses
    openWS('notify', wsbase+'/notifications/ws', d=>emit('notify', d), tok);

    emit('connected', CFG);
    return sockets;
  }
  function disconnect(){
    teardownAll = true; // suppress every pending/future reconnect attempt
    Object.keys(reconnectTimers).forEach(clearReconnectTimer);
    Object.values(sockets).forEach(ws=>{ ws._intentional = true; try{ws.close();}catch(_){} });
    Object.keys(wsSpecs).forEach(k => delete wsSpecs[k]);
    Object.keys(reconnectAttempts).forEach(k => delete reconnectAttempts[k]);
  }

  // ---- raw socket access (for binary streams e.g. mic audio) -------------
  function wsConnected(name){ const ws = sockets[name]; return !!ws && ws.readyState === WebSocket.OPEN; }
  function wsSend(name, data){
    const ws = sockets[name];
    if(!ws || ws.readyState !== WebSocket.OPEN) return false;
    try{ ws.send(typeof data === 'string' ? data : data); return true; }
    catch(e){ console.warn('[VECTOR] ws send fail', name, e); return false; }
  }

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
    // raw WS access — used by voice_stream.js to push mic audio to /ws/voice/stream
    wsConnected, wsSend,
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
