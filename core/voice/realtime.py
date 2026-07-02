"""RealtimeConversation — full-duplex voice orchestrator (design Phases 2-5).

Implements docs/REALTIME_CONVERSATION_DESIGN.md on top of existing modules:
  ConversationManager (FSM)  · VoiceActivityDetector (endpointing + barge-in)
  WhisperSTT/FasterWhisperSTT (partial + final transcripts)
  VoiceTTS/Kokoro (per-sentence synthesis) · rules_engine (instant bypass)
  Governor (action handoff, RULE 3 intact)  · nudge_engine (proactive speech)
  presence.allow_proactive (DND / reactive-mode gate)

Transport-agnostic: the WS router passes a `send_json` coroutine; everything
else is callbacks. One instance per connected duplex client.

Turn lifecycle (§6 of the design):
  LISTENING -> USER_SPEAKING (VAD speech) -> partial decodes every ~600ms
  -> endpoint at `endpoint_silence_ms` of silence -> final transcript
  -> PROCESSING (rules bypass | intent classify) ->
       chat:   streaming LLM -> sentence TTS  (VECTOR_SPEAKING)
       action: spoken ack -> governor.dispatch() async -> completion spoken
  -> LISTENING.  Barge-in (§7): speech while VECTOR_SPEAKING cancels the
  speak task, sends {"type":"stop_audio"}, returns to LISTENING.
"""

from __future__ import annotations

__all__ = ["RealtimeConversation"]

import asyncio
import base64
import io
import json
import re
import time

import numpy as np
from loguru import logger

from core.config import CONFIG


# ── sentence streaming helpers (shared with the legacy push-to-talk path) ────

_SENTENCE_ENDS = (".", "!", "?", "\n")


def pop_sentence(buf: str, max_chars: int = 220) -> tuple[str, str]:
    """Split off the first complete sentence from buf. Returns (sentence, rest)."""
    for i, ch in enumerate(buf):
        if ch in _SENTENCE_ENDS:
            nxt = buf[i + 1:i + 2]
            if ch == "." and nxt.isdigit():
                continue
            return buf[:i + 1].strip(), buf[i + 1:]
    if len(buf) > max_chars:
        cut = buf.rfind(" ", 0, max_chars)
        cut = cut if cut > 0 else max_chars
        return buf[:cut].strip(), buf[cut:]
    return "", buf


def tts_wav(text: str, speed: float = 0.85) -> bytes | None:
    """Synthesize one sentence with Kokoro -> WAV bytes. Never raises."""
    try:
        import soundfile as sf
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        if not tts._kokoro_ok:
            return None
        voice = CONFIG.get("voice", {}).get("kokoro_voice", "bf_emma")
        samples, sample_rate = tts._kokoro.create(text, voice=voice, speed=speed)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV")
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[VECTOR][realtime] tts failed: {e}")
        return None


# ── Phase 4: intent classification (chat vs action) ──────────────────────────
# Phrases that mean "go do something" route to the governor; everything else
# is conversational and answered directly by the streaming LLM.

_ACTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(venture|side.?hustle|business idea)\b.*\b(pipeline|scan|search|run)\b", "venture_pipeline"),
    (r"\brun\b.*\bventure pipeline\b", "venture_pipeline"),
    (r"\b(mine|scan)\b.*\b(reddit|social|problems)\b", "mine_social"),
    (r"\b(check|show)\b.*\battendance\b", "check_attendance"),
    (r"\bgit (status|log)\b", "git_status"),
    (r"\b(commit|push)\b.*\b(code|changes|repo)\b", "git_status"),
    (r"\b(write|fix|refactor|debug|implement)\b.*\b(code|bug|function|module|test)\b", "code_task"),
    (r"\b(research|investigate|deep.?dive)\b", "daily_digest"),
    (r"\b(search|find)\b.*\b(arxiv|papers?)\b", "search_arxiv"),
    (r"\b(search|look up|google)\b", "search_web"),
    (r"\b(monitor|watch|track)\b", "monitor"),
    (r"\b(scan|audit)\b.*\b(security|repo|system)\b", "security_scan"),
    (r"\bfinance report\b|\bmonthly report\b", "monthly_report"),
    (r"\b(schedule|remind me)\b", "schedule_task"),
    (r"\b(run|execute)\b.*\b(backtest|strategy)\b", "backtest"),
    (r"\b(summarize|digest)\b.*\b(news|feeds?)\b", "daily_digest"),
]


