/* ============================================================================
   VECTOR · orb.js  — orb SVG layers + live voice waveform + lock-screen clock
   ========================================================================== */
(function (global) {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs){ const e=document.createElementNS(NS,tag);
    for(const k in attrs) e.setAttribute(k, attrs[k]); return e; }

  function buildOrb(mount, label){
    const orb = document.createElement('div');
    orb.className = 'orb';
    // Supplements (does not replace) the existing global stage-click /
    // window-level Enter-to-wake handlers — lets a keyboard user Tab
    // directly to the orb and activate it with Enter or Space.
    orb.setAttribute('role', 'button');
    orb.setAttribute('tabindex', '0');
    orb.setAttribute('aria-label', label ? `${label} — click or press Enter to wake` : 'Click or press Enter to wake VECTOR');
    orb.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); orb.click(); }
    });

    const bloom = document.createElement('div'); bloom.className='orb__bloom'; orb.appendChild(bloom);

    // sparse radial tick marks OUTSIDE the ring (dashes + dots, irregular — like JARVIS)
    const marks = svg('svg', { class:'orb__marks', viewBox:'0 0 100 100' });
    const MARKS = [
      [-86,'dl'],[-72,'dot'],[-58,'d'],[-40,'dl'],[-22,'dot'],[-6,'d'],
      [16,'dl'],[34,'dot'],[52,'d'],[68,'dl'],[88,'dot'],[104,'d'],
      [122,'dl'],[140,'dot'],[160,'d'],[178,'dl'],[200,'dot'],[222,'dl'],[244,'dot'],[262,'d']
    ];
    MARKS.forEach(([deg,type])=>{
      const a=deg*Math.PI/180, r0=51;
      if(type==='dot'){
        marks.appendChild(svg('circle',{ cx:50+Math.cos(a)*r0, cy:50+Math.sin(a)*r0, r:0.7,
          fill:'rgba(127,230,255,.55)' }));
      } else {
        const len = type==='dl'?4:2.4;
        marks.appendChild(svg('line',{
          x1:50+Math.cos(a)*r0, y1:50+Math.sin(a)*r0,
          x2:50+Math.cos(a)*(r0+len), y2:50+Math.sin(a)*(r0+len),
          stroke:'rgba(127,230,255,.55)', 'stroke-width':type==='dl'?0.8:0.6 }));
      }
    });
    orb.appendChild(marks);

    // bright glowing main ring (CSS) + the white-hot pulses
    const ring = document.createElement('div'); ring.className='orb__ring'; orb.appendChild(ring);
    const p1=document.createElement('div'); p1.className='orb__pulse'; orb.appendChild(p1);
    const p2=document.createElement('div'); p2.className='orb__pulse'; orb.appendChild(p2);

    // single thin offset arc at the lower-left (the gyroscope feel)
    const arc = svg('svg',{ class:'orb__arc2', viewBox:'0 0 100 100' });
    arc.appendChild(svg('circle',{ cx:50, cy:50, r:47, fill:'none',
      stroke:'var(--accent-soft)', 'stroke-width':1, 'stroke-linecap':'round',
      'stroke-dasharray':'70 225', 'stroke-dashoffset':'-150',
      transform:'rotate(120 50 50)' }));
    orb.appendChild(arc);

    // live voice waveform (subtle at idle, reactive on listen/speak)
    const wave = document.createElement('canvas'); wave.className='orb__wave';
    orb.appendChild(wave);

    // dark core + wordmark
    const core = document.createElement('div'); core.className='orb__core';
    const lab = document.createElement('div'); lab.className='orb__label'; lab.textContent=label;
    core.appendChild(lab);
    const sub = document.createElement('div'); sub.className='orb__sub'; sub.textContent='ONLINE';
    core.appendChild(sub);
    orb.appendChild(core);

    mount.appendChild(orb);
    startWave(wave);

    // robustly show/hide the crisp parts by state (locked = organic plasma only)
    const crisp = [ring, arc, marks];
    function applyState(){
      const locked = /\b(locked|boot)\b/.test(document.getElementById('stage').className);
      crisp.forEach(elm=>{ elm.style.display = locked ? 'none' : ''; });
    }
    applyState();
    new MutationObserver(applyState).observe(document.getElementById('stage'),
      { attributes:true, attributeFilter:['class'] });

    return { setLabel:t=>lab.textContent=t, setSub:t=>sub.textContent=t, el:orb };
  }

  // ---- the living waveform ------------------------------------------------
  function startWave(canvas){
    const ctx = canvas.getContext('2d');
    const stage = document.getElementById('stage');
    let amp = 0, ampTarget = 0, t = 0, raf;
    const N = 120;
    const seeds = Array.from({length:5}, ()=>({ f: 1+Math.random()*4, p: Math.random()*6.28, s: .4+Math.random()*.9 }));

    function size(){
      const r = canvas.parentElement.getBoundingClientRect();
      const dpr = Math.min(2, devicePixelRatio||1);
      canvas.width = r.width*dpr; canvas.height = r.height*dpr;
      ctx.setTransform(dpr,0,0,dpr,0,0);
    }
    size(); addEventListener('resize', size);
    // re-measure when orb docks/scales
    new ResizeObserver(size).observe(canvas.parentElement);

    function stateAmp(){
      const c = stage.className;
      if(c.includes('speaking'))  return 1.0;
      if(c.includes('listening')) return 0.5;
      if(c.includes('processing'))return 0.28;
      if(c.includes('idle'))      return 0.12;
      return 0.06;                       // locked / boot
    }

    function frame(){
      t += 0.045;
      const cls = stage.className;
      const locked = cls.includes('locked') || cls.includes('boot');
      const audio = (global.VectorAudio ? global.VectorAudio.level() : 0);
      ampTarget = Math.max(stateAmp(), audio);
      amp += (ampTarget - amp) * 0.12;
      const reactive = cls.includes('listening') || cls.includes('speaking');
      const w = canvas.clientWidth, h = canvas.clientHeight, cx=w/2, cy=h/2;
      const speaking = cls.includes('speaking');
      const listening = cls.includes('listening');
      ctx.clearRect(0,0,w,h);

      if(locked){
        // ---- LOCKED: smooth wavy DOUBLE-line ring (the 23:43 lock-screen orb)
        const base = Math.min(w,h) * 0.33;
        // gentle organic wobble — low frequency, smooth; identical per line so
        // the two strokes stay parallel like a hand-drawn double circle
        const wob = ang => (Math.sin(ang*2 + t*0.45)*0.6
                          + Math.sin(ang*3 - t*0.33)*0.4
                          + Math.sin(ang*5 + t*0.20)*0.18) * base*0.07;
        const line = (rOff, alpha, lw, blur) => {
          ctx.beginPath();
          for(let i=0;i<=N;i++){
            const ang=(i/N)*Math.PI*2;
            const r = base + rOff + wob(ang);
            const x=cx+Math.cos(ang)*r, y=cy+Math.sin(ang)*r;
            i?ctx.lineTo(x,y):ctx.moveTo(x,y);
          }
          ctx.closePath();
          ctx.strokeStyle=`rgba(150,205,255,${alpha})`;
          ctx.lineWidth=lw; ctx.shadowBlur=blur; ctx.shadowColor='rgba(70,160,255,.9)';
          ctx.stroke();
        };
        const breathe = Math.sin(t*0.8) * base*0.012;
        line(breathe + base*0.06, 0.30, 7, 26);   // soft outer halo behind
        line(breathe + base*0.055, 0.92, 1.5, 8);  // outer crisp line
        line(breathe - base*0.0,   0.92, 1.5, 8);  // inner crisp line (parallel)
        raf = requestAnimationFrame(frame); return;
      }

      // ---- AWAKE: crisp reactive waveform riding just inside the ring
      const base = Math.min(w,h) * 0.355;
      ctx.beginPath();
      for(let i=0;i<=N;i++){
        const ang = (i/N)*Math.PI*2;
        let off = 0;
        for(const s of seeds) off += Math.sin(ang*s.f + t*s.s + s.p) * s.s;
        const spike = reactive ? Math.sin(ang*9 + t*6) * audio * 6 : 0;
        const jitter = listening ? (Math.random()-0.5)*0.9*(0.4+audio) : 0;
        const r = base + (off*5 + jitter*4 + spike) * amp * (speaking?2.4:1.4);
        const x = cx + Math.cos(ang)*r, y = cy + Math.sin(ang)*r;
        i?ctx.lineTo(x,y):ctx.moveTo(x,y);
      }
      ctx.closePath();
      const a = 0.16 + amp*0.7;
      ctx.strokeStyle = `rgba(127,230,255,${a})`;
      ctx.lineWidth = 1.1;
      ctx.shadowBlur = 10 + amp*18; ctx.shadowColor = 'rgba(0,207,255,.9)';
      ctx.stroke();
      raf = requestAnimationFrame(frame);
    }
    frame();
    return ()=>cancelAnimationFrame(raf);
  }

  function startClock(){
    const t=document.querySelector('#clock .t'), d=document.querySelector('#clock .d');
    function tick(){
      const n=new Date();
      const hh=String(n.getHours()).padStart(2,'0'), mm=String(n.getMinutes()).padStart(2,'0');
      if(t) t.textContent = hh+':'+mm;
      if(d) d.textContent = n.toLocaleDateString('en-GB',{weekday:'long',day:'2-digit',month:'long'})
        .toUpperCase().replace(/,/g,'');
    }
    tick(); setInterval(tick, 1000);
  }

  global.VectorOrb = { buildOrb, startClock };
})(window);
