/* ============================================================================
   VECTOR · speech.js  — real voice. Browser SpeechRecognition (Chrome/Edge).
   Passive wake-word listening ("VECTOR" / "hey vector") → active command
   capture → V.ask(command) → spoken reply. Toggle from the dock VOICE button.
   Needs a user gesture + mic permission (browser policy). Degrades to manual
   click-to-listen if the API is unavailable. When the backend /ws/voice/stream
   is connected it takes over and this stays dormant.
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  const SR = global.SpeechRecognition || global.webkitSpeechRecognition;

  let rec=null, active=false, listeningCmd=false, wantOn=false, restartT=null;
  const WAKE = /\b(vector|hey vector|ok vector|hey vctor)\b/i;

  function supported(){ return !!SR; }

  function build(){
    rec = new SR();
    rec.continuous = true; rec.interimResults = true; rec.lang = 'en-US'; rec.maxAlternatives = 1;
    rec.onresult = onResult;
    rec.onerror = e=>{ if(e.error==='not-allowed'||e.error==='service-not-allowed'){ wantOn=false;
      V.caption('Microphone blocked — allow access to talk to me.'); setTimeout(()=>V.caption(''),2600); } };
    rec.onend = ()=>{ if(wantOn){ clearTimeout(restartT); restartT=setTimeout(()=>{ try{ rec.start(); }catch(e){} }, 350); } };
  }

  let cmdBuf='', cmdTimer=null;
  function onResult(ev){
    let interim='', finalTxt='';
    for(let i=ev.resultIndex;i<ev.results.length;i++){
      const r=ev.results[i]; if(r.isFinal) finalTxt+=r[0].transcript; else interim+=r[0].transcript;
    }
    const heard=(finalTxt||interim).trim();

    if(!listeningCmd){
      // passive: wait for the wake word
      if(WAKE.test(heard)){
        // strip the wake word; whatever follows on the same phrase becomes the command
        const after = heard.replace(WAKE,'').replace(/^[\s,.;:-]+/,'').trim();
        beginCommand(after);
      }
      return;
    }
    // active: accumulate, then fire on a short silence
    if(finalTxt){ cmdBuf=(cmdBuf+' '+finalTxt).trim(); }
    if(interim){ V.caption('“'+(cmdBuf+' '+interim).trim()+'”'); }
    clearTimeout(cmdTimer);
    cmdTimer=setTimeout(fireCommand, 1100);
  }

  function beginCommand(seed){
    listeningCmd=true; cmdBuf=seed||'';
    V.listen();                              // INPUT state — frame glows
    if(global.VectorAudio) global.VectorAudio.startMic();
    V.caption(cmdBuf? '“'+cmdBuf+'”' : 'Listening…');
    clearTimeout(cmdTimer); cmdTimer=setTimeout(fireCommand, cmdBuf? 1100 : 4500);
  }
  function fireCommand(){
    const cmd=cmdBuf.trim(); listeningCmd=false; cmdBuf=''; V.caption('');
    if(cmd){ V.ask(cmd); } else { V.idle(); }   // nothing said → back to idle
  }

  // ---- control -----------------------------------------------------------
  // When the backend's local Whisper/Kokoro pipeline is reachable
  // (/ws/voice/stream open), stream raw mic audio to it and let *that*
  // handle transcription + reply — the browser's cloud SpeechRecognition
  // stays dormant. Falls back to SpeechRecognition only when the backend
  // voice socket is unavailable.
  function backendStreaming(){ return !!(global.VectorVoiceStream && global.VectorVoiceStream.backendReady()); }

  function start(){
    if(backendStreaming()){
      global.VectorVoiceStream.start().then(ok=>{
        if(!ok){ _startRecognition(); return; }
        active=true; wantOn=true;
        V.wake(); V.listen();
        V.caption('Voice online — streaming to local pipeline…');
        setTimeout(()=>{ if(V.state==='idle') V.caption(''); }, 2600);
      });
      return true;
    }
    return _startRecognition();
  }

  function _startRecognition(){
    if(!supported()){ V.caption('Voice recognition not supported in this browser.'); setTimeout(()=>V.caption(''),2400); return false; }
    if(!rec) build();
    wantOn=true; active=true;
    try{ rec.start(); }catch(e){ /* already started */ }
    V.wake();
    V.caption('Voice online — say “Hey VECTOR”.'); setTimeout(()=>{ if(V.state==='idle') V.caption(''); }, 2600);
    return true;
  }

  function stop(){
    wantOn=false; active=false; listeningCmd=false; clearTimeout(restartT); clearTimeout(cmdTimer);
    if(global.VectorVoiceStream && global.VectorVoiceStream.active) global.VectorVoiceStream.stop();
    if(rec){ try{ rec.stop(); }catch(e){} }
    V.caption('');
  }
  function toggle(){ active? stop():start(); return active; }

  global.VectorSpeech = { start, stop, toggle, supported, get active(){ return active; } };
})(window);
