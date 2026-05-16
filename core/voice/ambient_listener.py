import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


_END_PHRASES = {"that's all vector", "thats all vector", "stop vector", "goodbye vector"}
_WAKE_MODES = {
    "hey_vector": "conversation",
    "vector_think": "deep_think",
    "vector_private": "private",
}
_SILENCE_TIMEOUT_SEC = 45.0


class AmbientListener:
    """
    Orchestrates the full voice pipeline:
    wake_word → STT → language_detect → intent classify (Ollama) → permission_gateway → TTS

    Three wake phrases: "Hey VECTOR" (conversation), "VECTOR think" (deep), "VECTOR private".
    Session ends on "That's all VECTOR" or 45s silence.
    Called from autonomous_loop._observe_tick() every 0.5s.
    listen_tick() is non-blocking and never raises (RULE 2).
    """

    def __init__(self):
        self._wake = None
        self._stt = None
        self._tts = None
        self._lang = None
        self._gateway = None
        self._context = None
        self._wake_task: asyncio.Task | None = None
        self._session_active = False
        self._last_speech_time: float = 0.0
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

    def _get_gateway(self):
        if self._gateway is None:
            from core.loop.permission_gateway import PermissionGateway
            self._gateway = PermissionGateway()
        return self._gateway

    async def listen_tick(self) -> None:
        """
        Called every 0.5s from observe_loop. Non-blocking.
        Starts a background wake-word listener if not already running.
        When wake word fires, handle_voice_input() takes over.
        Never raises (RULE 2).
        """
        try:
            if self._wake is None:
                return
            # Spin up wake-word background task once
            if self._wake_task is None or self._wake_task.done():
                self._wake_task = asyncio.create_task(self._wake_and_handle())
        except Exception as e:
            logger.error(f"[VECTOR][voice] listen_tick error: {e}")

    async def _wake_and_handle(self) -> None:
        """Background task: wait for wake word, then handle voice input."""
        try:
            detected = await self._wake.listen_for_wake()
            if detected:
                await self.handle_voice_input()
        except Exception as e:
            logger.error(f"[VECTOR][voice] _wake_and_handle error: {e}")

    def _is_end_phrase(self, text: str) -> bool:
        return text.strip().lower() in _END_PHRASES

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

        try:
            while self._session_active:
                # Timeout check
                if time.time() - self._last_speech_time > _SILENCE_TIMEOUT_SEC:
                    logger.info("[VECTOR][voice] 45s silence — session closed")
                    self._session_active = False
                    break

                # 1. Transcribe
                text = ""
                if self._stt:
                    duration = CONFIG.get("voice", {}).get("record_duration_sec", 5.0)
                    text = await asyncio.to_thread(self._stt.record_and_transcribe, duration_sec=duration)
                if not text:
                    await asyncio.sleep(0.5)
                    continue

                self._last_speech_time = time.time()

                # End phrase check
                if self._is_end_phrase(text):
                    logger.info("[VECTOR][voice] End phrase — session closed")
                    if self._tts:
                        await asyncio.to_thread(self._tts.speak, "Goodbye.", lang="en")
                    self._session_active = False
                    break

                logger.info(f"[VECTOR][voice] TRANSCRIBE: '{text}'")

                # 2. Detect language
                lang = "en"
                if self._lang:
                    lang = self._lang.detect(text)

                # 3. RULE 1 — session_hydration_prompt before LLM call (cached instance)
                if self._context is None:
                    from core.loop.context_engine import ContextEngine
                    self._context = ContextEngine()
                hydration = self._context.session_hydration_prompt()

                # 4. Classify intent via Ollama vector-ambient
                intent = await self._classify_intent(text, hydration)
                action_type = intent.get("action_type", "search_web")
                params = intent.get("params", {"query": text})

                logger.info(f"[VECTOR][voice] THINK: {action_type} {params}")

                # 5. RULE 3 — all actions through permission_gateway
                from core.loop.permission_gateway import Action
                gw = self._get_gateway()
                action = Action(action_type=action_type, params=params, proposed_by="voice")
                result = await gw.execute(action)

                # 6. Speak response
                response_text = result.get("message", f"Done: {action_type}")
                logger.info(f"[VECTOR][voice] SPEAK: '{response_text}'")
                if self._tts:
                    await asyncio.to_thread(self._tts.speak, response_text, lang=lang)

        except Exception as e:
            logger.error(f"[VECTOR][voice] handle_voice_input error: {e}")
        finally:
            self._session_active = False

    async def _classify_intent(self, text: str, hydration: str) -> dict:
        """Call vector-ambient model to classify intent → {action_type, params}."""
        try:
            import httpx
            ollama_host = CONFIG["ollama_host"]
            model = CONFIG["models"]["ambient"]
            prompt = (
                f"{hydration}\n\n"
                f"User said: {text}\n\n"
                "Classify into JSON: {\"action_type\": \"...\", \"params\": {...}}\n"
                "action_type must be one of: search_web, set_timer, play_music, "
                "take_screenshot, check_weather, check_attendance, set_reminder, "
                "read_calendar, create_calendar_event, commit_code, download_file\n"
                "Respond with ONLY valid JSON, no explanation."
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{ollama_host}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "")
                import json
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start != -1 and end > start:
                    return json.loads(raw[start:end])
        except Exception as e:
            logger.warning(f"[VECTOR][voice] Intent classification failed: {e} — defaulting to respond")
        return {"action_type": "respond", "params": {"message": "I didn't catch that."}}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        listener = AmbientListener()
        # Test that all components initialized
        components = {
            "wake": listener._wake is not None,
            "stt": listener._stt is not None,
            "tts": listener._tts is not None,
            "lang": listener._lang is not None,
        }
        logger.info(f"[VECTOR][voice] Components: {components}")

        # Test listen_tick doesn't crash (no mic in CI — just verifies it creates a task)
        await listener.listen_tick()
        # Cancel the background wake task immediately
        if listener._wake_task and not listener._wake_task.done():
            listener._wake_task.cancel()
            try:
                await listener._wake_task
            except asyncio.CancelledError:
                pass

        all_ok = all(components.values())
        print(f"✅ ambient_listener OK {components}" if all_ok else f"⚠️ ambient_listener partial {components}")

    asyncio.run(_smoke())
