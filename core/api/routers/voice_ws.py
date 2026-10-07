"""WebSocket endpoint for streaming voice — push-to-talk flow.

Protocol:
  Client -> Server: binary audio chunks (webm/opus)
  Client -> Server: {"type": "end"}
  Server -> Client: {"type": "transcript", "text": "..."}
  Server -> Client: {"type": "response_partial", "text": "..."}  (streaming path, grows)
  Server -> Client: {"type": "audio", "data": "<base64 wav>", "sample_rate": 24000, "seq": N}
                    (streaming path: ONE complete WAV per SENTENCE, sent while the
                     LLM is still generating - client queues and plays sequentially)
  Server -> Client: {"type": "response", "text": "..."}          (final full text)
  Server -> Client: {"type": "done"}
  Close

Response resolution order (docs/REALTIME_CONVERSATION_DESIGN.md Phase 1):
  1. rules-engine bypass            - instant, no LLM
  2. streaming LLM + sentence TTS   - first audio after first sentence
  3. batch fallback                 - original whole-response behavior
"""

import sys

__all__ = [
    "router",
    "voice_stream",
]

import asyncio
import base64
import io
import json

import numpy as np
import soundfile as sf
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter(prefix="/ws/voice", tags=["voice"])


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()

    # RR-3.7C (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
    # RR3_7C_FINAL_INGRESS_AUTHORIZATION_FREEZE_REPORT.md): this endpoint had
    # ZERO authentication -- confirmed via direct Starlette source read that
    # `app.middleware("http")`-registered middleware (including the app's own
    # auth_middleware) unconditionally bypasses every WebSocket connection
    # (BaseHTTPMiddleware.__call__: `if scope["type"] != "http": await
    # self.app(...); return`), so the global HTTP auth gate never runs here.
    # /ws/command (core/api/routers/websocket.py::vector_ws) already
    # established the correct, canonical compensating pattern for this exact
    # Starlette limitation: an explicit require_auth_handshake() call inside
    # the handler itself. Reused verbatim here -- no new auth mechanism.
    #
    # This mattered beyond generic unauthenticated access: the "Fast path 0"
    # branch below (try_device_action()) hardcodes
    # `proposed_by="api_command"` on the resulting PermissionGateway Action --
    # the exact identity permission_gateway.py's RED tier treats as
    # "typed/spoken by the authenticated owner, the command IS the
    # confirmation" for RED_INTERACTIVE_TOOLS (which includes "launch_app",
    # the one action_type reachable here). Combined with zero authentication,
    # any network client that could open this socket could cause a real,
    # unconfirmed PCController.launch_app() call (opening spotify/chrome/
    # firefox/vscode/obsidian/notepad/calc/terminal/task_manager on the
    # owner's own machine) with no owner involvement at all.
    #
    # Both real frontend clients already send the matching handshake message
    # on connect (frontend/js/vector-core.js's openWS() passes `tok` for the
    # 'voice' socket, frontend/js/voice_duplex.js sends it directly) -- this
    # was a half-wired gap, not a missing frontend feature. This fix does not
    # change client-visible behavior for an already-correctly-configured
    # client.
    from core.api.routers.websocket import require_auth_handshake
    if not await require_auth_handshake(websocket):
        logger.warning("[VECTOR][voice_ws] connection rejected — auth handshake failed")
        return

    chunks: list[bytes] = []
    logger.info("[VECTOR][voice_ws] Client connected")

    # broadcast_event is imported lazily (avoids a circular import with the
    # websocket router) and shared across this handler's dashboard broadcasts.
    try:
        from core.api.routers.websocket import broadcast_event  # type: ignore
    except Exception:
        broadcast_event = None  # type: ignore

    # Helper to broadcast orb FSM state to every connected dashboard.
    # Never raises (RULE 2); logs are debug-level to avoid log spam.
    async def _orb(state: str) -> None:
        try:
            from core.api.routers.websocket import broadcast_event  # type: ignore
            await broadcast_event({"type": "orb_state", "state": state})
        except Exception as _bc_err:
            logger.warning(f"[VECTOR][voice_ws] orb_state broadcast skipped: {_bc_err}")

    try:
        await _orb("listening")  # connection open = mic active
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                # Client dropped — surface as a clean disconnect instead of
                # looping back into receive() (which raises "Cannot call receive
                # once a disconnect message has been received").
                raise WebSocketDisconnect(raw.get("code", 1000))
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

        # ── Fast path 0: direct device command ("open spotify") — executes
        # through the permission gateway, same as the typed command bar ─────
        try:
            from core.voice.realtime import try_device_action
            device_reply = await try_device_action(transcript)
        except Exception as _da_err:
            logger.debug(f"[VECTOR][voice_ws] device action skipped: {_da_err}")
            device_reply = None
        if device_reply:
            await websocket.send_json({"type": "response", "text": device_reply})
            await _orb("speaking")
            wav = await loop.run_in_executor(None, _tts_to_wav, device_reply, 0.85)
            if wav:
                await _send_wav(websocket, wav, seq=0)
            await websocket.send_json({"type": "done"})
            await _orb("idle")
            return

        # ── Fast path 1: rules-engine bypass — instant answer, no LLM ──────
        bypass_text = await loop.run_in_executor(None, _rules_bypass, transcript)
        if bypass_text:
            await websocket.send_json({"type": "response", "text": bypass_text})
            await _orb("speaking")
            wav = await loop.run_in_executor(None, _tts_to_wav, bypass_text, 0.85)
            if wav:
                await _send_wav(websocket, wav, seq=0)
            await websocket.send_json({"type": "done"})
            await _orb("idle")
            return

        # ── Fast path 2: streaming LLM → sentence-streamed TTS ─────────────
        # First audio leaves as soon as the FIRST sentence is complete,
        # while later sentences are still being generated (REALTIME_CONVERSATION_DESIGN.md Phase 1).
        response_text = ""
        tts_speed = 0.85
        try:
            response_text, tts_speed = await _stream_respond(websocket, transcript, _orb)
        except Exception as _stream_err:
            logger.warning(f"[VECTOR][voice_ws] streaming path failed, falling back to batch: {_stream_err}")

        streamed = bool(response_text)
        if not streamed:
            # Batch fallback — original behavior
            response_text, tts_speed = await loop.run_in_executor(None, _llm_respond_with_personality, transcript)
            await websocket.send_json({"type": "response", "text": response_text})

        # Broadcast voice response as ui_event for dashboard widgets
        try:
            await broadcast_event({"type": "ui_event", "action_type": "widget_open", "params": {"id": "text", "content": response_text, "title": "Response"}})
        except Exception as _bc_err:
            logger.debug(f"[VECTOR][voice_ws] ui_event broadcast skipped: {_bc_err}")

        # Check for location intent and trigger map widget
        intent = await _parse_intent(transcript)
        if intent:
            try:
                await broadcast_event({"type": "ui_event", **intent})
                logger.info(f"[VECTOR][voice_ws] Intent detected: {intent['action']} -> {intent['params']['query']}")
            except Exception as _int_err:
                logger.warning(f"[VECTOR][voice_ws] Intent broadcast failed: {_int_err}")

        if not streamed:
            # Batch fallback synthesizes the whole response in one go.
            # (Streaming path already sent per-sentence audio inside _stream_respond.)
            await _orb("speaking")
            wav_bytes = await loop.run_in_executor(None, _tts_to_wav, response_text, tts_speed)
            if wav_bytes:
                await _send_wav(websocket, wav_bytes, seq=0)

        await websocket.send_json({"type": "done"})
        await _orb("idle")

    except WebSocketDisconnect:
        logger.info("[VECTOR][voice_ws] Client disconnected")
    except Exception as e:
        logger.error(f"[VECTOR][voice_ws] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
    finally:
        try:
            await websocket.close()
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)


