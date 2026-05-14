import sys
import uuid
import asyncio
from pathlib import Path
from typing import Optional
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


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

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "VoiceResponder", "calls")
        if ghost:
            self.inherit_ghost(ghost)

        self._voice_config = CONFIG.get("voice", {})
        self._kokoro_dir = Path(self._voice_config.get("kokoro_model_dir", "./models/kokoro"))
        self._tts_available = self._check_tts()
        self._response_history: list[dict] = []
        logger.info(f"[VECTOR][voice_responder] VoiceResponder initialized - TTS: {self._tts_available}")

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

    def generate_response(self, text: str, context: dict = None) -> dict:
        """
        Generate text response using Ollama.
        Context can include conversation history, user preferences, etc.
        """
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
            import httpx

            ollama_host = CONFIG["ollama_host"]
            if not ollama_host.startswith("http"):
                ollama_host = "http://" + ollama_host

            model = CONFIG["models"]["focus"]

            response = httpx.post(
                f"{ollama_host}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            response_text = result.get("response", "").strip()

            response_entry = {
                "id": str(uuid.uuid4()),
                "input": text,
                "output": response_text,
                "tone": tone,
                "timestamp": self._get_timestamp()
            }
            self._response_history.append(response_entry)

            self.award_points(5, "voice_response_generated")
            logger.info(f"[VECTOR][voice_responder] Generated response: {response_text[:50]}...")

            return {
                "status": "success",
                "text": response_text,
                "response_id": response_entry["id"]
            }

        except Exception as e:
            logger.error(f"[VECTOR][voice_responder] Response generation failed: {e}")
            return {"status": "error", "message": str(e)}

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

        if output_path is None:
            output_dir = Path(__file__).parent.parent.parent.parent / "data" / "voice_output"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"response_{uuid.uuid4().hex[:8]}.wav")

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
            logger.info(f"[VECTOR][voice_responder] TTS generated: {output_path}")

            return {
                "status": "success",
                "audio_path": output_path,
                "duration_sec": len(audio_samples) / sample_rate,
                "voice": voice
            }

        except ImportError:
            return {"status": "error", "message": "kokoro_onnx not installed"}
        except Exception as e:
            logger.error(f"[VECTOR][voice_responder] TTS failed: {e}")
            return {"status": "error", "message": str(e)}

    async def respond_to_audio(self, audio_path: str, context: dict = None) -> dict:
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
        p = task.get("params", {})
        if p.get("text"):
            result = self.generate_response(p["text"], p.get("context"))
            return {"status": "ok", **result}
        return {"status": "ok", "agent": self.name}


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
