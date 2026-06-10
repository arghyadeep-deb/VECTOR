/* ============================================================================
   VECTOR · voice_duplex.js — full-duplex realtime conversation client.
   (docs/REALTIME_CONVERSATION_DESIGN.md Phases 2-5)

   Streams raw PCM (int16 mono 16kHz) to /ws/voice/duplex CONTINUOUSLY —
   no push-to-talk. The SERVER decides when you stopped talking (VAD),
   shows live partial transcripts, answers sentence-by-sentence, can be
   interrupted mid-sentence (barge-in), and may speak first (proactive).

   Server events handled here:
     state · partial_transcript · final_transcript · response_partial ·
     response · audio · stop_audio · action_ack · action_result ·
     proactive · done

   Exposes: VectorVoiceDuplex.start() / .stop() / .active
   Auto-starts on VECTOR 'connected' (mic permission asked once); disable by
   setting  VECTOR_CONFIG.voiceDuplex = false  before connect.
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  if (!V) { console.warn('[duplex] VECTOR core not loaded'); return; }

  let ws = null, ctx = null, src = null, proc = null, micStream = null;
  let active = false;

  // ---- PCM capture: mic → downsample to 16k → int16 frames ---------------
  function downsampleTo16k(input, inRate) {
    if (inRate === 16000) return input;
    const ratio = inRate / 16000;
    const outLen = Math.floor(input.length / ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const start = Math.floor(i * ratio), end = Math.floor((i + 1) * ratio);
      let sum = 0, n = 0;
      for (let j = start; j < end && j < input.length; j++) { sum += input[j]; n++; }
      out[i] = n ? sum / n : 0;
    }
    return out;
  }
  function floatToInt16(f32) {
    const out = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return out;
  }

  async function startMicPump() {
    ctx = new (global.AudioContext || global.webkitAudioContext)();
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });
    src = ctx.createMediaStreamSource(micStream);
    // ScriptProcessor: universally supported (incl. Electron); 4096 samples
    // @ ctx.sampleRate (~48k) ≈ 85ms per frame → ~21ms at 16k after downsample
    proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = (e) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      const pcm = floatToInt16(downsampleTo16k(e.inputBuffer.getChannelData(0), ctx.sampleRate));
      try { ws.send(pcm.buffer); } catch (_) {}
    };
    src.connect(proc);
    proc.connect(ctx.destination); // required by some browsers; processor outputs silence
  }

  function stopMicPump() {
    try { if (proc) { proc.disconnect(); proc.onaudioprocess = null; } } catch (_) {}
    try { if (src) src.disconnect(); } catch (_) {}
    try { if (micStream) micStream.getTracks().forEach(t => t.stop()); } catch (_) {}
    try { if (ctx) ctx.close(); } catch (_) {}
    proc = src = micStream = ctx = null;
  }

  // ---- server event handling ----------------------------------------------
  function onMessage(d) {
    switch (d.type) {
      case 'state':
        if (d.value === 'USER_SPEAKING') V.listen();
        else if (d.value === 'PROCESSING') V.process();
        // VECTOR_SPEAKING is driven by say()/captions below
        break;
      case 'partial_transcript':
        V.caption('▸ ' + d.text);
        break;
      case 'final_transcript':
        V.chat.push({ role: 'user', text: d.text });
        break;
      case 'response_partial':
        if (V.state !== 'speaking') { V.setState('speaking'); V.orb.setSub('SPEAKING'); }
        V.caption(d.text);
        break;
      case 'response':
        V.say(d.text);
        break;
      case 'audio':
        V.emit('audio', d);            // audio.js queues + plays (Kokoro voice)
        break;
      case 'stop_audio':
        V.emit('audio:flush');         // barge-in: kill playback instantly
        V.caption('');
        break;
      case 'action_ack':
        V.chat.push({ role: 'vector', text: d.text + ' (' + d.task_type + ')' });
        break;
      case 'action_result':
        V.say(d.text);
        break;
      case 'proactive':
        V.say(d.text);                 // VECTOR speaks first — JARVIS moment
        break;
      case 'done':
        break;
    }
  }

  // ---- lifecycle ------------------------------------------------------------
  async function start() {
    if (active) return true;
    const cfg = V.config || {};
    const wsbase = cfg.ws || (cfg.base || '').replace(/^http/, 'ws');
    if (!wsbase) { console.warn('[duplex] no backend configured'); return false; }
    try {
      ws = new WebSocket(wsbase + '/ws/voice/duplex');
      ws.binaryType = 'arraybuffer';
      ws.onmessage = (e) => { let d; try { d = JSON.parse(e.data); } catch (_) { return; } onMessage(d); };
      ws.onopen = async () => {
        if (cfg.apiKey) ws.send(JSON.stringify({ auth: 'Bearer ' + cfg.apiKey }));
        await startMicPump();
        active = true;
        console.log('[duplex] realtime conversation live');
      };
      ws.onclose = () => { active = false; stopMicPump(); };
      ws.onerror = () => { active = false; };
      return true;
    } catch (e) { console.warn('[duplex] start failed', e); return false; }
  }

  function stop() {
    try { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'control', action: 'end_session' })); } catch (_) {}
    try { if (ws) ws.close(); } catch (_) {}
    ws = null; active = false; stopMicPump();
  }

  // echo guard: tell the server when our speakers are playing VECTOR's voice
  V.on('server-voice', ({ playing }) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify({ type: 'playing', value: !!playing })); } catch (_) {}
    }
  });

  // auto-start after backend connect (first user gesture already unlocked audio)
  V.on('connected', (cfg) => {
    if (cfg && cfg.voiceDuplex === false) return;
    setTimeout(() => { start(); }, 800);
  });

  global.VectorVoiceDuplex = { start, stop, get active() { return active; } };
})(window);
