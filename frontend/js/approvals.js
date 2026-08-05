/* ============================================================================
   VECTOR · approvals.js — the "Shall I proceed, sir?" panel.

   Surfaces PermissionGateway YELLOW/RED actions awaiting owner approval.
   Backend (already implemented):
     GET  /gateway/pending            -> {pending:[{id,action_type,params,
                                          proposed_by,level,timestamp}],count}
     POST /gateway/approve/{id}
     POST /gateway/reject/{id}

   Behavior:
     • Polls every 4s while connected (V.http carries auth headers + CSRF).
     • New pending action -> card slides in top-right, alert blip, and VECTOR
       says "Approval required, sir." once per batch (not per item).
     • Approve = green, Reject = red; card resolves optimistically.
   Self-contained: injects its own CSS; no widgets.js changes required.
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  if (!V) return;

  // ---- styles (injected; namespaced .vapr-*) ------------------------------
  const css = `
  #vapr-stack{position:fixed;top:64px;right:16px;z-index:9500;display:flex;
    flex-direction:column;gap:10px;width:340px;pointer-events:none;}
  .vapr-card{pointer-events:auto;background:rgba(4,18,28,.92);
    border:1px solid rgba(0,229,255,.35);border-left:3px solid #ffb300;
    border-radius:10px;padding:12px 14px;color:#cfeef7;
    font:12px/1.45 "Segoe UI",system-ui,sans-serif;
    box-shadow:0 6px 24px rgba(0,0,0,.5);animation:vapr-in .25s ease-out;}
  .vapr-card.vapr-red{border-left-color:#ff5252;}
  .vapr-title{font-size:13px;font-weight:600;color:#fff;margin-bottom:2px;
    display:flex;justify-content:space-between;align-items:center;}
  .vapr-level{font-size:10px;letter-spacing:.12em;padding:1px 7px;
    border-radius:99px;background:rgba(255,179,0,.18);color:#ffb300;}
  .vapr-red .vapr-level{background:rgba(255,82,82,.18);color:#ff5252;}
  .vapr-meta{opacity:.75;margin:4px 0 8px;word-break:break-word;
    max-height:64px;overflow:hidden;}
  .vapr-btns{display:flex;gap:8px;}
  .vapr-btn{flex:1;padding:6px 0;border-radius:7px;border:1px solid transparent;
    cursor:pointer;font:600 12px "Segoe UI",system-ui,sans-serif;
    background:transparent;transition:filter .15s;}
  .vapr-btn:hover{filter:brightness(1.25);}
  .vapr-ok{color:#4ade80;border-color:rgba(74,222,128,.5);}
  .vapr-no{color:#ff5252;border-color:rgba(255,82,82,.5);}
  .vapr-done{opacity:.45;pointer-events:none;}
  @keyframes vapr-in{from{transform:translateX(24px);opacity:0;}
    to{transform:none;opacity:1;}}
  `;
  const styleEl = document.createElement('style');
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  const stack = document.createElement('div');
  stack.id = 'vapr-stack';
  document.body.appendChild(stack);

  // ---- state ---------------------------------------------------------------
  const shown = new Map();   // id -> card element
  let timer = null, connected = false, announced = new Set();

  function esc(s){ const d=document.createElement('div'); d.textContent=String(s||''); return d.innerHTML; }

  function card(item){
    const el = document.createElement('div');
    el.className = 'vapr-card' + ((item.level||'').toUpperCase()==='RED' ? ' vapr-red' : '');
    const params = esc(JSON.stringify(item.params||{}).slice(0,180));
    el.innerHTML =
      `<div class="vapr-title"><span>${esc(item.action_type)}</span>` +
      `<span class="vapr-level">${esc(item.level||'YELLOW')}</span></div>` +
      `<div class="vapr-meta">by ${esc(item.proposed_by||'loop')} · ${params}</div>` +
      `<div class="vapr-btns">` +
      `<button class="vapr-btn vapr-ok">Approve</button>` +
      `<button class="vapr-btn vapr-no">Reject</button></div>`;
    el.querySelector('.vapr-ok').onclick = () => act(item.id, 'approve', el);
    el.querySelector('.vapr-no').onclick = () => act(item.id, 'reject', el);
    return el;
  }

  async function act(id, verb, el){
    el.classList.add('vapr-done');
    try{
      await V.http(`/gateway/${verb}/${encodeURIComponent(id)}`, { method:'POST' });
      if (global.VectorAudio) global.VectorAudio.blip(verb==='approve'?880:300,.12,'sine',.1);
    }catch(e){ console.warn('[approvals]', verb, 'failed', e); el.classList.remove('vapr-done'); return; }
    setTimeout(()=>{ el.remove(); shown.delete(id); }, 350);
  }

  async function poll(){
    if (!connected) return;
    let data;
    try{ data = await V.http('/gateway/pending'); }
    catch(e){ return; }   // backend briefly away — keep quiet, retry next tick
    const pending = (data && data.pending) || [];
    const ids = new Set(pending.map(p=>p.id));

    // remove cards resolved elsewhere (voice approval, timeout, CLI)
    for (const [id, el] of shown){ if(!ids.has(id)){ el.remove(); shown.delete(id); } }

    let fresh = 0;
    for (const item of pending){
      if (shown.has(item.id)) continue;
      const el = card(item);
      stack.appendChild(el);
      shown.set(item.id, el);
      fresh++;
    }
    if (fresh > 0){
      const batch = pending.map(p=>p.id).join(',');
      if (!announced.has(batch)){
        announced.add(batch);
        if (announced.size > 50) announced.clear();
        try{ V.say('Approval required, sir.', { ms: 2200 }); }catch(e){}
        if (global.VectorAudio) global.VectorAudio.blip(620,.18,'triangle',.12);
      }
    }
  }

  V.on('connected', ()=>{ connected = true; clearInterval(timer); timer = setInterval(poll, 4000); poll(); });
  V.on('ws:close', ({name})=>{ if(name==='main') connected = false; });
  // 'main' auto-reconnects after a drop (vector-core.js backoff) and re-fires
  // 'ws:open' — without this, a single blip would permanently stop approval
  // polling for the rest of the session (only the one-time 'connected' event
  // used to turn it back on).
  V.on('ws:open', ({name})=>{ if(name==='main') connected = true; });

  global.VectorApprovals = { poll, get count(){ return shown.size; } };
})(window);