@router.websocket("/duplex")
async def voice_duplex(websocket: WebSocket):
    """Full-duplex realtime conversation (design Phases 2-5).

    Client -> Server: binary frames = int16 mono 16kHz PCM (continuous)
                      {"type":"playing","value":bool}  — echo guard
                      {"type":"control","action":"end_session"}
    Server -> Client: state / partial_transcript / final_transcript /
                      response_partial / response / audio / stop_audio /
                      action_ack / action_result / proactive / done
    """
    await websocket.accept()

    # RR-3.7C: same reasoning and same reused mechanism as voice_stream()
    # above -- this endpoint also had zero network-level authentication
    # (confirmed: app.middleware("http")-registered auth_middleware never
    # runs for WebSocket connections). frontend/js/voice_duplex.js already
    # sends the matching `{"auth": "Bearer <key>"}` handshake message on
    # connect (line 134) -- this was a half-wired gap on the server side
    # only, not a missing frontend feature.
    from core.api.routers.websocket import require_auth_handshake
    if not await require_auth_handshake(websocket):
        logger.warning("[VECTOR][voice_ws] duplex connection rejected — auth handshake failed")
        return

    logger.info("[VECTOR][voice_ws] duplex client connected")

    async def _orb(state: str) -> None:
        try:
            from core.api.routers.websocket import broadcast_event  # type: ignore
            await broadcast_event({"type": "orb_state", "state": state})
        except Exception as _e:
            logger.debug(f"[VECTOR][voice_ws] orb broadcast skipped: {_e}")

    from core.voice.realtime import RealtimeConversation
    rc = RealtimeConversation(send_json=websocket.send_json, orb=_orb)
    await rc.start()
    try:
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                break
            if raw.get("type") != "websocket.receive":
                continue
            if "bytes" in raw and raw["bytes"]:
                await rc.feed_pcm(raw["bytes"])
            elif "text" in raw:
                try:
                    msg = json.loads(raw["text"])
                except json.JSONDecodeError:
                    continue
                mtype = msg.get("type", "")
                if mtype == "playing":
                    rc.set_client_playing(bool(msg.get("value")))
                elif mtype == "control" and msg.get("action") == "end_session":
                    break
                # auth handshake messages ({"auth": ...}) are accepted silently
    except WebSocketDisconnect:
        logger.info("[VECTOR][voice_ws] duplex client disconnected")
    except Exception as e:
        logger.error(f"[VECTOR][voice_ws] duplex error: {e}")
    finally:
        await rc.stop()
        try:
            await websocket.close()
        except Exception as e:
            logger.warning(f"[VECTOR][voice_ws] close failed: {e}")


