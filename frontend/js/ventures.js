/* ============================================================================
   VECTOR · ventures.js — side-hustle pipeline results in the HUD.

   Shows the latest venture-pipeline output (ranked problem clusters) as a
   card; one-tap actions stay OWNER-GATED — buttons send a /command through
   the governor, so PermissionGateway classification applies as always.

   Backend:
     GET  /startups/ventures/latest  -> {status, analyzed_at, clusters[], report}
     POST /startups/ventures/run     -> run the full pipeline now

   Open via:  VECTOR.openWidget-style — this registers a floating panel toggled
   by VectorVentures.toggle(), terminal "ventures", or voice "show ventures".
   Self-contained (injects its own CSS).
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  if (!V) return;

  const css = `
  #vven-panel{position:fixed;bottom:18px;right:16px;z-index:9400;width:380px;
    max-height:60vh;overflow-y:auto;background:rgba(3,15,24,.94);
    border:1px solid rgba(0,229,255,.3);border-radius:12px;padding:14px 16px;
    color:#cfeef7;font:12px/1.5 "Segoe UI",system-ui,sans-serif;
    box-shadow:0 8px 30px rgba(0,0,0,.55);display:none;}
  #vven-panel.show{display:block;animation:vven-in .25s ease-out;}
  .vven-h{display:flex;justify-content:space-between;align-items:center;
    margin-bottom:8px;}
  .vven-h b{font-size:13px;color:#fff;letter-spacing:.04em;}
  .vven-sub{opacity:.65;font-size:11px;margin-bottom:10px;}
  .vven-item{border:1px solid rgba(0,229,255,.18);border-radius:9px;
    padding:9px 11px;margin-bottom:8px;}
  .vven-prob{color:#fff;font-weight:600;margin-bottom:3px;}
  .vven-idea{color:#7fe3ff;margin-bottom:5px;}
  .vven-stats{opacity:.7;font-size:11px;margin-bottom:7px;}
  .vven-acts{display:flex;gap:7px;}
  .vven-btn{padding:4px 10px;border-radius:6px;cursor:pointer;
    border:1px solid rgba(0,229,255,.4);background:transparent;color:#7fe3ff;
    font:600 11px "Segoe UI",system-ui,sans-serif;}
  .vven-btn:hover{filter:brightness(1.3);}
  .vven-run{width:100%;margin-top:4px;padding:7px 0;border-radius:8px;
    border:1px solid rgba(74,222,128,.45);color:#4ade80;background:transparent;
    cursor:pointer;font:600 12px "Segoe UI",system-ui,sans-serif;}
  .vven-x{cursor:pointer;opacity:.6;font-size:15px;background:none;border:none;
    color:#cfeef7;}
  @keyframes vven-in{from{transform:translateY(14px);opacity:0;}to{transform:none;opacity:1;}}
  `;
  const st = document.createElement('style'); st.textContent = css;
  document.head.appendChild(st);

  const panel = document.createElement('div');
  panel.id = 'vven-panel';
  document.body.appendChild(panel);

  function esc(s){ const d=document.createElement('div'); d.textContent=String(s||''); return d.innerHTML; }

  function render(data){
    const clusters = (data.clusters||[]).filter(c=>c.software_solvable).slice(0,5);
    let html =
      `<div class="vven-h"><b>VENTURE PIPELINE</b>` +
      `<button class="vven-x" title="close">✕</button></div>` +
      `<div class="vven-sub">${data.status==='ok'
        ? `run ${esc(data.analyzed_at)} · ${data.total_posts} posts analyzed · report: ${esc(data.report||'—')}`
        : 'No pipeline run yet — it fires every Monday 07:00, or run it now.'}</div>`;
    for (const c of clusters){
      html +=
        `<div class="vven-item">` +
        `<div class="vven-prob">${esc(c.problem)}</div>` +
        (c.product_idea ? `<div class="vven-idea">💡 ${esc(c.product_idea)}</div>` : '') +
        `<div class="vven-stats">${c.size} posts · demand ${c.demand_score} · ${esc((c.sources||[]).join(', '))}</div>` +
        `<div class="vven-acts">` +
        `<button class="vven-btn" data-act="build" data-idea="${esc(c.product_idea||c.problem)}">Build MVP</button>` +
        `<button class="vven-btn" data-act="content" data-idea="${esc(c.product_idea||c.problem)}">Draft content</button>` +
        `<button class="vven-btn" data-act="validate" data-idea="${esc(c.product_idea||c.problem)}">Deep validate</button>` +
        `</div></div>`;
    }
    html += `<button class="vven-run">⟳ Run pipeline now</button>`;
    panel.innerHTML = html;

    panel.querySelector('.vven-x').onclick = ()=>panel.classList.remove('show');
    panel.querySelector('.vven-run').onclick = runNow;
    panel.querySelectorAll('.vven-btn').forEach(btn=>{
      btn.onclick = ()=>dispatch(btn.dataset.act, btn.dataset.idea);
    });
  }

  // Owner-gated: everything routes through /command -> governor -> gateway.
  async function dispatch(act, idea){
    const text = act==='build'   ? `start a code task: build an MVP of ${idea}`
               : act==='content' ? `generate a marketing script for ${idea}`
               :                   `validate this startup idea in depth: ${idea}`;
    try{
      await V.command(text, 'high');
      V.say(act==='build' ? 'Code task queued — I will ask before anything risky.'
           : act==='content' ? 'Drafting content. Nothing posts without you.'
           : 'Running deep validation.', { ms: 2600 });
    }catch(e){ console.warn('[ventures] dispatch failed', e); }
  }

  async function runNow(){
    const btn = panel.querySelector('.vven-run');
    btn.textContent = '⟳ Running… (this mines Reddit/HN, ~1-2 min)';
    btn.disabled = true;
    try{
      await V.http('/startups/ventures/run', { method:'POST' });
      await refresh();
      V.say('Venture pipeline complete.', { ms: 2200 });
    }catch(e){ console.warn('[ventures] run failed', e); }
    btn.disabled = false;
  }

  async function refresh(){
    try{ render(await V.http('/startups/ventures/latest')); }
    catch(e){ render({status:'none', clusters:[]}); }
  }

  function toggle(){
    if (panel.classList.contains('show')) panel.classList.remove('show');
    else { panel.classList.add('show'); refresh(); }
  }

  // surface hooks: terminal command + voice phrase + nudge click-through
  V.on('say', ({text})=>{
    if (text && /venture pipeline finished/i.test(text)) { panel.classList.add('show'); refresh(); }
  });

  global.VectorVentures = { toggle, refresh };
})(window);
