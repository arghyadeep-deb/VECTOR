/* ============================================================================
   VECTOR · cinematic.js  — the "alive" layer
   • Spoken, time-aware greeting on wake
   • Thinking trace (scrolling reasoning) near the orb while PROCESSING
   • Holographic parallax (orb + panels + backdrop drift with the cursor)
   • Targeting scan-lock flourish when a widget materializes
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR, D = global.VECTOR_DATA, stage = document.getElementById('stage');

  /* ---- 1 · spoken greeting on wake ------------------------------------ */
  let lastGreet = 0;
  function greeting(){
    const h = new Date().getHours();
    const part = h<5?'You are up late':h<12?'Good morning':h<17?'Good afternoon':h<22?'Good evening':'Working late';
    const t = new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
    const pend = (D && D.APPROVALS) ? D.APPROVALS.length : 0;
    const goals = (D && D.GOALS) ? (D.GOALS.LONG.length+D.GOALS.MID.length+D.GOALS.SHORT.length) : 0;
    // Only state what the backend actually reported. "All systems nominal" used to be spoken unconditionally,
    // even with the threat level HIGH or the loop down.
    const L = (D && D.LIVE) || {};
    let tail;
    if(pend){
      tail = ` You have ${pend} approval${pend>1?'s':''} pending and ${goals} active goals.`;
    } else if(L.loop){
      const bits = [L.loop.running ? 'The loop is running.' : 'The loop is not running.'];
      if(L.threat && String(L.threat).toLowerCase() !== 'low') bits.push(`Threat level ${String(L.threat).toLowerCase()}.`);
      tail = ' ' + bits.join(' ');
    } else {
      tail = '';
    }
    return `${part}, sir. It is ${t}.${tail}`;
  }
  V.on('wake', ()=>{
    const now = Date.now();
    if(now - lastGreet < 30000) return;     // don't greet on every micro-wake
    lastGreet = now;
    setTimeout(()=>{ if(V.state==='idle') V.say(greeting()); }, 650);
  });

  /* ---- 2 · thinking trace --------------------------------------------- */
  const POOL = [
    'parsing intent', 'tokenising utterance', 'querying episodic memory',
    'semantic recall · 3 hits', 'routing → research district', 'routing → coding district',
    'spawning 4 candidates', 'goal-alignment 0.30', 'confidence 0.25', 'policy score 0.82',
    'red-team pass · clear', 'permission gate · GREEN', 'ranking candidates',
    'chairman synthesis', 'composing response'
  ];
  let think = null, thinkTimer = null;
  function ensureThink(){
    if(think) return think;
    think = document.createElement('div'); think.id='think';
    think.innerHTML = '<div class="th-head"><span class="th-dot"></span>COGNITION TRACE</div><div class="th-log"></div>';
    stage.appendChild(think); return think;
  }
  function placeThink(){
    const orb = document.getElementById('orb-wrap').getBoundingClientRect();
    const t = ensureThink();
    const w = 250;
    let left = orb.left + orb.width/2 - w/2;
    let top  = orb.top + orb.height/2 + orb.height*0.30;
    // if docked bottom-right, sit the trace to the LEFT of the orb instead
    if(stage.classList.contains('docked')){ left = orb.left - w - 18; top = orb.top + orb.height*0.2; }
    left = Math.max(16, Math.min(innerWidth - w - 16, left));
    top  = Math.max(16, Math.min(innerHeight - 150, top));
    t.style.left = left+'px'; t.style.top = top+'px'; t.style.width = w+'px';
  }
  function startThink(){
    const t = ensureThink(); placeThink(); t.classList.add('on');
    const logEl = t.querySelector('.th-log'); logEl.innerHTML='';
    const picks = shuffle(POOL).slice(0, 5+Math.floor(Math.random()*3));
    let i=0; clearInterval(thinkTimer);
    thinkTimer = setInterval(()=>{
      if(i>=picks.length || !stage.className.includes('processing')){ clearInterval(thinkTimer); return; }
      const line=document.createElement('div'); line.className='th-line';
      line.innerHTML = '<i>▸</i> '+picks[i++]+' <b>✓</b>';
      logEl.appendChild(line); logEl.scrollTop = logEl.scrollHeight;
    }, 220);
  }
  function stopThink(){ if(think){ think.classList.remove('on'); } clearInterval(thinkTimer); }
  function shuffle(a){ a=a.slice(); for(let i=a.length-1;i>0;i--){ const j=Math.random()*(i+1)|0; [a[i],a[j]]=[a[j],a[i]]; } return a; }
  V.on('state', ({to})=>{ if(to==='processing') startThink(); else stopThink(); });

  /* ---- 3 · holographic parallax --------------------------------------- */
  let tx=0, ty=0, cx=0, cy=0;
  addEventListener('pointermove', e=>{
    tx = (e.clientX/innerWidth - .5);     // -0.5..0.5
    ty = (e.clientY/innerHeight - .5);
  }, { passive:true });
  (function loop(){
    cx += (tx-cx)*0.06; cy += (ty-cy)*0.06;
    const s = stage.style;
    // near plane (panels) move OPPOSITE the cursor; far plane (grid/dust) move WITH it
    s.setProperty('--ox', (-cx*16).toFixed(2)+'px');  s.setProperty('--oy', (-cy*16).toFixed(2)+'px');
    s.setProperty('--nx', (-cx*26).toFixed(2)+'px');  s.setProperty('--ny', (-cy*26).toFixed(2)+'px');
    s.setProperty('--fx', ( cx*12).toFixed(2)+'px');  s.setProperty('--fy', ( cy*12).toFixed(2)+'px');
    requestAnimationFrame(loop);
  })();

  /* ---- 4 · targeting scan-lock when a widget opens -------------------- */
  // widgets.js stamps each card; we draw a converging reticle just before it shows.
  V.on('widget:lock', ({rect})=>{
    if(!rect) return;
    const r=document.createElement('div'); r.className='target-lock';
    r.style.left=rect.left+'px'; r.style.top=rect.top+'px';
    r.style.width=rect.width+'px'; r.style.height=rect.height+'px';
    r.innerHTML='<i class="tl"></i><i class="tr"></i><i class="bl"></i><i class="br"></i>';
    stage.appendChild(r);
    requestAnimationFrame(()=>r.classList.add('go'));
    setTimeout(()=>r.remove(), 520);
  });

  global.VectorCinematic = { greeting };
})(window);
