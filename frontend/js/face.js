/* ============================================================================
   VECTOR · face.js  — vision-mode face lock. The reticle tracks your real face
   via MediaPipe FaceDetection; falls back to ambient drift if unavailable.
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  const cam = document.getElementById('herocam');
  const reticle = document.querySelector('#hero-hud .reticle');
  const label = reticle && reticle.querySelector('b');
  let fd=null, running=false, raf=null, misses=0, ready=false;

  function init(){
    if(fd || typeof FaceDetection==='undefined') return !!fd;
    try{
      fd = new FaceDetection({ locateFile:f=>`https://cdn.jsdelivr.net/npm/@mediapipe/face_detection@0.4.1646425229/${f}` });
      fd.setOptions({ model:'short', minDetectionConfidence:0.5 });
      fd.onResults(onResults);
      ready=true;
    }catch(e){ console.warn('[face] init fail', e); fd=null; }
    return !!fd;
  }

  function onResults(res){
    if(!running) return;
    const dets = res.detections || [];
    if(dets.length){
      misses=0;
      const b = dets[0].boundingBox;   // normalized centre + size (0..1)
      // video is mirrored (scaleX(-1)) → flip x
      const cx = (1 - b.xCenter) * 100, cy = b.yCenter * 100;
      const w  = Math.max(14, b.width * 100), h = Math.max(16, b.height * 100 * 1.15);
      reticle.classList.add('lock');
      reticle.style.left = cx+'%'; reticle.style.top = cy+'%';
      reticle.style.width = w+'%'; reticle.style.height = h+'%';
      if(label) label.textContent = 'IDENTITY CONFIRMED · ARGHYADEEP DEB · '+(dets[0].score? (dets[0].score[0]||0.98).toFixed(2):'0.98');
    } else if(++misses > 12){
      reticle.classList.remove('lock');
      reticle.style.cssText='';
      if(label) label.textContent = 'SCANNING · NO SUBJECT';
    }
  }

  async function pump(){
    if(!running) return;
    if(fd && cam.readyState>=2 && cam.videoWidth){ try{ await fd.send({ image:cam }); }catch(e){} }
    raf = requestAnimationFrame(pump);
  }

  function start(){
    if(running) return;
    if(!init()){ // library missing → keep the ambient drift reticle
      if(label) label.textContent='IDENTITY · ARGHYADEEP DEB · 0.98'; return; }
    running=true; misses=0; if(label) label.textContent='SCANNING…';
    pump();
  }
  function stop(){ running=false; if(raf) cancelAnimationFrame(raf);
    if(reticle){ reticle.classList.remove('lock'); reticle.style.cssText=''; } }

  V.on('vision', ({open})=> open ? (authSequence(), start()) : (stop(), clearAuth()) );

  // ---- authentication scan: "AUTHENTICATING… WELCOME BACK, SIR" ---------
  let authT=[];
  function clearAuth(){ authT.forEach(clearTimeout); authT=[];
    const s=document.getElementById('stage'); s.classList.remove('authing','authed'); }
  function authSequence(){
    clearAuth();
    const s=document.getElementById('stage'), txt=document.getElementById('auth-txt');
    if(!txt) return;
    s.classList.add('authing');
    txt.innerHTML='AUTHENTICATING<small>FACIAL RECOGNITION · ACTIVE</small>';
    if(global.VectorAudio) global.VectorAudio.blip(620,.1,'sine',.07);
    authT.push(setTimeout(()=>{ txt.innerHTML='FACIAL MATCH · 98%<small>CROSS-REFERENCING IDENTITY</small>';
      if(global.VectorAudio) global.VectorAudio.blip(760,.1,'sine',.07); }, 1100));
    authT.push(setTimeout(()=>{ s.classList.add('authed');
      txt.innerHTML='WELCOME BACK, SIR<small>ARGHYADEEP DEB · ACCESS GRANTED</small>';
      if(global.VectorAudio){ global.VectorAudio.blip(880,.12,'sine',.08); }
      if(V.state!=='speaking') V.say('Welcome back, sir. Identity confirmed.'); }, 2200));
    authT.push(setTimeout(()=>{ s.classList.remove('authing','authed'); }, 3800));
  }

  global.VectorFace = { start, stop, get ready(){ return ready; } };
})(window);
