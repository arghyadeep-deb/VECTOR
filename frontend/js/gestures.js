/* ============================================================================
   VECTOR · gestures.js  — hand cursor (cyan dot), pinch-to-grab widgets.
   Three input sources, unified:
     • mouse     (always available; visual cursor + native drag)
     • mediapipe (in-browser webcam hand tracking — opt in)
     • backend   (VECTOR.on('gesture') frames from /gesture/ws, spec §7)
   Gesture map (spec): point→move · pinch→grab/click · open_palm→wake ·
                       fist→close top widget · swipe→dismiss/pan
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR, W = global.VectorWidgets;
  const cur = document.getElementById('cursor');
  const label = cur.querySelector('.cur-label');
  const stage = document.getElementById('stage');

  let mode = 'off';            // 'off' | 'mouse' | 'hand'
  let pinching = false;
  let pos = { x: innerWidth/2, y: innerHeight/2 };

  function show(on){ cur.classList.toggle('on', !!on); stage.style.cursor = on==='hide' ? 'none' : ''; }
  function setPos(x,y){ pos.x=x; pos.y=y; cur.style.left=x+'px'; cur.style.top=y+'px'; if(pinching) W.dragMove(x,y); }
  function setLabel(t){ label.textContent=t||''; }

  function pinchDown(){ if(pinching) return; pinching=true; cur.classList.add('pinch');
    const got = W.grabAt(pos.x,pos.y); if(!got){ synthClick(); } setLabel('GRAB'); }
  function pinchUp(){ if(!pinching) return; pinching=false; cur.classList.remove('pinch'); W.release(); setLabel('POINT'); }
  function synthClick(){ const t=document.elementFromPoint(pos.x,pos.y);
    if(t && t.closest('#dock,.w-x,.send,.ok2,.no2,.db,.d-btn')) t.click(); }

  // ---- mouse mode (visual cursor; native head-drag still works) ----------
  function onMove(e){ setPos(e.clientX,e.clientY); }
  function enableMouse(){ mode='mouse'; show(true); setLabel('POINT');
    addEventListener('mousemove', onMove); }
  function disableMouse(){ removeEventListener('mousemove', onMove); }

  // ---- MediaPipe webcam hand tracking ------------------------------------
  let mp=null, mpCam=null, lastSwipe=0, prevX=null;
  async function enableHand(){
    if(typeof Hands==='undefined'){ V.say('Hand tracking library unavailable. Falling back to pointer.'); enableMouse(); return false; }
    try{
      const video=document.getElementById('handcam');
      mp=new Hands({ locateFile:f=>`vendor/mediapipe/hands/${f}` });
      mp.setOptions({ maxNumHands:1, modelComplexity:0, minDetectionConfidence:.6, minTrackingConfidence:.6 });
      mp.onResults(onHand);
      mpCam=new Camera(video,{ onFrame:async()=>{ await mp.send({image:video}); }, width:640, height:480 });
      await mpCam.start();
      mode='hand'; show('hide'); setLabel('HAND'); disableMouse();
      return true;
    }catch(e){ console.warn('mediapipe fail',e); V.say('Camera unavailable. Pointer mode engaged.'); enableMouse(); return false; }
  }
  function disableHand(){ try{ mpCam&&mpCam.stop(); }catch(_){} mpCam=null; }

  function dist(a,b){ return Math.hypot(a.x-b.x,a.y-b.y); }
  function onHand(res){
    const hands=res.multiHandLandmarks;
    if(!hands||!hands.length){ if(pinching) pinchUp(); return; }
    const lm=hands[0];
    const idx=lm[8], thumb=lm[4];
    // index fingertip → cursor (mirror X to match the user)
    const x=(1-idx.x)*innerWidth, y=idx.y*innerHeight; setPos(x,y);
    // pinch = thumb/index close
    const pinch=dist(idx,thumb)<0.06;
    if(pinch && !pinching) pinchDown(); else if(!pinch && pinching) pinchUp();
    // open palm = all finger tips well above their knuckles → wake / unlock
    const ext=[8,12,16,20].every(t=>lm[t].y < lm[t-2].y);
    if(ext){ setLabel('OPEN PALM');
      if(V.state==='locked'||stage.classList.contains('fortress')) V.wake(); }
    // fist = tips below knuckles → close topmost widget; fist+pinch within 1s → lock
    const fist=[8,12,16,20].every(t=>lm[t].y > lm[t-2].y);
    if(fist){
      if(!fist._t) fist._t = Date.now(); // mark fist start time
      if(pinch && Date.now() - (onHand._fistAt||0) < 1000){ V.lock(); setLabel('LOCK'); }
      else { const top=topWidget(); if(top) V.closeWidget(top); }
      onHand._fistAt = Date.now();
    } else { onHand._fistAt = 0; }
    // swipe (fast horizontal travel) → toggle workspace
    if(prevX!=null){ const dx=x-prevX, now=Date.now();
      if(Math.abs(dx)>240 && now-lastSwipe>900){ lastSwipe=now; V.toggleWorkspace(); } }
    prevX=x;
  }
  function topWidget(){ const ws=document.querySelectorAll('.widget'); let best=null,zz=-1;
    ws.forEach(w=>{ const z=+w.style.zIndex||0; if(z>=zz){ zz=z; best=w; } }); return best&&best.dataset.id; }

  // ---- backend gesture stream (spec /gesture/ws) -------------------------
  V.on('gesture', d=>{
    if(mode==='mouse') return; // don't fight local mouse
    if(d.x!=null) setPos(d.x*innerWidth, d.y*innerHeight);
    show(true);
    switch(d.gesture){
      case 'pinch': pinchDown(); break;
      case 'point': pinchUp(); setLabel('POINT'); break;
      case 'open_palm': if(V.state==='locked') V.wake(); break;
      case 'fist': {
        const now=Date.now();
        if(now - (V._lastFistGesture||0) < 1000){ V.lock(); }
        else { const t=topWidget(); if(t) V.closeWidget(t); }
        V._lastFistGesture = now; break; }
      case 'swipe_left': case 'swipe_right': V.toggleWorkspace(); break;
    }
  });

  // ---- public ------------------------------------------------------------
  global.VectorCursor = {
    mouse(){ disableHand(); enableMouse(); },
    hand(){ return enableHand(); },
    off(){ disableHand(); disableMouse(); mode='off'; show(false); stage.style.cursor=''; },
    get mode(){ return mode; }
  };
})(window);
