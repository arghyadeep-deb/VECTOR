/* ============================================================================
   VECTOR · ambient.js  — living backdrop: drifting particles + scan sweep
   ========================================================================== */
(function (global) {
  'use strict';
  const canvas = document.getElementById('dust');
  const stage  = document.getElementById('stage');
  const ctx = canvas.getContext('2d');
  let W=0,H=0,dpr=Math.min(2,devicePixelRatio||1), parts=[];

  function size(){ W=innerWidth; H=innerHeight; canvas.width=W*dpr; canvas.height=H*dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0); }
  size(); addEventListener('resize', size);

  function reset(p){ p.x=Math.random()*W; p.y=H+Math.random()*H; p.r=Math.random()*1.4+0.3;
    p.s=0.15+Math.random()*0.45; p.a=Math.random()*0.5+0.15; p.tw=Math.random()*6.28; }
  for(let i=0;i<70;i++){ const p={}; reset(p); p.y=Math.random()*H; parts.push(p); }

  function frame(){
    ctx.clearRect(0,0,W,H);
    const awake = stage.classList.contains('awake') || stage.classList.contains('locked');
    const mul = stage.classList.contains('awake') ? 1 : 0.4;
    for(const p of parts){
      p.y -= p.s; p.tw += 0.03;
      if(p.y < -10) reset(p);
      const a = p.a * (0.6 + Math.sin(p.tw)*0.4) * mul;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, 6.28);
      ctx.fillStyle = `rgba(0,207,255,${awake?a:a*0.5})`;
      ctx.fill();
    }
    requestAnimationFrame(frame);
  }
  frame();

  // periodic faint horizontal scan sweep while awake
  const sweep = document.getElementById('sweep');
  setInterval(()=>{ if(stage.classList.contains('awake')){ sweep.classList.remove('go');
    void sweep.offsetWidth; sweep.classList.add('go'); } }, 11000);
})(window);
