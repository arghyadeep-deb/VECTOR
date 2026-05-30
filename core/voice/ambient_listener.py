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
from core.resilience.bulkhead_executor import BulkheadRegistry, BulkheadRejectedError

_END_PHRASES = {"that's all vector", "thats all vector", "stop vector", "goodbye vector"}
_WAKE_MODES = {
    "hey_vector": "conversation",
    "vector_think": "deep_think",
    "vector_private": "private",
}
_SILENCE_TIMEOUT_SEC = 45.0
_CONSENT_PATH = Path(__file__).parent.parent.parent / "data" / "consent.json"


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
    "When classifying intent, always respond with valid JSON only."
)

_ACTION_TYPES = (
    "search_web, set_timer, play_music, take_screenshot, check_weather, "
    "check_attendance, set_reminder, read_calendar, create_calendar_event, "
    "commit_code, download_file, open_panel, run_command, respond, "
    "widget_open, widget_close, widget_show_location, music_play, music_pause, music_next, "
    "home_control"
)


class AmbientListener:
    """
    Orchestrates the full voice pipeline:
    wake_word â†’ STT â†’ language_detect â†’ intent classify (Ollama) â†’ permission_gateway â†’ TTS â†’ memory

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
            from core.voice.stt import WhisperSTT
            self._stt = WhisperSTT()
        except Exception as e:
            logger.warning(f"[VECTOR][voice] WhisperSTT init failed: {e}")

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
                if self._conversation:
                    self._conversation.start_session("default_user")
                    self._conversation.transition("LISTENING")
                await self.handle_voice_input(mode=mode)
        except Exception as e:
            logger.error(f"[VECTOR][voice] _wake_and_handle error: {e}")

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

        # Seed conversation history from recent episodic memory (bridges chatâ†”voice silo)
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
                if self._stt:
                    duration = CONFIG.get("voice", {}).get("record_duration_sec", 5.0)
                    text = await asyncio.to_thread(self._stt.record_and_transcribe, duration_sec=duration)
                if not text:
                    await asyncio.sleep(0.5)
                    continue

                self._last_speech_time = time.time()

                if self._is_end_phrase(text):
                    logger.info("[VECTOR][voice] End phrase — session closed")
                    farewell = "Understood, sir. Standing by."
                    if self._tts:
                        await asyncio.to_thread(self._tts.speak, farewell, lang="en")
                    self._session_active = False
                    if self._conversation:
                        self._conversation.end_session()
                    break

                logger.info(f"[VECTOR][voice] TRANSCRIBE: '{text}'")

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

                    if action_type == "home_control":
                        msg = await self._handle_home_control(text)
                        response_parts.append(msg)
                    else:
                        action = Action(action_type=action_type, params=params, proposed_by="voice")
                        result = await gw.execute(action)
                        msg = result.get("message", f"Done, sir: {action_type}.")
                        response_parts.append(msg)

                        if str(result.get("decision", "")).upper() == "RED":
                            logger.info(f"[VECTOR][voice] RED denial on {action_type} — stopping chain")
                            break

                if self._conversation:
                    self._conversation.transition("VECTOR_SPEAKING")

                response_text = " ".join(p for p in response_parts if p) or f"Done, sir."
                logger.info(f"[VECTOR][voice] SPEAK: '{response_text}'")
                if self._tts:
                    if tone_config:
                        self._tts._speed = tone_config.speed
                    await asyncio.to_thread(self._tts.speak, response_text, lang=lang)

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
            import httpx
            ollama_host = CONFIG["ollama_host"]
            model = CONFIG["models"]["ambient"]

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

            bulkhead = BulkheadRegistry.get("voice")
            async def _classify_call():
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(
                        f"{ollama_host}/api/chat",
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt},
                            ],
                            "stream": False,
                        },
                    )
                    resp.raise_for_status()
                    raw = resp.json().get("message", {}).get("content", "")
                    start = raw.find("{")
                    end = raw.rfind("}") + 1
                    if start != -1 and end > start:
                        return json.loads(raw[start:end])
                    return None
            if bulkhead:
                result = await bulkhead.execute(_classify_call)
                if result:
                    return result
            else:
                result = await _classify_call()
                if result:
                    return result
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
            import httpx
            ollama_host = CONFIG["ollama_host"]
            model = CONFIG["models"]["ambient"]

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
                "For pure conversational replies use one intent action_type='respond' "
                "with params.message set to the spoken reply.\n"
                "Preserve order of commands as the user said them.\n"
                "Respond with ONLY valid JSON. No prose."
            )

            bulkhead = BulkheadRegistry.get("voice")
            async def _classify_call():
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(
                        f"{ollama_host}/api/chat",
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt},
                            ],
                            "stream": False,
                        },
                    )
                    resp.raise_for_status()
                    return resp.json().get("message", {}).get("content", "")
            if bulkhead:
                raw = await bulkhead.execute(_classify_call)
            else:
                raw = await _classify_call()

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


    async def _handle_home_control(self, text: str) -> str:
        try:
            from districts.home_assistant.voice_bridge import VoiceBridge
            from districts.home_assistant.entity_manager import EntityManager
            from districts.home_assistant.connector import HAConfig, HAConnector

            cfg = HAConfig(
                host=CONFIG.get("home_assistant", {}).get("host", "homeassistant.local"),
                port=CONFIG.get("home_assistant", {}).get("port", 8123),
                token=CONFIG.get("home_assistant", {}).get("token", ""),
                use_ssl=CONFIG.get("home_assistant", {}).get("use_ssl", False),
            )
            connector = HAConnector(cfg)
            await connector.connect()
            entity_mgr = EntityManager()
            await entity_mgr.discover(connector)
            bridge = VoiceBridge(entity_mgr, connector)
            result = await bridge.process(text)
            await connector.disconnect()
            return result
        except Exception as e:
            logger.error(f"[VECTOR][voice] home_control failed: {e}")
            return f"Home control failed: {e}"


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
        print(f"âœ… ambient_listener OK {components}" if all_ok else f"âš ï¸ ambient_listener partial {components}")

    asyncio.run(_smoke())
