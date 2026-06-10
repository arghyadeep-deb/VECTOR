/* ============================================================================
   VECTOR · audio.js  — the sense of hearing & voice.
   • Mic AnalyserNode  → real amplitude while LISTENING
   • Speech synthesis  → word-synced amplitude while SPEAKING (+ caption)
   • Sound design      → UI blips on state/widget events + low ambient hum
   Exposes:  VectorAudio.level()  (0..1, smoothed)  ·  VectorAudio.speak(text)
   AudioContext is created lazily on the first user gesture (browser policy).
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  let ctx=null, master=null;
  let micAnalyser=null, micData=null, micStream=null;
  let level=0, speakEnv=0;            // smoothed mic level / speaking envelope
  let hum=null, humGain=null, noiseGain=null;
  let enabled=true;

  // ---- lazy AudioContext (needs a user gesture) --------------------------
  function ensure(){
    if(ctx) return ctx;
    try{
      ctx = new (global.AudioContext||global.webkitAudioContext)();
      master = ctx.createGain(); master.gain.value = 0.9; master.connect(ctx.destination);
      buildHum();
    }catch(e){ console.warn('[audio] no AudioContext', e); }
    return ctx;
  }
  function resume(){ if(ctx && ctx.state==='suspended') ctx.resume(); }

  // ---- low ambient hum (reactor idle) ------------------------------------
  function buildHum(){
    // two detuned low sines + filtered noise, very quiet, gated by "awake"
    humGain = ctx.createGain(); humGain.gain.value = 0; humGain.connect(master);
    const o1=ctx.createOscillator(); o1.type='sine'; o1.frequency.value=58;
    const o2=ctx.createOscillator(); o2.type='sine'; o2.frequency.value=58*1.5; o2.detune.value=6;
    const og=ctx.createGain(); og.gain.value=.5; o1.connect(og); o2.connect(og); og.connect(humGain);
    // airy noise
    const buf=ctx.createBuffer(1, ctx.sampleRate*2, ctx.sampleRate); const d=buf.getChannelData(0);
    for(let i=0;i<d.length;i++) d[i]=(Math.random()*2-1)*0.5;
    const noise=ctx.createBufferSource(); noise.buffer=buf; noise.loop=true;
    const nf=ctx.createBiquadFilter(); nf.type='bandpass'; nf.frequency.value=520; nf.Q.value=0.7;
    noiseGain=ctx.createGain(); noiseGain.gain.value=.12; noise.connect(nf); nf.connect(noiseGain); noiseGain.connect(humGain);
    // slow LFO on hum gain for "breathing"
    const lfo=ctx.createOscillator(); lfo.type='sine'; lfo.frequency.value=.12;
    const lg=ctx.createGain(); lg.gain.value=.018; lfo.connect(lg); lg.connect(humGain.gain);
    o1.start(); o2.start(); noise.start(); lfo.start();
  }
  function humLevel(v){ if(!humGain) return; humGain.gain.setTargetAtTime(enabled?v:0, ctx.currentTime, .6); }

  // ---- UI blips ----------------------------------------------------------
  function blip(freq, dur, type, vol){
    if(!ensure()||!enabled) return; resume();
    const o=ctx.createOscillator(), g=ctx.createGain();
    o.type=type||'sine'; o.frequency.value=freq;
    const t=ctx.currentTime;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol||.12, t+.008);
    g.gain.exponentialRampToValueAtTime(.0001, t+(dur||.12));
    o.connect(g); g.connect(master); o.start(t); o.stop(t+(dur||.12)+.02);
  }
  function chord(freqs, dur){ freqs.forEach((f,i)=>setTimeout(()=>blip(f,dur||.18,'sine',.08), i*40)); }
  const SND={
    wake:()=>chord([440,660,880],.5),
    listen:()=>blip(720,.1,'triangle',.12),
    process:()=>{ blip(520,.07,'square',.05); setTimeout(()=>blip(640,.07,'square',.05),70); },
    speak:()=>blip(880,.08,'sine',.07),
    lock:()=>chord([520,390],.4),
    open:()=>blip(1040,.06,'triangle',.06),
    close:()=>blip(360,.08,'sine',.06),
    alert:()=>{ blip(300,.16,'sawtooth',.12); setTimeout(()=>blip(300,.16,'sawtooth',.12),200); }
  };

  // ---- microphone analyser (real listening amplitude) -------------------
  async function startMic(){
    if(micAnalyser) return true;
    if(!ensure()) return false; resume();
    try{
      micStream = await navigator.mediaDevices.getUserMedia({ audio:true });
      const src=ctx.createMediaStreamSource(micStream);
      micAnalyser=ctx.createAnalyser(); micAnalyser.fftSize=512; micAnalyser.smoothingTimeConstant=.6;
      micData=new Uint8Array(micAnalyser.frequencyBinCount); src.connect(micAnalyser);
      return true;
    }catch(e){ console.warn('[audio] mic blocked', e); return false; }
  }
  function micLevel(){
    if(!micAnalyser) return 0;
    micAnalyser.getByteTimeDomainData(micData);
    let sum=0; for(let i=0;i<micData.length;i++){ const v=(micData[i]-128)/128; sum+=v*v; }
    return Math.min(1, Math.sqrt(sum/micData.length)*3.2);
  }

  // ---- speech synthesis (word-synced envelope drives the orb) -----------
  let voice=null;
  function pickVoice(){
    const vs=speechSynthesis.getVoices();
    voice = vs.find(v=>/daniel|google uk english male|arthur/i.test(v.name))
         || vs.find(v=>/en-GB/i.test(v.lang)) || vs.find(v=>/en/i.test(v.lang)) || vs[0];
  }
  if('speechSynthesis' in global){ pickVoice(); speechSynthesis.onvoiceschanged=pickVoice; }

  function speak(text){
    if(!('speechSynthesis' in global) || !enabled) return;
    try{ speechSynthesis.cancel(); }catch(e){}
    const u=new SpeechSynthesisUtterance(text);
    if(voice) u.voice=voice; u.rate=1.02; u.pitch=.92; u.volume=1;
    // envelope: ramp up on speech, pulse per word boundary
    u.onstart=()=>{ speakEnv=.5; };
    u.onboundary=()=>{ speakEnv=Math.min(1,.55+Math.random()*.45); };
    u.onend=()=>{ speakEnv=0; };
    speechSynthesis.speak(u);
  }

  // ---- the level the orb reads -------------------------------------------
  function tick(){
    const s=document.getElementById('stage').className;
    let target=0;
    if(s.includes('speaking')){
      target = speakEnv; speakEnv *= .90;            // decay between word pulses
    } else if(s.includes('listening')){
      target = micLevel();
    }
    level += (target - level) * 0.25;
    requestAnimationFrame(tick);
  }
  tick();

  // ---- wire to VECTOR events --------------------------------------------
  if(V){
    V.on('state', ({from,to})=>{
      if(SND[to]) SND[to]();
      humLevel(['idle','listening','processing','speaking','docked'].includes(to)?0.06:0.0);
      if(to==='listening') startMic();
      if(to==='fortress') SND.alert();
    });
    V.on('wake', ()=>{ humLevel(.06); });
    V.on('say', ({text})=>{
      // Server (Kokoro) audio takes priority — only use browser TTS when no
      // server audio arrived for this turn (e.g. backend TTS unavailable).
      if(text && !serverVoiceRecent()) speak(text);
    });
    V.on('audio', d=>enqueueServerAudio(d));
    V.on('widget:open', ()=>SND.open());
    V.on('widget:close', ()=>SND.close());
    V.on('workspace', ({open})=>open?chord([660,990],.3):SND.close());
  }

  // ---- server (Kokoro) audio playback queue ------------------------------
  // Sentence-streamed WAVs from /ws/voice/stream: each 'audio' message is one
  // complete WAV. Decode independently, play strictly in order. While server
  // audio plays, drive speakEnv so the orb reacts, and suppress browser TTS.
  let srvQueue=[], srvPlaying=false, srvLastAt=0;
  function serverVoiceRecent(){ return srvPlaying || (Date.now()-srvLastAt) < 3000; }
  function b64ToArrayBuffer(b64){
    const bin=atob(b64), len=bin.length, buf=new Uint8Array(len);
    for(let i=0;i<len;i++) buf[i]=bin.charCodeAt(i);
    return buf.buffer;
  }
  function enqueueServerAudio(d){
    if(!d || !d.data || !enabled) return;
    const c=ensure(); if(!c) return; resume();
    srvLastAt=Date.now();
    c.decodeAudioData(b64ToArrayBuffer(d.data))
      .then(buf=>{ srvQueue.push(buf); pumpServerAudio(); })
      .catch(e=>console.warn('[audio] server wav decode failed', e));
  }
  function pumpServerAudio(){
    if(srvPlaying || !srvQueue.length || !ctx) return;
    srvPlaying=true; srvLastAt=Date.now();
    const buf=srvQueue.shift();
    const src=ctx.createBufferSource(); src.buffer=buf; src.connect(master);
    const env=setInterval(()=>{ speakEnv=0.35+Math.random()*0.45; }, 90);
    src.onended=()=>{ clearInterval(env); speakEnv=0; srvPlaying=false; srvLastAt=Date.now(); pumpServerAudio(); };
    try{ src.start(); }catch(e){ clearInterval(env); speakEnv=0; srvPlaying=false; console.warn('[audio] server wav play failed', e); }
  }

  // first-gesture unlock
  ['click','keydown','pointerdown'].forEach(ev=>addEventListener(ev, function once(){
    ensure(); resume(); removeEventListener(ev, once);
  }, { once:true }));

  global.VectorAudio = {
    level:()=>level,
    speak, blip, startMic,
    setEnabled(v){ enabled=v; if(!v){ humLevel(0); try{speechSynthesis.cancel();}catch(e){} } },
    get enabled(){ return enabled; }
  };
})(window);
