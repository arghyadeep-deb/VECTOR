/* ============================================================================
   VECTOR · voice_stream.js — real mic capture streamed to the local backend.
   Wires navigator.mediaDevices.getUserMedia + MediaRecorder to the
   /ws/voice/stream WebSocket so VECTOR's own Whisper STT + Kokoro TTS
   pipeline (not the browser's cloud SpeechRecognition) handles voice.

   Protocol (matches core/api/routers/voice_ws.py):
     Client -> Server: binary audio chunks (webm/opus)
     Client -> Server: {"type": "end"}              — stop & transcribe
     Server -> Client: transcript / response / audio / done (handled in
                       vector-core.js's 'voice' WS adapter already)

   This module only owns capture + streaming. Playback of the returned
   `audio` chunks and chat updates are handled where the 'voice' socket
   is consumed (vector-core.js emits 'audio'; widgets.js plays it).
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  if (!V) return;

  const MIME_CANDIDATES = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
  ];

  let stream = null, recorder = null, streaming = false;

  function pickMime() {
    if (!global.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
    return MIME_CANDIDATES.find(m => MediaRecorder.isTypeSupported(m)) || '';
  }

  function supported() {
    return !!(global.navigator && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && global.MediaRecorder);
  }

  // True only when the backend voice socket is actually open — this is the
  // "takes over" condition speech.js defers to (browser SpeechRecognition
  // stays dormant while the real local pipeline is reachable).
  function backendReady() {
    return V.wsConnected && V.wsConnected('voice');
  }

  async function start() {
    if (streaming) return true;
    if (!supported() || !backendReady()) return false;

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      console.warn('[VECTOR] mic permission denied', e);
      return false;
    }

    const mime = pickMime();
    try {
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    } catch (e) {
      console.warn('[VECTOR] MediaRecorder init failed', e);
      _cleanupStream();
      return false;
    }

    recorder.ondataavailable = ev => {
      if (ev.data && ev.data.size > 0 && backendReady()) {
        V.wsSend('voice', ev.data);
      }
    };
    recorder.onerror = e => console.warn('[VECTOR] voice stream recorder error', e);

    streaming = true;
    recorder.start(250); // emit a chunk every 250ms — low enough latency for near-real-time STT
    return true;
  }

  function stop() {
    if (!streaming) return;
    streaming = false;
    try { if (recorder && recorder.state !== 'inactive') recorder.stop(); } catch (_) {}
    if (backendReady()) V.wsSend('voice', JSON.stringify({ type: 'end' }));
    _cleanupStream();
  }

  function _cleanupStream() {
    if (stream) { stream.getTracks().forEach(t => { try { t.stop(); } catch (_) {} }); stream = null; }
    recorder = null;
  }

  global.VectorVoiceStream = { start, stop, supported, backendReady, get active() { return streaming; } };
})(window);
