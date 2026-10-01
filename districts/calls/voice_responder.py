
import sys
import uuid
import asyncio
from pathlib import Path
from typing import Optional

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

_MAX_RESPONSE_HISTORY = 1000

class VoiceResponder(AgentBase):
    """
    Generates text responses and converts them to speech
    for voice interaction pipelines.
    """

    VOICE_OPTIONS = {
        "default": {"speed": 1.0, "pitch": 0},
        "fast": {"speed": 1.2, "pitch": 0},
        "slow": {"speed": 0.8, "pitch": 0},
        "happy": {"speed": 1.1, "pitch": 2},
        "serious": {"speed": 0.9, "pitch": -1}
    }

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "VoiceResponder", "calls")
        self.capabilities = ["calls", "generate_response", "get_available_voices", "get_response_history", "respond", "respond_to_audio", "text_to_speech", "voice"]
        if ghost:
            self.inherit_ghost(ghost)

        self._ensure_legacy_event_loop()
        self._voice_config = CONFIG.get("voice", {})
        self._kokoro_dir = Path(self._voice_config.get("kokoro_model_dir", "./models/kokoro"))
        self._tts_available = self._check_tts()
        self._response_history: list[dict] = []
        logger.info("[VECTOR][voice_responder] VoiceResponder initialized - TTS: {}", self._tts_available)

    @staticmethod
    def _ensure_legacy_event_loop() -> None:
        """Keep sync callers using get_event_loop().run_until_complete() working."""
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def _check_tts(self) -> bool:
        """Check if TTS (Kokoro) is available."""
        if self._kokoro_dir.exists():
            return True
        try:
            import kokoro_onnx
            return True
        except ImportError:
            logger.warning("[VECTOR][voice_responder] Kokoro TTS not available")
            return False

    def generate_response(self, text: str, context: dict | None = None) -> dict:
        """
        Generate text response using Ollama.
        Context can include conversation history, user preferences, etc.
        """
        # Enforce history bound unconditionally so it holds even when the LLM call fails.
        if len(self._response_history) > _MAX_RESPONSE_HISTORY:
            del self._response_history[:-_MAX_RESPONSE_HISTORY]

        context = context or {}
        conversation_history = context.get("history", [])
        user_name = context.get("user_name", "User")
        tone = context.get("tone", "friendly")

        history_text = ""
        if conversation_history:
            history_text = "\n".join([
                f"{msg.get('speaker', 'Unknown')}: {msg.get('text', '')}"
                for msg in conversation_history[-5:]
            ])

        tone_instruction = self._get_tone_instruction(tone)

        prompt = f"""{tone_instruction}

{"Previous conversation:" if history_text else ""}
{history_text}

{user_name}: {text}

V.E.C.T.O.R. Response:"""

        try:
            import asyncio as _asyncio
            import concurrent.futures as _cf
            from core.inference.provider_client import ProviderClient as _PC

            async def _call():
                r = await _PC().chat(
                    messages=[{"role": "user", "content": prompt}],
                    tier="conversation",
                    temperature=0.7,
                    max_tokens=400,
                    caller_id="voice_responder",
                    # Caller speech is in the prompt: local Ollama only.
                    sensitive=True,
                    district="calls",
                )
                return r.content

            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                response_text = pool.submit(_asyncio.run, _call()).result(timeout=30).strip()

            response_entry = {
                "id": str(uuid.uuid4()),
                "input": text,
                "output": response_text,
                "tone": tone,
                "timestamp": self._get_timestamp()
            }
            self._response_history.append(response_entry)
            if len(self._response_history) > _MAX_RESPONSE_HISTORY:
                del self._response_history[:-_MAX_RESPONSE_HISTORY]

            self.award_points(5, "voice_response_generated")
            logger.info("[VECTOR][voice_responder] Generated response ({} chars)", len(response_text))

            return {
                "status": "success",
                "text": response_text,
                "response_id": response_entry["id"]
            }

        except Exception as e:
            # Provider errors can echo the prompt (caller speech): type only.
            logger.error("[VECTOR][voice_responder] Response generation failed: {}", type(e).__name__)
            # Canned reply: must not echo the caller's words back, and must
            # never be reported as a real generated answer.
            response_text = "Sorry, I could not generate a reply right now."
            response_entry = {
                "id": str(uuid.uuid4()),
                "input": text,
                "output": response_text,
                "tone": tone,
                "timestamp": self._get_timestamp(),
                "fallback": True,
            }
            self._response_history.append(response_entry)
            if len(self._response_history) > _MAX_RESPONSE_HISTORY:
                del self._response_history[:-_MAX_RESPONSE_HISTORY]
            return {
                "status": "degraded",
                "text": response_text,
                "response_id": response_entry["id"],
                "degraded": True,
                "warning": f"LLM unavailable ({type(e).__name__})",
            }

    def _get_tone_instruction(self, tone: str) -> str:
        """Get tone instruction for LLM."""
        instructions = {
            "friendly": "Respond in a warm, friendly manner with casual language",
            "professional": "Respond professionally with clear, concise language",
            "casual": "Respond casually, like chatting with a friend",
            "formal": "Respond formally with proper grammar and structure",
            "empathetic": "Respond with empathy and emotional understanding",
            "humorous": "Respond with light humor when appropriate"
        }
        return instructions.get(tone, instructions["friendly"])

    async def text_to_speech(self, text: str, voice: str = "default", output_path: Optional[str] = None) -> dict:
        """
        Convert text to speech using Kokoro TTS.
        Returns path to generated audio file.
        """
        if not self._tts_available:
            return {"status": "error", "message": "TTS not available"}

        voice_settings = self.VOICE_OPTIONS.get(voice, self.VOICE_OPTIONS["default"])

        from core.runtime_paths import data_path

        output_dir = data_path("voice_output")
        output_dir.mkdir(parents=True, exist_ok=True)
        if output_path is None:
            output_path = str(output_dir / f"response_{uuid.uuid4().hex[:8]}.wav")
        else:
            # CWE-22: params/context-supplied path must stay inside voice_output.
            try:
                resolved = Path(output_path).resolve()
                if not resolved.is_relative_to(output_dir.resolve()):
                    raise ValueError("outside voice_output")
            except (ValueError, OSError):
                logger.warning("[VECTOR][voice_responder] rejected output_path outside voice_output")
                return {"status": "error", "message": "output_path must be inside the voice_output directory"}
            output_path = str(resolved)

        try:
            import kokoro_onnx
            import numpy as np

            model = kokoro_onnx.load_model(
                voice,
                repo_id=kokoro_onnx.HF_REPO,
                filename=kokoro_onnx.MODEL_FILENAME,
            )

            speed = voice_settings["speed"]
            audio_samples, sample_rate = model.create_audio(text, speed=speed)

            import scipy.io.wavfile as wavfile
            audio_int16 = (audio_samples * 32767).astype(np.int16)

            wavfile.write(output_path, sample_rate, audio_int16)

            self.award_points(10, "tts_generated")
            logger.info("[VECTOR][voice_responder] TTS generated: {}", Path(output_path).name)

            return {
                "status": "success",
                "audio_path": output_path,
                "duration_sec": len(audio_samples) / sample_rate,
                "voice": voice
            }

        except ImportError:
            return {"status": "error", "message": "kokoro_onnx not installed"}
        except Exception as e:
            logger.error("[VECTOR][voice_responder] TTS failed: {}", type(e).__name__)
            return {"status": "error", "message": str(e)}

    async def respond_to_audio(self, audio_path: str, context: dict | None = None) -> dict:
        """
        Full pipeline: transcribe audio, generate response, convert to speech.
        Returns transcription, response text, and audio file path.
        """
        from .transcription_bot import TranscriptionBot

        bot = TranscriptionBot()

        transcription = bot.transcribe_audio(audio_path)
        if transcription.get("status") != "success":
            return {
                "status": "error",
                "message": "Transcription failed",
                "details": transcription
            }

        text = transcription["text"]

        response = self.generate_response(text, context)
        if response.get("status") != "success":
            return {
                "status": "error",
                "message": "Response generation failed",
                "transcription": text
            }

        tts_result = await self.text_to_speech(
            response["text"],
            voice=context.get("voice", "default") if context else "default",
            output_path=context.get("output_path") if context else None
        )

        result = {
            "status": "success",
            "transcription": text,
            "response_text": response["text"],
            "response_id": response["response_id"]
        }

        if tts_result.get("status") == "success":
            result["audio_path"] = tts_result["audio_path"]
            result["audio_duration"] = tts_result["duration_sec"]

        self.award_points(20, "full_pipeline_completed")
        return result

    def get_available_voices(self) -> list[str]:
        """Get list of available TTS voices."""
        return list(self.VOICE_OPTIONS.keys())

    def get_response_history(self, limit: int = 20) -> list[dict]:
        """Get recent response history."""
        return self._response_history[-limit:]

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = [
            "generate_response", "text_to_speech", "respond_to_audio",
            "get_available_voices", "get_response_history",
        ]

        if task_type == "generate_response":
            return self.generate_response(p.get("text", ""), p.get("context"))
        if task_type == "text_to_speech":
            return await self.text_to_speech(p.get("text", ""), p.get("voice", "default"), p.get("output_path"))
        if task_type == "respond_to_audio":
            return await self.respond_to_audio(p.get("audio_path", ""), p.get("context"))
        if task_type == "get_available_voices":
            return {"status": "ok", "voices": self.get_available_voices()}
        if task_type == "get_response_history":
            return {"status": "ok", "history": self.get_response_history(p.get("limit", 20))}

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import asyncio

    async def test():
        responder = VoiceResponder()

        response = responder.generate_response(
            "Hello, how are you today?",
            context={"user_name": "Arghyadeep", "tone": "friendly"}
        )
        print(f"Response: {response.get('text', 'N/A')[:50]}...")

        print(f"Available voices: {responder.get_available_voices()}")

        print("✅ voice_responder.py OK")

    asyncio.run(test())