def _parse_intent(text: str) -> dict | None:
    """Extract location queries from natural voice commands.
    
    Matches: 'show me Paris', 'show Paris on the map', 'where is Tokyo?'
    """
    text_lower = text.lower().strip()
    
    # Pattern 1: "show me <location>"
    if "show me" in text_lower:
        parts = text_lower.split("show me")
        if len(parts) > 1:
            location = parts[1].strip().rstrip(".?!")
            return {"action": "widget_show_location", "params": {"query": location}}
    
    # Pattern 2: "where is <location>"
    if "where is" in text_lower or "where's" in text_lower:
        for prefix in ["where is", "where's"]:
            parts = text_lower.split(prefix)
            if len(parts) > 1:
                location = parts[1].strip().rstrip(".?!")
                return {"action": "widget_show_location", "params": {"query": location}}
    
    # Pattern 3: "map of <location>"
    if "map of" in text_lower:
        parts = text_lower.split("map of")
        if len(parts) > 1:
            location = parts[1].strip().rstrip(".?!")
            return {"action": "widget_show_location", "params": {"query": location}}
    
    # Pattern 4: "lock HUD" or "unlock HUD"
    if "lock hud" in text_lower or "unlock hud" in text_lower:
        locked = "lock" in text_lower and "unlock" not in text_lower
        return {"action": "hud_lock_toggle", "params": {"locked": locked}}
    
    # Pattern 5: "hide" or "show" (generic hide/show commands)
    if text_lower in ("hide", "hide hud", "hide interface"):
        return {"action": "hud_lock_toggle", "params": {"locked": True}}
    if text_lower in ("show", "show hud", "show interface"):
        return {"action": "hud_lock_toggle", "params": {"locked": False}}
    
    return None


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