def classify_intent(text: str) -> str | None:
    """Return a governor task type for action-like utterances, else None (chat)."""
    low = text.lower()
    for pattern, task_type in _ACTION_PATTERNS:
        if re.search(pattern, low):
            return task_type
    return None


def classify_intent_llm(text: str) -> str | None:
    """LLM chat-vs-action fallback when the regex patterns miss.

    Asks the ambient model (resident, fast) whether the utterance is a command.
    Returns a short natural-language task type — Governor.route_task() accepts
    natural language (keyword map + its own LLM district classifier) — or None
    for conversation / any failure. Gated by CONFIG voice.llm_intent_fallback.
    """
    try:
        from core.config import CONFIG
        voice_cfg = CONFIG.get("voice", {})
        if not voice_cfg.get("llm_intent_fallback", True):
            return None
        from core.inference.ollama_safe import chat
        prompt = (
            "You are VECTOR's voice intent gate. Decide if the utterance below is a "
            "COMMAND asking the assistant to perform work (run, search, scan, build, "
            "monitor, schedule, report, control something), or just conversation.\n"
            "Reply with exactly one line:\n"
            "CHAT\n"
            "or\n"
            "ACTION: <3-6 word task description>\n\n"
            f'Utterance: "{text}"'
        )
        result = chat(
            model=CONFIG["models"]["ambient"],
            messages=[{"role": "user", "content": prompt}],
            timeout=float(voice_cfg.get("llm_intent_timeout_sec", 4.0)),
            temperature=0.0,
        ).strip()
        if not result:
            return None
        first_line = result.splitlines()[0].strip()
        if first_line.upper().startswith("ACTION:"):
            task_type = first_line[len("ACTION:"):].strip().strip('."')
            # Sanity clamp — a task type is a short phrase, not an essay.
            if 0 < len(task_type) <= 80:
                logger.info(f"[VECTOR][realtime] LLM intent: ACTION '{task_type}' <- {text[:60]!r}")
                return task_type
        return None
    except Exception as e:
        logger.warning(f"[VECTOR][realtime] LLM intent fallback failed (treating as chat): {e}")
        return None


def _in_quiet_hours(now_minutes: int, spec: str) -> bool:
    """spec '23:30-07:00' (may wrap midnight). Empty spec -> never quiet."""
    try:
        if not spec or "-" not in spec:
            return False
        a, b = spec.split("-", 1)
        ah, am = (int(x) for x in a.strip().split(":"))
        bh, bm = (int(x) for x in b.strip().split(":"))
        start, end = ah * 60 + am, bh * 60 + bm
        if start == end:
            return False
        if start < end:
            return start <= now_minutes < end
        return now_minutes >= start or now_minutes < end  # wraps midnight
    except Exception:
        return False


