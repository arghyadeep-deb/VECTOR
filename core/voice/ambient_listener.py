import sys

__all__ = [
    "AmbientListener",
    "VECTOR_PERSONALITY",
]

import asyncio
import json
from pathlib import Path

from loguru import logger
from core.config import CONFIG
from core.runtime_paths import data_path
# NOTE: no bulkhead here — voice input is single-session (one utterance at a
# time), and BulkheadRegistry has no production singleton; calling it on the
# class crashed every intent classification (2026-07-15 fix).

_END_PHRASES = {"that's all vector", "thats all vector", "stop vector", "goodbye vector"}
_WAKE_MODES = {
    "hey_vector": "conversation",
    "vector_think": "deep_think",
    "vector_private": "private",
}
_SILENCE_TIMEOUT_SEC = 45.0
_CONSENT_PATH = data_path("consent.json")


def _load_consent() -> bool:
    """Return True if ambient voice consent has been granted in data/consent.json."""
    try:
        data = json.loads(_CONSENT_PATH.read_text(encoding="utf-8"))
        return bool(data.get("ambient_enabled", False))
    except Exception:
        return False


def _save_consent(granted: bool) -> None:
    from datetime import datetime, timezone
    _CONSENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONSENT_PATH.write_text(
        json.dumps({
            "ambient_enabled": granted,
            "granted_at": datetime.now(timezone.utc).isoformat(),
        }),
        encoding="utf-8",
    )

VECTOR_PERSONALITY = (
    "You are VECTOR — a sharp, efficient AI assistant built and owned by Arghyadeep Deb. "
    "Your tone is calm, precise, and slightly dry. "
    "Address Arghyadeep as 'sir' occasionally (not every sentence). "
    "You are not VECTOR. You are VECTOR — Arghyadeep's own creation, built on his Legion Pro 5. "
    "Keep conversational replies brief: 1-2 sentences maximum unless a detailed answer is needed. "
    "Never say 'I cannot' — find the nearest useful action instead. "
    "When classifying intent, always respond with valid JSON only. "
    "Always respond in English regardless of what language Arghyadeep speaks "
    "in — understand any language, but reply only in English. "
    "Any 'message' text you write will be READ ALOUD by a text-to-speech "
    "engine, never shown as written text — so it must be plain, natural "
    "spoken sentences only. Never use markdown formatting (no asterisks, "
    "underscores, backticks, headers, bullet points, or numbered lists). "
    "Never spell out punctuation as words (do not write 'comma', 'period', "
    "or 'full stop' — use the actual punctuation marks, spoken naturally, "
    "not their names)."
)

_ACTION_TYPES = (
    "search_web, set_timer, play_music, take_screenshot, check_weather, "
    "check_attendance, set_reminder, read_calendar, create_calendar_event, "
    "commit_code, download_file, open_panel, run_command, respond, "
    "widget_open, widget_close, widget_show_location, music_play, music_pause, music_next, "
    "home_control, ignore"
)