async def _send_wav(websocket, wav_bytes: bytes, seq: int = 0) -> None:
    """Send one complete WAV as a single base64 'audio' message.

    One message per WAV (not 32KB chunks) so the client can decodeAudioData()
    each message independently — headerless WAV fragments can't be decoded.
    Localhost WS handles MB-scale frames fine.
    """
    await websocket.send_json({
        "type": "audio",
        "data": base64.b64encode(wav_bytes).decode(),
        "sample_rate": 24000,
        "seq": seq,
    })


def _rules_bypass(text: str) -> str:
    """Instant no-LLM answer for simple queries via the rules engine. Returns '' on miss."""
    try:
        from core.security.rules_engine import get_rules_engine
        engine = get_rules_engine()
        rule = engine.match(text)
        if rule:
            answer = engine.execute_rule(rule, {})
            logger.info("[VECTOR][voice_ws] rules bypass '{}' answered without LLM", rule.category)
            try:
                from core.memory.episodic import EpisodicMemory
                EpisodicMemory().store(
                    event_type="bypass_response",
                    content=f"Q: {text} | A: {answer}",
                    tags=["bypass", rule.category, "voice"],
                    source="voice_ws",
                )
            except Exception as _ep_err:
                logger.debug(f"[VECTOR][voice_ws] bypass episodic store skipped: {_ep_err}")
            return answer or ""
    except Exception as e:
        logger.debug(f"[VECTOR][voice_ws] rules bypass unavailable: {e}")
    return ""


_PERSONALITY_ENGINE = None  # cached — PersonalityEngine construction is not free


def _get_personality():
    """Return (system_prompt_fn, speed_fn) personality helpers, cached engine."""
    global _PERSONALITY_ENGINE
    from core.config import CONFIG
    if not CONFIG.get("personality", {}).get("enabled", True):
        return None
    if _PERSONALITY_ENGINE is None:
        try:
            from core.personality import PersonalityEngine
            _PERSONALITY_ENGINE = PersonalityEngine()
        except Exception as e:
            logger.warning(f"[VECTOR][voice_ws] personality init failed: {e}")
            return None
    return _PERSONALITY_ENGINE


_SENTENCE_ENDS = (".", "!", "?", "\n")


def _pop_sentence(buf: str, max_chars: int = 220) -> tuple[str, str]:
    """Split off the first complete sentence from buf. Returns (sentence, rest).

    A sentence is complete at . ! ? or newline followed by a space/end, or when
    buf exceeds max_chars (forced cut at last space to keep TTS chunks bounded).
    Returns ('', buf) when no complete sentence is available yet.
    """
    for i, ch in enumerate(buf):
        if ch in _SENTENCE_ENDS:
            # avoid cutting decimals like "3.14" — require boundary or end
            nxt = buf[i + 1:i + 2]
            if ch == "." and nxt.isdigit():
                continue
            return buf[:i + 1].strip(), buf[i + 1:]
    if len(buf) > max_chars:
        cut = buf.rfind(" ", 0, max_chars)
        cut = cut if cut > 0 else max_chars
        return buf[:cut].strip(), buf[cut:]
    return "", buf


