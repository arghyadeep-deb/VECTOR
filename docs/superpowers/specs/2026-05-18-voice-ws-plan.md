# Streaming Voice WebSocket — Implementation Plan

**Goal:** Replace REST voice pipeline with WebSocket push-to-talk.
**Architecture:** WebSocket at `/ws/voice/stream`. Client streams chunks, server runs Whisper→LLM→TTS, streams audio back.

---

### Task 1: Backend WebSocket endpoint

**File:** Create `core/api/routers/voice_ws.py`

```python
"""WebSocket endpoint for streaming voice — push-to-talk flow.

Protocol:
  Client → Server: binary audio chunks (webm/opus)
  Client → Server: {"type": "end"}
  Server → Client: {"type": "transcript", "text": "..."}
  Server → Client: {"type": "response", "text": "..."}
  Server → Client: {"type": "audio", "data": "<base64 wav chunk>"}
  Server → Client: {"type": "done"}
  Close
"""

import sys, asyncio, base64, io, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import numpy as np
import soundfile as sf
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter(prefix="/ws/voice", tags=["voice"])


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    chunks: list[bytes] = []
    logger.info("[VECTOR][voice_ws] Client connected")

    try:
        # Phase 1: Receive audio chunks until end signal
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.receive" and "text" in raw:
                try:
                    msg = json.loads(raw["text"])
                    if msg.get("type") == "end":
                        break
                except json.JSONDecodeError:
                    continue
            elif raw.get("type") == "websocket.receive" and "bytes" in raw:
                chunks.append(raw["bytes"])

        if not chunks:
            await websocket.send_json({"type": "error", "text": "No audio received"})
            await websocket.close()
            return

        # Phase 2: Transcribe
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(None, _transcribe, chunks)
        if not transcript:
            await websocket.send_json({"type": "error", "text": "Could not transcribe audio"})
            await websocket.close()
            return
        await websocket.send_json({"type": "transcript", "text": transcript})
        logger.info(f"[VECTOR][voice_ws] Transcript: {transcript}")

        # Phase 3: LLM response
        response_text = await loop.run_in_executor(None, _llm_respond, transcript)
        await websocket.send_json({"type": "response", "text": response_text})

        # Phase 4: TTS
        wav_bytes = await loop.run_in_executor(None, _tts_to_wav, response_text)
        if wav_bytes:
            chunk_size = 32000  # ~2s of 16kHz mono 16-bit PCM
            for i in range(0, len(wav_bytes), chunk_size):
                chunk = wav_bytes[i:i + chunk_size]
                await websocket.send_json({
                    "type": "audio",
                    "data": base64.b64encode(chunk).decode(),
                    "sample_rate": 24000,
                })
                await asyncio.sleep(0.1)

        await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("[VECTOR][voice_ws] Client disconnected")
    except Exception as e:
        logger.error(f"[VECTOR][voice_ws] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _transcribe(chunks: list[bytes]) -> str:
    import soundfile as sf
    import io
    import numpy as np

    raw = b"".join(chunks)
    try:
        audio_io = io.BytesIO(raw)
        audio_np, sr = sf.read(audio_io, dtype="float32")
        if len(audio_np.shape) > 1:
            audio_np = audio_np[:, 0]
    except Exception:
        audio_np = None

    if audio_np is None or len(audio_np) == 0:
        return ""

    from core.voice.stt import WhisperSTT
    stt = WhisperSTT()
    return stt.transcribe(audio_np, sr)


def _llm_respond(text: str) -> str:
    import httpx
    from core.config import CONFIG
    ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
    try:
        r = httpx.post(
            f"{ollama_host}/api/generate",
            json={"model": "llama3.2:latest", "prompt": text, "stream": False},
            timeout=30.0,
        )
        if r.status_code == 200:
            return r.json().get("response", "Done.")
    except Exception as e:
        logger.warning(f"[VECTOR][voice_ws] LLM error: {e}")
    return "Done."


def _tts_to_wav(text: str) -> bytes | None:
    from core.voice.tts import VoiceTTS
    tts = VoiceTTS()
    if not tts._kokoro_ok:
        logger.warning("[VECTOR][voice_ws] Kokoro not available, skipping TTS")
        return None
    try:
        from kokoro_onnx import Kokoro
        voice = "bf_emma"
        samples, sample_rate = tts._kokoro.create(text, voice=voice, speed=0.85)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV")
        return buf.getvalue()
    except Exception as e:
        logger.error(f"[VECTOR][voice_ws] TTS failed: {e}")
        return None
```

- [ ] Write file
- [ ] Run: `python -c "from core.api.routers.voice_ws import router; print('OK')"` → expect OK

---

### Task 2: Register router in app.py

**File:** Modify `core/api/app.py`

- [ ] Add `voice_ws` to imports
- [ ] Add `app.include_router(voice_ws.router)`
- [ ] Verify no conflicts

---

### Task 3: Frontend VoiceInput WebSocket path

**File:** Modify `core/ui/dashboard/src/components/VoiceInput.tsx`

Replace existing `POST /voice` REST call with WebSocket flow:
- On mic press: `new WebSocket("ws://host/ws/voice/stream")`
- `MediaRecorder.ondataavailable` → `ws.send(blob)` (binary)
- On mic release: `ws.send(JSON.stringify({type: "end"}))`
- On `transcript` message: call `onResult(transcript, "")`
- On `response` message: update command response display
- On `audio` message: decode base64 → play via AudioContext
- On `done` message: close WebSocket

- [ ] Implement
- [ ] Build: `cd core/ui/dashboard && npx vite build` → expect PASS