class RealtimeConversation:
    """One full-duplex voice session. Feed PCM in; JSON events come out."""

    def __init__(self, send_json, orb=None):
        self._send = send_json                  # async callable(dict)
        self._orb = orb                         # async callable(str) | None
        voice_cfg = CONFIG.get("voice", {})
        self._sr = 16000
        self._endpoint_ms = int(voice_cfg.get("endpoint_silence_ms", 280))
        self._bargein = bool(voice_cfg.get("bargein_enabled", True))
        self._bargein_debounce_ms = int(voice_cfg.get("bargein_debounce_ms", 120))
        self._partial_interval = float(voice_cfg.get("partial_interval_sec", 0.6))
        self._proactive = bool(voice_cfg.get("proactive_speech", True))
        self._proactive_min_priority = float(voice_cfg.get("proactive_min_priority", 0.7))
        self._quiet_hours = str(voice_cfg.get("quiet_hours", "00:00-08:00"))

        from core.voice.conversation_manager import ConversationManager
        self._conv = ConversationManager()

        from core.voice.vad import VoiceActivityDetector
        self._vad = VoiceActivityDetector()
        self._vad._min_silence_ms = self._endpoint_ms      # realtime endpointing
        self._base_vad_threshold = self._vad._energy_threshold

        self._stt = None                        # lazy — model load is heavy
        self._utterance: list[np.ndarray] = []
        self._utterance_started = 0.0
        self._last_partial = 0.0
        self._partial_busy = False
        self._client_playing = False            # echo guard flag from client
        self._bargein_speech_ms = 0.0
        self._speak_task: asyncio.Task | None = None
        self._cancel_speak = asyncio.Event()
        self._nudge_unsub = None
        self._closed = False
        self._speaker_owner = True   # last utterance verified as owner?

        # Phase 6 — session idle timeout → IDLE, wake word resumes (design §6)
        self._conversation_timeout = float(voice_cfg.get("conversation_timeout_sec", 30))
        self._last_activity = time.monotonic()
        self._wake_detector = None
        self._wake_failed = False
        self._wake_buffer: list[np.ndarray] = []
        self._wake_buffer_ms = 0.0
        self._wake_busy = False

    # ── session ──────────────────────────────────────────────────────────────

    async def start(self, user_id: str = "owner") -> None:
        self._conv.start_session(user_id)
        self._conv.transition("LISTENING")
        await self._state("LISTENING")
        if self._proactive:
            self._subscribe_nudges()
        logger.info("[VECTOR][realtime] session started")

    async def stop(self) -> None:
        self._closed = True
        await self._cancel_speaking()
        if self._nudge_unsub:
            try:
                self._nudge_unsub()
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
            self._nudge_unsub = None
        self._conv.end_session()
        logger.info("[VECTOR][realtime] session ended")

    def set_client_playing(self, playing: bool) -> None:
        """Echo guard: client reports speaker playback; raise VAD threshold."""
        self._client_playing = playing
        self._vad._energy_threshold = (
            self._base_vad_threshold * 2.5 if playing else self._base_vad_threshold
        )

    # ── audio in (Phase 2 + Phase 3) ─────────────────────────────────────────

    async def feed_pcm(self, pcm_bytes: bytes) -> None:
        """One int16 mono 16kHz frame from the client (~20-130ms)."""
        if self._closed or not pcm_bytes:
            return
        frame = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        frame_ms = len(frame) / self._sr * 1000.0
        is_speech = self._vad.is_speech(frame, self._sr)
        state = str(self._conv.current_state)

        # Phase 6 — IDLE: only the wake word gets us out
        if state == "IDLE":
            await self._idle_frame(frame, is_speech)
            return

        # Idle timer: anything except quiet LISTENING counts as activity
        if is_speech or state != "LISTENING":
            self._last_activity = time.monotonic()
        elif (self._conversation_timeout > 0
              and (time.monotonic() - self._last_activity) >= self._conversation_timeout):
            await self._go_idle()
            return

        # Phase 3 — barge-in: user speaks while VECTOR is speaking
        if state == "VECTOR_SPEAKING":
            if self._bargein and is_speech:
                self._bargein_speech_ms += frame_ms
                if self._bargein_speech_ms >= self._bargein_debounce_ms:
                    await self._barge_in(frame)
            else:
                self._bargein_speech_ms = 0.0
            return

        if state == "PROCESSING":
            return  # ignore audio while thinking (next phase could queue it)

        # Phase 2 — endpointing
        if is_speech:
            if state == "LISTENING":
                self._conv.transition("USER_SPEAKING")
                await self._state("USER_SPEAKING")
                self._utterance = []
                self._utterance_started = time.monotonic()
                self._last_partial = time.monotonic()
            self._utterance.append(frame)
            # partial transcript every ~partial_interval while speaking
            if (time.monotonic() - self._last_partial) >= self._partial_interval:
                self._last_partial = time.monotonic()
                asyncio.create_task(self._partial_decode())
        elif state == "USER_SPEAKING":
            self._utterance.append(frame)        # trailing context for STT
            # VAD flipped back to SILENCE == endpoint reached
            if self._vad.state == "SILENCE":
                audio = np.concatenate(self._utterance) if self._utterance else np.zeros(0)
                self._utterance = []
                self._conv.transition("PROCESSING")
                await self._state("PROCESSING")
                asyncio.create_task(self._finalize_utterance(audio))

    async def _barge_in(self, seed_frame: np.ndarray) -> None:
        logger.info("[VECTOR][realtime] barge-in — interrupting")
        self._bargein_speech_ms = 0.0
        self._conv.interrupt()                   # VECTOR_SPEAKING -> INTERRUPTED
        await self._cancel_speaking()
        await self._safe_send({"type": "stop_audio"})
        self._conv.transition("LISTENING")
        await self._state("LISTENING")
        # the speech that triggered the interrupt starts the next utterance
        self._conv.transition("USER_SPEAKING")
        await self._state("USER_SPEAKING")
        self._utterance = [seed_frame]
        self._utterance_started = time.monotonic()
        self._last_partial = time.monotonic()

    # ── Phase 6: idle timeout + wake-word resume ──────────────────────────────

    async def _go_idle(self) -> None:
        logger.info("[VECTOR][realtime] no speech for {:.0f}s — IDLE (say 'Vector' to resume)",
                    self._conversation_timeout)
        self._utterance = []
        self._wake_buffer = []
        self._wake_buffer_ms = 0.0
        await self._cancel_speaking()
        self._conv.transition("IDLE")
        await self._state("IDLE")

    def _get_wake(self):
        """Lazy WakeWordDetector; None when unavailable (STT fallback handles wake)."""
        if self._wake_detector is None and not self._wake_failed:
            try:
                from core.voice.wake_word import WakeWordDetector
                self._wake_detector = WakeWordDetector()
            except Exception as e:
                logger.warning(f"[VECTOR][realtime] wake detector unavailable: {e}")
                self._wake_failed = True
        return self._wake_detector

    async def _idle_frame(self, frame: np.ndarray, is_speech: bool) -> None:
        """While IDLE, scan incoming frames for the wake word."""
        det = self._get_wake()
        if det is not None and det._model is not None and not det._use_whisper_kws:
            int16 = (frame * 32767.0).astype(np.int16)
            if det.is_wake_word(int16):
                await self._wake_up()
            return

        # Fallback (no openwakeword): buffer one speech burst, STT it once,
        # look for the wake phrase. Reuses the session's lazy STT.
        if is_speech:
            self._wake_buffer.append(frame)
            self._wake_buffer_ms += len(frame) / self._sr * 1000.0
            if self._wake_buffer_ms >= 2500:
                await self._check_wake_buffer()
        elif self._wake_buffer and self._vad.state == "SILENCE":
            await self._check_wake_buffer()

    async def _check_wake_buffer(self) -> None:
        if self._wake_busy:
            self._wake_buffer = []
            self._wake_buffer_ms = 0.0
            return
        audio = np.concatenate(self._wake_buffer) if self._wake_buffer else np.zeros(0)
        self._wake_buffer = []
        self._wake_buffer_ms = 0.0
        if audio.size < self._sr * 0.3:
            return
        stt = self._get_stt()
        if stt is None:
            return
        self._wake_busy = True
        try:
            text = (await asyncio.to_thread(stt.transcribe, audio, self._sr)).lower().strip()
            if "vector" in text or "vektor" in text:
                await self._wake_up()
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] wake KWS decode failed: {e}")
        finally:
            self._wake_busy = False

    async def _wake_up(self) -> None:
        logger.info("[VECTOR][realtime] wake word detected — resuming")
        self._last_activity = time.monotonic()
        self._wake_buffer = []
        self._wake_buffer_ms = 0.0
        self._conv.transition("LISTENING")
        await self._safe_send({"type": "wake"})
        await self._state("LISTENING")

    # ── STT (Phase 2) ─────────────────────────────────────────────────────────

    def _get_stt(self):
        if self._stt is None:
            voice_cfg = CONFIG.get("voice", {})
            realtime_model = voice_cfg.get("realtime_stt_model", "small")
            try:
                from core.voice.stt import FasterWhisperSTT
                stt = FasterWhisperSTT()
            except Exception:
                from core.voice.stt import WhisperSTT
                stt = WhisperSTT()
            stt._model_name = realtime_model     # latency choice, see design §11
            self._stt = stt
        return self._stt

    async def _partial_decode(self) -> None:
        if self._partial_busy or not self._utterance:
            return
        self._partial_busy = True
        try:
            audio = np.concatenate(self._utterance)
            text = await asyncio.to_thread(self._get_stt().transcribe, audio, self._sr)
            if text and str(self._conv.current_state) == "USER_SPEAKING":
                await self._safe_send({"type": "partial_transcript", "text": text})
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] partial decode skipped: {e}")
        finally:
            self._partial_busy = False

    async def _finalize_utterance(self, audio: np.ndarray) -> None:
        try:
            if audio.size < self._sr // 4:       # <250ms of audio — noise blip
                self._back_to_listening()
                await self._state("LISTENING")
                return
            text = await asyncio.to_thread(self._get_stt().transcribe, audio, self._sr)
            text = (text or "").strip()
            if not text:
                self._back_to_listening()
                await self._state("LISTENING")
                return
            await self._safe_send({"type": "final_transcript", "text": text})

            # prompt-injection scan before the text reaches any LLM (design §11)
            try:
                from core.security.prompt_injection import scan_text
                if not scan_text(text, "realtime_voice").clean:
                    await self._speak_text("I'm not acting on that input.")
                    self._back_to_listening()
                    await self._state("LISTENING")
                    return
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass

            # Speaker verification — only the enrolled owner can command actions.
            # Fails open when not enrolled (see speaker_verify.py); every
            # decision is surfaced to the HUD as a "speaker" event.
            self._speaker_owner = True
            try:
                from core.voice.speaker_verify import get_verifier
                _v = get_verifier()
                if _v.active:
                    self._speaker_owner, _sim = await asyncio.to_thread(
                        _v.verify, audio, self._sr)
                    await self._safe_send({"type": "speaker",
                                           "owner": self._speaker_owner,
                                           "similarity": round(_sim, 3)})
                    if not self._speaker_owner:
                        logger.warning(
                            "[VECTOR][realtime] unverified speaker (sim={:.3f})", _sim)
            except Exception as _sv_err:
                logger.debug(f"[VECTOR][realtime] speaker verify skipped: {_sv_err}")

            await self._respond(text)
        except Exception as e:
            logger.error(f"[VECTOR][realtime] finalize failed: {e}")
            self._back_to_listening()
            await self._state("LISTENING")

    def _back_to_listening(self) -> None:
        cur = str(self._conv.current_state)
        if cur != "LISTENING":
            self._conv.transition("LISTENING")

    # ── respond (Phases 1+4) ──────────────────────────────────────────────────

    async def _respond(self, text: str) -> None:
        # 1. rules-engine bypass — instant, no LLM
        try:
            from core.security.rules_engine import get_rules_engine
            engine = get_rules_engine()
            rule = engine.match(text)
            if rule:
                answer = engine.execute_rule(rule, {}) or "Done."
                await self._safe_send({"type": "response", "text": answer})
                await self._speak_text(answer)
                self._store_turn(text, answer, ["bypass", rule.category])
                self._back_to_listening()
                await self._state("LISTENING")
                return
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] rules bypass skipped: {e}")

        # 2. Phase 4 — action handoff to governor (RULE 3: gateway untouched)
        task_type = classify_intent(text)
        if task_type is None:
            # Regex miss → LLM chat-vs-action gate (ambient model, off-thread so
            # the event loop keeps streaming). Governor.route_task() handles the
            # natural-language task type it returns.
            task_type = await asyncio.to_thread(classify_intent_llm, text)
        if task_type and not self._speaker_owner:
            refusal = ("Voice not recognized — action commands are owner-only. "
                       "We can still chat.")
            await self._safe_send({"type": "response", "text": refusal})
            await self._speak_text(refusal)
            self._store_turn(text, refusal, ["security", "speaker_rejected"])
            self._back_to_listening()
            await self._state("LISTENING")
            return
        if task_type:
            ack = "On it."
            await self._safe_send({"type": "action_ack", "task_type": task_type, "text": ack})
            await self._speak_text(ack)
            asyncio.create_task(self._run_action(task_type, text))
            await self._publish_voice_event(text, task_type)
            self._back_to_listening()
            await self._state("LISTENING")
            return

        # 3. chat — streaming LLM -> sentence TTS
        self._cancel_speak.clear()
        self._speak_task = asyncio.create_task(self._stream_chat(text))
        try:
            await self._speak_task
        except asyncio.CancelledError:
            logger.info("[VECTOR][realtime] speak task cancelled (barge-in)")
        finally:
            self._speak_task = None
            if str(self._conv.current_state) == "VECTOR_SPEAKING":
                self._conv.transition("LISTENING")
                await self._state("LISTENING")
            await self._safe_send({"type": "done"})

    async def _stream_chat(self, text: str) -> None:
        speed = 0.85
        system_prompt = ""
        try:
            if CONFIG.get("personality", {}).get("enabled", True):
                from core.personality import PersonalityEngine
                if not hasattr(RealtimeConversation, "_pe"):
                    RealtimeConversation._pe = PersonalityEngine()
                result = RealtimeConversation._pe.process(text)
                sp = result.get("system_prompt", "")
                tone = result.get("tone_config")
                if tone:
                    speed = tone.speed
                if sp:
                    system_prompt = sp
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] personality skipped: {e}")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": text})

        # Use conversation tier: groq → cerebras → gemini → llm7 → ollama (offline fallback)
        # provider_client.chat() handles fallback automatically across all configured providers
        from core.inference.provider_client import ProviderClient
        full, buf, seq = "", "", 0
        speaking = False
        try:
            _client = ProviderClient()
            result = await _client.chat(
                messages=messages,
                tier="conversation",
                max_tokens=512,
                temperature=0.7,
                caller_id="realtime_voice",
            )
            tokens = result.content
        except Exception as e:
            logger.warning("[VECTOR][realtime] provider_client failed, using ollama direct: {}", e)
            # Hard fallback: direct Ollama call so voice never goes silent
            import httpx
            ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
            model = CONFIG.get("models", {}).get("focus", "vector-focus")
            prompt = f"{system_prompt}\n\nUser: {text}" if system_prompt else text
            tokens = ""
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST", f"{ollama_host}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": True, "keep_alive": -1},
                ) as r:
                    async for line in r.aiter_lines():
                        if self._cancel_speak.is_set():
                            return
                        if not line.strip():
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        tokens += payload.get("response", "")
                        if payload.get("done"):
                            break

        # Stream tokens into sentence-chunked TTS
        for token in tokens:
            if self._cancel_speak.is_set():
                return
            full += token
            buf += token
            await self._safe_send({"type": "response_partial", "text": full})
            sentence, buf = pop_sentence(buf)
            if sentence:
                if not speaking:
                    speaking = True
                    self._conv.transition("VECTOR_SPEAKING")
                    await self._state("VECTOR_SPEAKING")
                await self._emit_sentence(sentence, speed, seq)
                seq += 1

        tail = buf.strip()
        if tail and not self._cancel_speak.is_set():
            if not speaking:
                self._conv.transition("VECTOR_SPEAKING")
                await self._state("VECTOR_SPEAKING")
            await self._emit_sentence(tail, speed, seq)
        if full.strip():
            await self._safe_send({"type": "response", "text": full.strip()})
            self._store_turn(text, full.strip(), ["chat", "realtime"])

    async def _emit_sentence(self, sentence: str, speed: float, seq: int) -> None:
        if self._cancel_speak.is_set():
            return
        wav = await asyncio.to_thread(tts_wav, sentence, speed)
        if wav and not self._cancel_speak.is_set():
            await self._safe_send({
                "type": "audio",
                "data": base64.b64encode(wav).decode(),
                "sample_rate": 24000,
                "seq": seq,
            })

    async def _speak_text(self, text: str) -> None:
        """Speak a short standalone line (ack / nudge / bypass answer)."""
        prev = str(self._conv.current_state)
        if prev == "IDLE":
            # FSM: IDLE only allows LISTENING — step through it first
            self._conv.transition("LISTENING")
            prev = "LISTENING"
        if prev in ("LISTENING", "PROCESSING"):
            # FSM only allows VECTOR_SPEAKING from PROCESSING
            if prev != "PROCESSING":
                self._conv.transition("USER_SPEAKING")
                self._conv.transition("PROCESSING")
            self._conv.transition("VECTOR_SPEAKING")
            await self._state("VECTOR_SPEAKING")
        await self._emit_sentence(text, 0.85, 0)
        self._last_activity = time.monotonic()   # don't instantly re-idle after speaking
        if str(self._conv.current_state) == "VECTOR_SPEAKING":
            self._conv.transition("LISTENING")
            await self._state("LISTENING")

    # ── Phase 4: governor handoff ─────────────────────────────────────────────

    async def _run_action(self, task_type: str, text: str) -> None:
        try:
            from core.city.governor import Governor
            result = await Governor().dispatch({
                "type": task_type,
                "params": {"query": text, "user_message": text},
                "source": "voice_realtime",
            })
            status = result.get("status", "unknown")
            if status == "ok":
                summary = str(
                    result.get("summary")
                    or result.get("message")
                    or f"{task_type.replace('_', ' ')} finished."
                )[:280]
            elif status == "no_agents":
                summary = f"No agent is registered for {task_type.replace('_', ' ')} yet."
            else:
                summary = f"{task_type.replace('_', ' ')} came back with status {status}."
            if not self._closed:
                await self._safe_send({"type": "action_result", "task_type": task_type,
                                       "status": status, "text": summary})
                await self._speak_text(summary)
            self._store_turn(text, summary, ["action", task_type])
        except Exception as e:
            logger.error(f"[VECTOR][realtime] action '{task_type}' failed: {e}")
            if not self._closed:
                await self._speak_text("That task hit an error. Details are in the log.")

    async def _publish_voice_event(self, text: str, task_type: str) -> None:
        """Wake the autonomous loop via the event bus (kills the 10s poll path)."""
        try:
            from core.event_bus.bus import get_event_bus
            from core.event_bus.types import Event, EventType
            bus = await get_event_bus()
            await bus.publish(Event(
                event_type=EventType.VOICE_INPUT,
                data={"text": text, "task_type": task_type},
                source="voice_realtime",
            ))
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] voice event publish skipped: {e}")

    # ── Phase 5: proactive speech ─────────────────────────────────────────────

    def _subscribe_nudges(self) -> None:
        try:
            from core.loop.nudge_engine import nudge_engine
            if hasattr(nudge_engine, "subscribe"):
                self._nudge_unsub = nudge_engine.subscribe(self._on_nudge)
                logger.info("[VECTOR][realtime] proactive speech armed")
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] nudge subscribe skipped: {e}")

    def _on_nudge(self, nudge: dict) -> None:
        """Sync callback from nudge_engine — schedule async speech if allowed."""
        try:
            asyncio.get_running_loop().create_task(self._maybe_speak_nudge(nudge))
        except RuntimeError:
            pass  # no running loop in caller thread — skip

    async def _maybe_speak_nudge(self, nudge: dict) -> None:
        if self._closed or not nudge:
            return
        state = str(self._conv.current_state)
        if state not in ("IDLE", "LISTENING"):
            return                                # never talk over a turn
        priority = float(nudge.get("priority", 0.5))
        if priority < self._proactive_min_priority:
            return
        now = time.localtime()
        if _in_quiet_hours(now.tm_hour * 60 + now.tm_min, self._quiet_hours):
            return
        try:
            from core.loop.presence import allow_proactive
            if not allow_proactive("realtime_voice"):
                return
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass
        text = str(nudge.get("text", "")).strip()
        if not text:
            return
        logger.info("[VECTOR][realtime] proactive: {}", text[:80])
        await self._safe_send({"type": "proactive", "text": text})
        await self._speak_text(text)
        self._store_turn("(proactive)", text, ["proactive", str(nudge.get("rule", ""))])

    # ── plumbing ──────────────────────────────────────────────────────────────

    async def _cancel_speaking(self) -> None:
        self._cancel_speak.set()
        task = self._speak_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._speak_task = None

    async def _state(self, value: str) -> None:
        await self._safe_send({"type": "state", "value": value})
        if self._orb is not None:
            try:
                orb_map = {"LISTENING": "listening", "USER_SPEAKING": "listening",
                           "PROCESSING": "processing", "VECTOR_SPEAKING": "speaking",
                           "IDLE": "idle"}
                await self._orb(orb_map.get(value, "idle"))
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass

    async def _safe_send(self, payload: dict) -> None:
        if self._closed:
            return
        try:
            await self._send(payload)
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] send failed (client gone?): {e}")
            self._closed = True

    def _store_turn(self, user_text: str, vector_text: str, tags: list[str]) -> None:
        try:
            from core.memory.episodic import EpisodicMemory
            EpisodicMemory().store(
                event_type="realtime_conversation",
                content=f"Q: {user_text} | A: {vector_text}",
                tags=["voice"] + tags,
                source="realtime_voice",
            )
        except Exception as e:
            logger.debug(f"[VECTOR][realtime] episodic store skipped: {e}")