async def _stream_respond(websocket, text: str, orb) -> tuple[str, float]:
    """Streaming pipeline: Ollama tokens → sentence cuts → per-sentence Kokoro TTS.

    First audio is sent as soon as the first sentence completes, while the LLM
    is still generating. Sentence N+1 synthesizes while N plays client-side.
    Returns (full_response_text, tts_speed); raises on transport failure so the
    caller can fall back to the batch path.
    """
    import httpx
    from core.config import CONFIG

    ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
    model = CONFIG.get("models", {}).get("focus", "vector-focus")
    speed = 0.85

    pe = _get_personality()
    prompt = text
    system_prompt = ""
    from core.loop.context_engine import ContextEngine
    hydration = ContextEngine().session_hydration_prompt()
    if pe is not None:
        try:
            result = pe.process(text)
            system_prompt = result.get("system_prompt", "")
            tone = result.get("tone_config")
            if tone:
                speed = tone.speed
            if system_prompt:
                prompt = f"{hydration}\n\n{system_prompt}\n\nUser: {text}"
        except Exception as e:
            logger.debug(f"[VECTOR][voice_ws] personality process skipped: {e}")
    # 2026-07-29 CORRECTION (issue #37): `core.personality` DOES exist and
    # `pe.process()` normally succeeds with a real system_prompt built from
    # vector.json's `rules` array. The actual bug was that vector.json never
    # had an English-only or spoken-text-safety rule — fixed at the source,
    # so every consumer of PersonalityEngine now gets it automatically. This
    # stays as a defense-in-depth fallback for when personality is
    # disabled/unavailable.
    if not system_prompt:
        try:
            from core.voice.ambient_listener import VECTOR_PERSONALITY
            system_prompt = VECTOR_PERSONALITY
        except Exception as e:
            logger.warning(f"[VECTOR][voice_ws] VECTOR_PERSONALITY fallback failed: {e}")
            system_prompt = (
                "You are VECTOR, Arghyadeep's personal AI assistant. Always "
                "respond in English regardless of what language the user's "
                "message is written in. This reply will be read aloud by "
                "text-to-speech — plain natural spoken sentences only, no "
                "markdown, no spelled-out punctuation names."
            )
        prompt = f"{hydration}\n\n{system_prompt}\n\nUser: {text}"

    loop = asyncio.get_event_loop()
    full_text = ""
    buf = ""
    seq = 0
    speaking = False
    # KNOWN_ISSUES #4 (2026-07-30): this pipeline is genuinely incremental —
    # sentence 1 is synthesized and sent while the LLM is still generating
    # sentence 2+, so buffering the WHOLE response first (like realtime.py's
    # _stream_chat, which turned out to already collect the full text before
    # any TTS) would defeat the entire point of this path. Cheaper
    # compromise: gate only the FIRST sentence on the same deterministic
    # Devanagari check text chat (#35) already has. If it fails, raise here
    # (before any audio is sent) so the caller's existing except-block falls
    # back to the batch path below, which now carries its own full
    # translate-retry backstop — one sentence of extra latency, not the
    # whole reply, and still a hard guarantee overall.
    checked_first_sentence = False

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{ollama_host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": True,
                  "keep_alive": -1},  # keep model warm — kills cold-start TTFT
        ) as r:
            if r.status_code != 200:
                raise RuntimeError(f"ollama status {r.status_code}")
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = payload.get("response", "")
                if token:
                    full_text += token
                    buf += token
                    # surface partial text to HUD captions as it grows
                    await websocket.send_json({"type": "response_partial", "text": full_text})
                    sentence, buf = _pop_sentence(buf)
                    if sentence:
                        if not checked_first_sentence:
                            checked_first_sentence = True
                            from core.city.governor import _is_mostly_devanagari
                            if _is_mostly_devanagari(sentence):
                                raise RuntimeError(
                                    "first sentence failed English-only policy check"
                                )
                        if not speaking:
                            speaking = True
                            await orb("speaking")
                        wav = await loop.run_in_executor(None, _tts_to_wav, sentence, speed)
                        if wav:
                            await _send_wav(websocket, wav, seq=seq)
                            seq += 1
                if payload.get("done"):
                    break

    # flush whatever is left in the buffer (last partial sentence)
    tail = buf.strip()
    if tail:
        wav = await loop.run_in_executor(None, _tts_to_wav, tail, speed)
        if wav:
            await _send_wav(websocket, wav, seq=seq)

    full_text = full_text.strip()
    if full_text:
        # final full response for chat history / widgets (existing frontend contract)
        await websocket.send_json({"type": "response", "text": full_text})
    return full_text, speed


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
        system_prompt = ""
        if personality_enabled:
            try:
                from core.personality import PersonalityEngine
                pe = PersonalityEngine()
                personality_result = pe.process(text)
                system_prompt = personality_result.get("system_prompt", "")
                tone_config = personality_result.get("tone_config")
                if tone_config:
                    speed = tone_config.speed
            except Exception as e:
                logger.warning(f"[VECTOR][voice_ws] personality init failed: {e}")
        # 2026-07-29 CORRECTION (issue #37): see _stream_respond() above —
        # `core.personality` works; the real fix lives in vector.json's rules.
        # This stays as a defense-in-depth fallback.
        if not system_prompt and personality_enabled:
            try:
                from core.voice.ambient_listener import VECTOR_PERSONALITY
                system_prompt = VECTOR_PERSONALITY
            except Exception as e:
                logger.warning(f"[VECTOR][voice_ws] VECTOR_PERSONALITY fallback failed: {e}")
                system_prompt = (
                    "You are VECTOR, Arghyadeep's personal AI assistant. Always "
                    "respond in English regardless of what language the user's "
                    "message is written in. This reply will be read aloud by "
                    "text-to-speech — plain natural spoken sentences only, no "
                    "markdown, no spelled-out punctuation names."
                )
        prompt = f"{system_prompt}\n\nUser: {text}" if system_prompt else text
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        prompt = f"{hydration}\n\n{prompt}"

        r = httpx.post(
            f"{ollama_host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=30.0,
        )
        if r.status_code == 200:
            response = r.json().get("response", "Done.")
            # KNOWN_ISSUES #4 (2026-07-30): this is the batch fallback that
            # both the streaming path (on a first-sentence policy failure)
            # and the caller's own transport-error handling land on — give
            # it the same hard English-only guarantee text chat (#35) has,
            # since a fully-collected response (stream=False, same as here)
            # is exactly the shape that backstop was built for. Runs in this
            # executor thread (no existing event loop), so asyncio.run() is
            # safe here.
            try:
                from core.city.governor import _ensure_english_response
                response = asyncio.run(_ensure_english_response(response))
            except Exception as e:
                logger.warning(f"[VECTOR][voice_ws] English-only backstop skipped: {e}")
            if pe is not None:
                try:
                    validation = pe.validate_response(response, text)
                    if validation.get("rewritten"):
                        response = validation["rewritten"]
                        logger.debug("[VECTOR][voice_ws] response rewritten by consistency enforcer")
                except Exception as e:
                    logger.warning(f"[VECTOR][voice_ws] consistency check skipped: {e}")
    except Exception as e:
        logger.warning(f"[VECTOR][voice_ws] LLM error: {e}")
    return response, speed


def _tts_to_wav(text: str, speed: float | None = None) -> bytes | None:
    from core.voice.tts import VoiceTTS, _voice_for, sanitize_for_speech
    # 2026-07-28: calls Kokoro directly, bypassing VoiceTTS.speak()'s own
    # sanitization — see core/voice/tts.py's sanitize_for_speech() docstring.
    text = sanitize_for_speech(text)
    if not text:
        return None
    tts = VoiceTTS()
    if not tts._kokoro_ok:
        logger.warning("[VECTOR][voice_ws] Kokoro not available, skipping TTS")
        return None
    try:
        # Config-driven voice (bm_george) — was hardcoded bf_emma, which kept
        # the HUD/browser voice FEMALE after the main path went male (2026-07-15).
        voice = _voice_for("en")
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
