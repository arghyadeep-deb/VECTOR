"""WebSocket endpoint for streaming voice — push-to-talk flow.

Protocol:
  Client -> Server: binary audio chunks (webm/opus)
  Client -> Server: {"type": "end"}
  Server -> Client: {"type": "transcript", "text": "..."}
  Server -> Client: {"type": "response", "text": "..."}
  Server -> Client: {"type": "audio", "data": "<base64 wav chunk>", "sample_rate": 24000}
  Server -> Client: {"type": "done"}
  Close
"""

import sys
import asyncio
import base64
import io
import json
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

    # Helper to broadcast orb FSM state to every connected dashboard.
    # Never raises (RULE 2); logs are debug-level to avoid log spam.
    async def _orb(state: str) -> None:
        try:
            from core.api.routers.websocket import broadcast_event  # type: ignore
            await broadcast_event({"type": "orb_state", "state": state})
        except Exception as _bc_err:
            logger.debug(f"[VECTOR][voice_ws] orb_state broadcast skipped: {_bc_err}")

    try:
        await _orb("listening")  # connection open = mic active
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
            await _orb("idle")
            await websocket.close()
            return

        await _orb("processing")
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(None, _transcribe, chunks)
        if not transcript:
            await websocket.send_json({"type": "error", "text": "Could not transcribe audio"})
            await _orb("idle")
            await websocket.close()
            return
        await websocket.send_json({"type": "transcript", "text": transcript})
        logger.info(f"[VECTOR][voice_ws] Transcript: {transcript}")

        response_text, tts_speed = await loop.run_in_executor(None, _llm_respond_with_personality, transcript)
        await websocket.send_json({"type": "response", "text": response_text})

        await _orb("speaking")
        wav_bytes = await loop.run_in_executor(None, _tts_to_wav, response_text, tts_speed)
        if wav_bytes:
            chunk_size = 32000
            for i in range(0, len(wav_bytes), chunk_size):
                chunk = wav_bytes[i:i + chunk_size]
                await websocket.send_json({
                    "type": "audio",
                    "data": base64.b64encode(chunk).decode(),
                    "sample_rate": 24000,
                })
                await asyncio.sleep(0.1)

        await websocket.send_json({"type": "done"})
        await _orb("idle")

    except WebSocketDisconnect:
        logger.info("[VECTOR][voice_ws] Client disconnected")
    except Exception as e:
        logger.error(f"[VECTOR][voice_ws] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)
    finally:
        try:
            await websocket.close()
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)


def _transcribe(chunks: list[bytes]) -> str:
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


def _llm_respond_with_personality(text: str) -> tuple[str, float]:
    import httpx
    from core.config import CONFIG
    ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
    speed = 0.85
    response = "Done."
    try:
        model = CONFIG.get("models", {}).get("focus", "vector-focus")
        personality_enabled = CONFIG.get("personality", {}).get("enabled", True)
        pe = None
        if personality_enabled:
            try:
                from core.personality import PersonalityEngine
                pe = PersonalityEngine()
                personality_result = pe.process(text)
                system_prompt = personality_result.get("system_prompt", "")
                tone_config = personality_result.get("tone_config")
                if tone_config:
                    speed = tone_config.speed
                prompt = f"{system_prompt}\n\nUser: {text}" if system_prompt else text
            except Exception as e:
                logger.debug(f"[VECTOR][voice_ws] personality init failed: {e}")
                prompt = text
        else:
            prompt = text

        r = httpx.post(
            f"{ollama_host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=30.0,
        )
        if r.status_code == 200:
            response = r.json().get("response", "Done.")
            if pe is not None:
                try:
                    validation = pe.validate_response(response, text)
                    if validation.get("rewritten"):
                        response = validation["rewritten"]
                        logger.debug("[VECTOR][voice_ws] response rewritten by consistency enforcer")
                except Exception as e:
                    logger.debug(f"[VECTOR][voice_ws] consistency check skipped: {e}")
    except Exception as e:
        logger.warning(f"[VECTOR][voice_ws] LLM error: {e}")
    return response, speed


def _tts_to_wav(text: str, speed: float | None = None) -> bytes | None:
    from core.voice.tts import VoiceTTS
    tts = VoiceTTS()
    if not tts._kokoro_ok:
        logger.warning("[VECTOR][voice_ws] Kokoro not available, skipping TTS")
        return None
    try:
        voice = "bf_emma"
        tts_speed = speed if speed is not None else 0.85
        samples, sample_rate = tts._kokoro.create(text, voice=voice, speed=tts_speed)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV")
        return buf.getvalue()
    except Exception as e:
        logger.error(f"[VECTOR][voice_ws] TTS failed: {e}")
        return None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