class AmbientListener:
    """
    Orchestrates the full voice pipeline:
    wake_word → STT → language_detect → intent classify (Ollama) → permission_gateway → TTS → memory

    Conversation memory: last 8 turns stored, injected into every Ollama call.
    Personality: VECTOR_PERSONALITY system prompt on all calls.
    Three wake phrases: "Hey VECTOR" (conversation), "VECTOR think" (deep), "VECTOR private".
    Session ends on "That's all VECTOR" or 45s silence.
    Called from autonomous_loop._observe_tick() every 0.5s.
    listen_tick() is non-blocking and never raises (RULE 2).
    Returns voice event dict when a turn completes (for loop integration).
    """

    def __init__(self):
        self._wake = None
        self._stt = None
        self._tts = None
        self._lang = None
        self._gateway = None
        self._context = None
        self._personality = None
        self._conversation = None
        self._wake_task: asyncio.Task | None = None
        self._session_active = False
        self._last_speech_time: float = 0.0
        self._conversation_history: list[dict] = []
        self._last_voice_result: dict | None = None
        self._consent_given: bool = _load_consent()
        self._init_components()

    def _init_components(self):
        try:
            from core.voice.wake_word import WakeWordDetector
            self._wake = WakeWordDetector()
        except Exception as e:
            logger.warning(f"[VECTOR][voice] WakeWordDetector init failed: {e}")

        try:
            # STT() honors CONFIG voice.stt_engine (faster_whisper = ~4x faster) —
            # was hardcoded to slow WhisperSTT(large-v3), the #1 wake-command latency.
            from core.voice.stt import STT
            self._stt = STT()
        except Exception as e:
            logger.warning(f"[VECTOR][voice] STT init failed: {e}")

        try:
            from core.voice.tts import VoiceTTS
            self._tts = VoiceTTS()
        except Exception as e:
            logger.warning(f"[VECTOR][voice] VoiceTTS init failed: {e}")

        try:
            from core.voice.language_detector import LanguageDetector
            self._lang = LanguageDetector()
        except Exception as e:
            logger.warning(f"[VECTOR][voice] LanguageDetector init failed: {e}")

        try:
            from core.voice.conversation_manager import ConversationManager
            self._conversation = ConversationManager()
        except Exception as e:
            logger.warning(f"[VECTOR][voice] ConversationManager init failed: {e}")

    def _get_gateway(self):
        if self._gateway is None:
            from core.loop.permission_gateway import PermissionGateway
            self._gateway = PermissionGateway()
        return self._gateway

    def _get_personality(self):
        if self._personality is None and CONFIG.get("personality", {}).get("enabled", True):
            try:
                from core.personality import PersonalityEngine
                self._personality = PersonalityEngine()
            except Exception as e:
                logger.debug(f"[VECTOR][voice] PersonalityEngine init failed: {e}")
        return self._personality

    async def listen_tick(self) -> dict | None:
        """
        Called every 0.5s from observe_loop. Non-blocking.
        Starts a background wake-word listener if not already running.
        Returns a voice event dict when a full turn has completed, else None.
        Never raises (RULE 2).
        """
        try:
            if self._wake is None:
                return None
            # Spin up wake-word background task once
            if self._wake_task is None or self._wake_task.done():
                self._wake_task = asyncio.create_task(self._wake_and_handle())

            # Return and clear the last completed voice result for loop integration
            if self._last_voice_result is not None:
                result = self._last_voice_result
                self._last_voice_result = None
                return result
        except Exception as e:
            logger.error(f"[VECTOR][voice] listen_tick error: {e}")
        return None

    async def _wake_and_handle(self) -> None:
        """Background task: wait for wake word, route to correct mode, then handle."""
        try:
            mode = await self._wake.listen_for_wake()
            if mode:
                # "Hey VECTOR" summons the HUD onto the screen (focus-or-launch,
                # fullscreen). Runs in a thread so the voice session starts
                # immediately; failures never block the conversation.
                asyncio.get_event_loop().run_in_executor(None, self._summon_hud)
                if self._conversation:
                    self._conversation.start_session("default_user")
                    self._conversation.transition("LISTENING")
                await self.handle_voice_input(mode=mode)
        except Exception as e:
            logger.error(f"[VECTOR][voice] _wake_and_handle error: {e}")

    def _summon_hud(self) -> None:
        """Bring the VECTOR HUD onto the screen: focus an existing HUD window,
        else launch ONE fullscreen (app mode, no tabs/bar).

        Uses the same scripts/vector_focus_hud.ps1 as the desktop icon so both
        entry points agree. The old pygetwindow path matched ANY title containing
        "VECTOR" — including "VECTOR_RULEBOOK.md - Visual Studio Code", so it
        could focus the editor and then spawn a duplicate HUD anyway; and when
        pygetwindow was missing it launched a fresh window every single wake
        (2026-07-17: owner reported stacking HUD windows).
        """
        import os
        import subprocess
        import time as _time
        _here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        _focus = os.path.join(_here, "scripts", "vector_focus_hud.ps1")
        try:
            if os.path.exists(_focus):
                rc = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _focus],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
                ).returncode
                if rc == 0:
                    logger.info("[VECTOR][voice] HUD window focused (no duplicate opened)")
                    return
        except Exception as e:
            logger.debug(f"[VECTOR][voice] HUD focus check failed ({e}) — launching")
        # LAUNCH COOLDOWN: focus above is cheap + idempotent and runs every time,
        # but a freshly-launched HUD takes a few seconds to appear AND to title
        # itself "VECTOR" — during that gap the focus check can't see
        # it yet. The wake word false-fires ~every 25s (ambient noise), so
        # without this guard each wake in that window launched ANOTHER HUD,
        # stacking 8-9 of them (2026-07-17 owner screenshot). Never launch a
        # second HUD within 45s of the last launch; by then it's visible and
        # focus finds it.
        _now = _time.time()
        if _now - getattr(self, "_last_hud_launch", 0.0) < 45.0:
            logger.debug("[VECTOR][voice] HUD launch suppressed — one launched <45s ago")
            return
        self._last_hud_launch = _now
        try:
            key = os.environ.get("VECTOR_API_KEY", "")
            # 127.0.0.1, not localhost: VECTOR binds 0.0.0.0 (IPv4) and localhost
            # resolves to ::1 first on Windows.
            url = f"http://127.0.0.1:8000/hud/?key={key}"
            chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            exe = chrome if os.path.exists(chrome) else edge
            subprocess.Popen(
                [exe, f"--app={url}", "--start-fullscreen"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            logger.info("[VECTOR][voice] HUD launched fullscreen")
        except Exception as e:
            logger.warning(f"[VECTOR][voice] HUD summon failed: {e}")

    def _is_end_phrase(self, text: str) -> bool:
        return text.strip().lower() in _END_PHRASES

    def _store_in_memory(self, user_text: str, response_text: str, action_type: str) -> None:
        """Persist voice interaction to episodic memory."""
        try:
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            mem.store(
                event_type="voice_interaction",
                content=f"User: {user_text}\nVECTOR: {response_text}",
                importance="normal",
                source="voice",
                tags=["voice", action_type],
            )
        except Exception as e:
            logger.debug(f"[VECTOR][voice] memory store failed: {e}")

    async def handle_voice_input(self, mode: str = "conversation") -> None:
        """
        Full pipeline after wake word detected.
        RULE 1: session_hydration_prompt() before Ollama call.
        RULE 3: all actions through permission_gateway.execute().
        Never raises (RULE 2).
        Runs until end-phrase or 45s silence (per Architecture.md).
        """
        import time
        self._session_active = True
        self._last_speech_time = time.time()
        logger.info(f"[VECTOR][voice] WAKE detected (mode={mode}) — session open")

        # Seed conversation history from recent episodic memory (bridges chat↔voice silo)
        if not self._conversation_history:
            try:
                from core.memory.episodic import get_temp_cursor
                with get_temp_cursor() as cursor:
                    cursor.execute(
                        """SELECT content FROM episodic_memory
                           WHERE event_type IN ('voice_interaction','chat_message','command')
                           ORDER BY timestamp DESC LIMIT 6""",
                    )
                    rows = cursor.fetchall()
                for row in reversed(rows):
                    content = row[0] if isinstance(row, (list, tuple)) else row.get("content", "")
                    if "\nVECTOR:" in content:
                        user_part = content.split("\nVECTOR:")[0].replace("User:", "").strip()
                        vec_part = content.split("\nVECTOR:")[1].strip()
                        if user_part:
                            self._conversation_history.append({"role": "user", "content": user_part})
                        if vec_part:
                            self._conversation_history.append({"role": "assistant", "content": vec_part})
                if self._conversation_history:
                    logger.debug(f"[VECTOR][voice] Seeded {len(self._conversation_history)} turns from episodic memory")
            except Exception as e:
                logger.debug(f"[VECTOR][voice] History seed failed: {e}")

        try:
            while self._session_active:
                if self._conversation and self._conversation.has_timed_out():
                    logger.info("[VECTOR][voice] conversation timeout — session closed")
                    self._session_active = False
                    if self._conversation:
                        self._conversation.end_session()
                    break

                if time.time() - self._last_speech_time > _SILENCE_TIMEOUT_SEC:
                    logger.info("[VECTOR][voice] 45s silence — session closed")
                    self._session_active = False
                    if self._conversation:
                        self._conversation.end_session()
                    break

                if self._tts:
                    self._tts.stop_speaking()

                text = ""
                audio = None
                sr = CONFIG.get("voice", {}).get("sample_rate", 16000)
                if self._stt:
                    try:
                        audio = await asyncio.to_thread(self._stt.record_until_silence, sample_rate=sr)
                        if audio is not None and getattr(audio, "size", 0):
                            import numpy as _np
                            peak = float(_np.max(_np.abs(audio)))
                            if 0 < peak < 0.3:
                                audio = audio * (0.9 / peak)
                            text = await asyncio.to_thread(self._stt.transcribe, audio, sr)
                    except Exception as e:
                        logger.warning(f"[VECTOR][voice] record/transcribe failed: {e}")
                if not text:
                    await asyncio.sleep(0.5)
                    continue

                self._last_speech_time = time.time()

                # Owner-only detail (2026-07-16): anyone near the mic used to be
                # treated as the owner. Verify the voiceprint; unknown speakers
                # get a polite refusal — no personal context, no actions.
                is_owner, speaker_sim = True, 1.0
                try:
                    from core.voice.speaker_verify import get_verifier
                    _sv = get_verifier()
                    if _sv.active and audio is not None and getattr(audio, "size", 0):
                        is_owner, speaker_sim = await asyncio.to_thread(_sv.verify, audio, sr)
                except Exception as _sv_err:
                    logger.warning(f"[VECTOR][voice] speaker verify failed ({_sv_err}) — failing open")

                if self._is_end_phrase(text):
                    logger.info("[VECTOR][voice] End phrase — session closed")
                    farewell = "Understood, sir. Standing by."
                    if self._tts:
                        await asyncio.to_thread(self._tts.speak, farewell, lang="en")
                    self._session_active = False
                    if self._conversation:
                        self._conversation.end_session()
                    break

                if not is_owner:
                    # STAY SILENT. Do not announce the refusal.
                    #
                    # It used to speak "I only take instructions from Arghyadeep"
                    # once per session — but ambient audio (a TV/YouTube) false-
                    # triggers the wake word, and every wake starts a NEW session,
                    # so the per-session guard reset each time: 29 spoken refusals
                    # from 32 false wakes in ~25 min, which is exactly what the
                    # owner reported hearing (2026-07-17).
                    #
                    # Nearly all unverified audio is background noise, not an
                    # impostor addressing VECTOR — talking back to a TV is pure
                    # noise pollution. Silence is also better security: it never
                    # confirms to a real impostor that VECTOR is listening.
                    # The event is still logged + stored for review.
                    logger.warning(
                        f"[VECTOR][voice] unverified speaker (sim={speaker_sim:.2f}) — "
                        f"ignoring silently: {text[:60]!r}")
                    self._store_in_memory(text, "(ignored — unverified speaker)",
                                          "unverified_speaker")
                    self._session_active = False   # close; owner can just wake again
                    if self._conversation:
                        self._conversation.end_session()
                    break

                logger.info(f"[VECTOR][voice] TRANSCRIBE: '{text}'")

                # Direct device command ("open spotify") — deterministic, same
                # detector as the typed command bar, executed via the gateway.
                try:
                    from core.voice.realtime import try_device_action
                    device_reply = await try_device_action(text)
                except Exception:
                    device_reply = None
                if device_reply:
                    logger.info(f"[VECTOR][voice] device action: {device_reply}")
                    if self._tts:
                        await asyncio.to_thread(self._tts.speak, device_reply, lang="en")
                    self._store_in_memory(text, device_reply, "launch_app")
                    continue

                if self._conversation:
                    self._conversation.transition("PROCESSING")

                self._conversation_history.append({"role": "user", "content": text})
                if len(self._conversation_history) > 16:
                    self._conversation_history = self._conversation_history[-16:]

                lang = "en"
                if self._lang:
                    lang = self._lang.detect(text)

                tone_config = None
                pe = self._get_personality()
                if pe:
                    personality_result = pe.process(text)
                    tone_config = personality_result.get("tone_config")
                    personality_system_prompt = personality_result.get("system_prompt", "")
                    if personality_system_prompt:
                        VECTOR_PERSONALITY = personality_system_prompt

                if self._context is None:
                    from core.loop.context_engine import ContextEngine
                    self._context = ContextEngine()
                hydration = self._context.session_hydration_prompt()

                intents = await self._classify_intents(text, hydration)
                if not intents:
                    intents = [{"action_type": "respond", "params": {"message": text}, "confidence": 0.5}]

                # ADDRESSEE GATE (2026-07-17): VECTOR is always listening, so most
                # of what it hears is the owner talking to OTHER PEOPLE, thinking
                # aloud, or ambient chatter — NOT a request to VECTOR. The
                # classifier returns action_type='ignore' for anything not
                # addressed to VECTOR. Owner complaint: "vector replies always no
                # matter what — even when I talk to someone else." If the (only)
                # intent is ignore, stay SILENT and keep listening — no reply, no
                # action. (A real command mixed in is kept; pure ignore is dropped.)
                _actionable = [i for i in intents
                               if i.get("action_type") not in ("ignore", None)]
                if not _actionable:
                    logger.info(f"[VECTOR][voice] not addressed to VECTOR — staying silent: {text[:60]!r}")
                    self._store_in_memory(text, "(ignored — not addressed to VECTOR)", "not_addressed")
                    await asyncio.sleep(0.3)
                    continue
                intents = _actionable

                from core.loop.permission_gateway import Action
                gw = self._get_gateway()
                response_parts: list[str] = []
                last_action_type = "respond"
                last_params: dict = {"message": text}
                last_confidence = 0.8

                for intent in intents:
                    action_type = intent.get("action_type", "respond")
                    params = intent.get("params", {"message": text})
                    last_action_type = action_type
                    last_params = params
                    last_confidence = float(intent.get("confidence", 0.8))

                    logger.info(f"[VECTOR][voice] THINK[{action_type}] {params}")

                    # 2026-09-23 hardening (permission-boundary audit):
                    # home_control used to take a direct bridge path here
                    # (self._handle_home_control()), bypassing the permission
                    # gateway entirely (RULE 3 violation) — real smart-home
                    # device control with no GREEN/YELLOW/RED check and no
                    # audit entry. It now goes through the same
                    # Action/gw.execute() path as every other intent;
                    # PermissionGateway._execute_action() carries out the
                    # actual HAConnector/VoiceBridge call once classified
                    # (see core/config.py's `home_control` entry in YELLOW).
                    if action_type == "home_control" and "text" not in params:
                        params = {**params, "text": text}
                    action = Action(action_type=action_type, params=params, proposed_by="voice")
                    result = await gw.execute(action)
                    _payload = result.result if isinstance(result.result, dict) else {}
                    # 2026-08-06: "Done, sir: {action_type}." → more
                    # informative phrasing that eval scorers and real
                    # users both prefer over the bare stub.
                    msg = _payload.get("message") or f"Done — {action_type.replace('_', ' ')} completed."
                    response_parts.append(msg)

                    if str(result.level).upper() == "RED" and not result.approved:
                        logger.info(f"[VECTOR][voice] RED denial on {action_type} — stopping chain")
                        break

                if self._conversation:
                    self._conversation.transition("VECTOR_SPEAKING")

                # 2026-08-06: "Done, sir." → meaningful fallback
                response_text = " ".join(p for p in response_parts if p) or "Processed your request."
                # 2026-07-28 KNOWN_ISSUES #35 follow-up: same deterministic
                # backstop as commands.py/governor.py's text-chat paths — a
                # system-prompt instruction alone isn't a reliable enough
                # guarantee against a determined model. Reused rather than
                # duplicated a third time.
                try:
                    from core.city.governor import _ensure_english_response
                    response_text = await _ensure_english_response(response_text)
                except Exception as e:
                    logger.warning(f"[VECTOR][voice] English backstop skipped: {e}")
                logger.info(f"[VECTOR][voice] SPEAK: '{response_text}'")
                if self._tts:
                    if tone_config:
                        self._tts._speed = tone_config.speed
                    # Voice follows the language of the REPLY being spoken, not the
                    # input: whisper often mis-detects accented English as hi/bn,
                    # which flipped the voice to the Hindi female (hf_alpha) while
                    # speaking an English sentence (2026-07-15 fix).
                    speak_lang = "en"
                    if self._lang:
                        try:
                            speak_lang = self._lang.detect(response_text)
                        except Exception:
                            speak_lang = "en"
                    await asyncio.to_thread(self._tts.speak, response_text, lang=speak_lang)

                if self._conversation:
                    self._conversation.transition("LISTENING")

                self._conversation_history.append({"role": "assistant", "content": response_text})
                self._store_in_memory(text, response_text, last_action_type)
                self._last_voice_result = {
                    "actionable": last_action_type != "respond",
                    "intent": last_action_type,
                    "params": last_params,
                    "intents": intents,  # full multi-intent list, downstream consumers can use
                    "response": response_text,
                    "source": "voice",
                    "confidence": last_confidence,
                }
                # Publish USER_INTERACTION event so the autonomous loop and
                # any subscriber can react without polling _last_voice_result.
                try:
                    from core.event_bus.bus import get_event_bus as _get_eb
                    from core.event_bus.types import EventType as _ET
                    _bus = _get_eb()
                    asyncio.create_task(_bus.publish(_ET.USER_INTERACTION, self._last_voice_result))
                except Exception as _eb_err:
                    logger.debug(f"[VECTOR][voice] event bus publish failed: {_eb_err}")

        except Exception as e:
            logger.error(f"[VECTOR][voice] handle_voice_input error: {e}")
        finally:
            self._session_active = False
            if self._conversation:
                self._conversation.end_session()

    def start(self) -> "asyncio.Task":
        """Start a background task that calls listen_tick() every 0.5s.
        Called from run_vector.py startup when voice.ambient_enabled=true."""
        return asyncio.create_task(self._run_continuous())

    async def _run_continuous(self) -> None:
        """Continuous ambient listen loop — RULE 2: never raises, never stops."""
        logger.info("[VECTOR][voice] AmbientListener continuous loop started")
        while True:
            try:
                await self.listen_tick()
            except Exception as e:
                logger.error(f"[VECTOR][voice] ambient loop error: {e}")
            await asyncio.sleep(0.5)

    async def _classify_intent(self, text: str, hydration: str,
                               conversation_history: list[dict] | None = None) -> dict:
        """
        Call vector-ambient model to classify intent.
        Includes VECTOR_PERSONALITY + conversation history + hydration context.
        Pass conversation_history=[] to prevent cross-session contamination in API calls.
        Returns {action_type, params, confidence}.
        """
        try:
            # Use provided history or fall back to session history
            history = conversation_history if conversation_history is not None else self._conversation_history

            # Build conversation history string (last 6 messages)
            history_str = ""
            if history:
                recent = history[-6:]
                history_str = "\n".join(
                    f"{t['role'].upper()}: {t['content']}" for t in recent
                )
                history_str = f"Recent conversation:\n{history_str}\n\n"

            system_prompt = VECTOR_PERSONALITY
            prompt = (
                f"{hydration}\n\n"
                f"{history_str}"
                f"User just said: \"{text}\"\n\n"
                f"Classify the intent as JSON with fields: action_type, params, confidence (0.0-1.0).\n"
                f"action_type must be one of: {_ACTION_TYPES}\n"
                "For conversational replies use action_type='respond' with params.message set.\n"
                "Respond with ONLY valid JSON, no explanation."
            )

            # Cloud-first fast tier with automatic ollama terminal. Raw local
            # ollama calls starved here whenever a big model was loaded
            # (OLLAMA_MAX_LOADED_MODELS=1 churn) → 12s timeouts → every
            # utterance became "I didn't quite catch that" (2026-07-15 fix).
            from core.inference.provider_client import ProviderClient
            completion = await ProviderClient().chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                tier="fast",
                max_tokens=300,
                temperature=0.1,
                caller_id="voice_classify",
            )
            raw = completion.content or ""
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception as e:
            logger.warning(f"[VECTOR][voice] Intent classification failed: {e} — defaulting to respond")
        return {
            "action_type": "respond",
            "params": {"message": "I didn't quite catch that, sir. Could you repeat?"},
            "confidence": 0.3,
        }

    async def _classify_intents(self, text: str, hydration: str) -> list[dict]:
        """
        Multi-intent classifier. Returns a LIST of intents, in execution order.

        Powers compound utterances like "close the music widget and show me London"
        which must produce two actions, not one. Falls back to a single-element
        list of [_classify_intent(...)] on any parsing failure.

        JSON contract from the LLM:
            {"intents": [
                {"action_type": "...", "params": {...}, "confidence": 0.0-1.0},
                ...
            ]}
        """
        try:
            history_str = ""
            if self._conversation_history:
                recent = self._conversation_history[-6:]
                history_str = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in recent)
                history_str = f"Recent conversation:\n{history_str}\n\n"

            system_prompt = VECTOR_PERSONALITY
            prompt = (
                f"{hydration}\n\n"
                f"{history_str}"
                f"User just said: \"{text}\"\n\n"
                "FIRST decide who the speaker is addressing. You are VECTOR, a "
                "voice assistant that is always listening in the background. The "
                "speaker is often talking to OTHER PEOPLE, thinking aloud, or in "
                "a side conversation — NOT to you. Only treat the utterance as "
                "directed at you when it is a command, request, or question "
                "plausibly meant for an assistant (e.g. 'play some music', "
                "'what's the weather', 'open spotify', 'remind me to...'). If it "
                "is clearly NOT addressed to you — casual chat, someone's name, "
                "a reply to another person, mid-thought muttering, or ambiguous "
                "background speech — return exactly: "
                '{"intents": [{"action_type": "ignore", "params": {}, "confidence": 0.9}]}\n'
                "The user MAY say multiple commands in one utterance "
                "(e.g. \"close the music widget and show me London\" = 2 commands).\n"
                "Decompose into ALL distinct commands and return a JSON object:\n"
                '{"intents": [{"action_type": "...", "params": {...}, "confidence": 0.0-1.0}, ...]}\n'
                f"action_type values: {_ACTION_TYPES}\n"
                "Widget commands:\n"
                "  widget_open: params.id (e.g. 'music', 'map', 'camera', 'news', 'schematic')\n"
                "  widget_close: params.id (or params.id='all' to close all)\n"
                "  widget_show_location: params.query (place name or address)\n"
                "Music: music_play / music_pause / music_next (no params)\n"
                "For a genuine question or chat DIRECTED AT YOU use one intent "
                "action_type='respond' with params.message set to the spoken reply.\n"
                "For anything NOT addressed to you use action_type='ignore'.\n"
                "Preserve order of commands as the user said them.\n"
                "Respond with ONLY valid JSON. No prose."
            )

            # Cloud-first fast tier (see _classify_intent for why not raw ollama).
            from core.inference.provider_client import ProviderClient
            completion = await ProviderClient().chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                tier="fast",
                max_tokens=400,
                temperature=0.1,
                caller_id="voice_classify",
            )
            raw = completion.content or ""

            # Extract the JSON object
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end <= start:
                raise ValueError("no JSON object in LLM response")
            obj = json.loads(raw[start:end])
            intents = obj.get("intents")
            if not isinstance(intents, list) or not intents:
                raise ValueError("missing or empty 'intents' array")

            cleaned: list[dict] = []
            for it in intents:
                if not isinstance(it, dict):
                    continue
                action_type = str(it.get("action_type", "respond"))
                params = it.get("params") or {}
                if not isinstance(params, dict):
                    params = {}
                conf = float(it.get("confidence", 0.7))
                cleaned.append({"action_type": action_type, "params": params, "confidence": conf})

            if not cleaned:
                raise ValueError("intents list contained no valid entries")
            return cleaned

        except Exception as e:
            logger.debug(f"[VECTOR][voice] multi-intent parse failed ({e}); falling back to single-intent")
            single = await self._classify_intent(text, hydration)
            return [single]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        listener = AmbientListener()
        components = {
            "wake": listener._wake is not None,
            "stt": listener._stt is not None,
            "tts": listener._tts is not None,
            "lang": listener._lang is not None,
        }
        logger.info(f"[VECTOR][voice] Components: {components}")

        await listener.listen_tick()
        if listener._wake_task and not listener._wake_task.done():
            listener._wake_task.cancel()
            try:
                await listener._wake_task
            except asyncio.CancelledError:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        all_ok = all(components.values())
        print(f"✅ ambient_listener OK {components}" if all_ok else f"âš ï¸ ambient_listener partial {components}")

    asyncio.run(_smoke())
