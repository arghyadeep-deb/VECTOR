# Streaming Voice + Behavioral Nudging — Design Spec

## Feature 1: Streaming Voice (WebSocket + Push-to-Talk)

**Goal:** Replace existing REST-based voice pipeline (`POST /voice`) with a WebSocket-based
push-to-talk flow where audio streams in real-time and TTS audio streams back.

**Architecture:**
- Client: Modified `VoiceInput.tsx` — MediaRecorder streams chunks through WebSocket,
  plays TTS responses via Web Audio API.
- Backend: New `voice_ws.py` router — WebSocket receives binary audio, buffers until
  `end` signal, runs Whisper STT → LLM → Kokoro TTS, streams result back.

**Data flow:**
1. Client presses mic → opens `ws://host/ws/voice/stream`
2. Client sends binary audio chunks (webm/opus from MediaRecorder)
3. Client sends `{"type": "end"}` on mic release
4. Server runs Whisper on buffered audio → transcript
5. Server sends `{"type": "transcript", "text": "..."}` to client
6. Server runs LLM on transcript → response text
7. Server sends `{"type": "response", "text": "..."}` to client
8. Server runs Kokoro TTS on response → WAV PCM audio
9. Server chunks and sends `{"type": "audio", "data": "<base64>"}` messages
10. Client plays each audio chunk via `AudioContext.decodeAudioData()`
11. Server sends `{"type": "done"}` → closes WebSocket

**Files:**
- Create: `core/api/routers/voice_ws.py`
- Modify: `core/api/app.py` (register new router)
- Modify: `core/ui/dashboard/src/components/VoiceInput.tsx` (WebSocket path)
- Not touching: `core/voice/stt.py`, `core/voice/tts.py` (reused as-is)

---

## Feature 2: Behavioral Nudging

**Goal:** Monitor activity patterns and surface proactive nudges via dashboard toast + voice.

**Architecture:**
- Python `NudgeEngine` in `core/loop/` runs on 30s cron
- Collects signals: git cadence, system idle, active window, error frequency
- Rule engine matches patterns → asks Ollama for contextual nudge text
- Stores latest nudge in-memory → exposed via `GET /nudge/latest`
- Frontend polls every 15s, shows toast + speaks via Kokoro

**Nudge rules (v1):**
- **Deep work**: 45+ min continuous activity → "You've been in flow for 45 minutes."
- **Debug loop**: 5+ rapid build/test failures → "You've hit 5 errors. Try a fresh approach."
- **Idle**: 10+ min inactivity → "You seem stuck. Want me to research something?"
- **Long session**: 2+ hours without break → "You've been at this for 2 hours. Stretch?"

**Files:**
- Create: `core/loop/nudge_engine.py`
- Create: `core/api/routers/nudge.py`
- Create: `core/ui/dashboard/src/components/NudgeToast.tsx`
- Modify: `core/api/app.py` (register nudge router)
- Modify: `core/ui/dashboard/src/App.tsx` (add NudgeToast)
- Modify: `core/ui/dashboard/src/lib/api.ts` (add nudge methods)
