import sys
import uuid
import tempfile
import wave
import asyncio
from pathlib import Path
from typing import Optional
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class TranscriptionBot(AgentBase):
    """
    Transcribes audio to text using Whisper and provides
    summarization capabilities via Ollama.
    """

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "TranscriptionBot", "calls")
        if ghost:
            self.inherit_ghost(ghost)

        self._whisper_model = CONFIG.get("voice", {}).get("whisper_model", "base")
        self._sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
        self._whisper = None
        self._init_whisper()
        logger.info(f"[VECTOR][transcription_bot] TranscriptionBot initialized - model: {self._whisper_model}")

    def _init_whisper(self) -> None:
        """Initialize Whisper model."""
        try:
            import whisper
            self._whisper = whisper.load_model(self._whisper_model)
            logger.info(f"[VECTOR][transcription_bot] Whisper model loaded: {self._whisper_model}")
        except ImportError:
            logger.warning("[VECTOR][transcription_bot] whisper not installed - transcription disabled")
        except Exception as e:
            logger.error(f"[VECTOR][transcription_bot] Whisper init failed: {e}")

    def transcribe_audio(self, audio_path: str, language: Optional[str] = None) -> dict:
        """
        Transcribe audio file to text.
        Returns dict with transcription and metadata.
        """
        if not self._whisper:
            return {"status": "error", "message": "Whisper not available"}

        audio_file = Path(audio_path)
        if not audio_file.exists():
            return {"status": "error", "message": "Audio file not found"}

        try:
            import whisper

            options = {
                "fp16": False,
                "verbose": False
            }
            if language:
                options["language"] = language

            result = self._whisper.transcribe(str(audio_file), **options)

            transcription = {
                "status": "success",
                "text": result["text"].strip(),
                "language": result.get("language", "unknown"),
                "duration": result.get("duration", 0),
                "segments": [
                    {
                        "start": seg["start"],
                        "end": seg["end"],
                        "text": seg["text"].strip()
                    }
                    for seg in result.get("segments", [])
                ]
            }

            self.award_points(20, f"audio_transcribed_{audio_file.stem}")
            logger.info(f"[VECTOR][transcription_bot] Transcribed: {audio_file.name} ({transcription['duration']:.1f}s)")

            return transcription

        except Exception as e:
            logger.error(f"[VECTOR][transcription_bot] Transcription failed: {e}")
            return {"status": "error", "message": str(e)}

    async def transcribe_live(self, duration_sec: float = 5.0) -> dict:
        """
        Record and transcribe audio from microphone.
        Duration: how many seconds to record.
        """
        import numpy as np

        if not self._whisper:
            return {"status": "error", "message": "Whisper not available"}

        duration_sec = min(duration_sec, 30.0)

        try:
            import sounddevice as sd

            logger.info(f"[VECTOR][transcription_bot] Recording for {duration_sec}s...")

            audio_data = []
            sample_rate = self._sample_rate
            total_samples = int(sample_rate * duration_sec)

            def callback(indata, frames, time, status):
                if status:
                    logger.warning(f"[VECTOR][transcription_bot] Recording status: {status}")
                audio_data.append(indata.copy())

            with sd.InputStream(samplerate=sample_rate, channels=1, callback=callback):
                await asyncio.sleep(duration_sec)

            audio_array = np.concatenate(audio_data, axis=0)
            audio_array = audio_array.flatten().astype(np.float32)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = Path(f.name)
                with wave.open(str(wav_path), 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes((audio_array * 32767).astype(np.int16).tobytes())

            result = self.transcribe_audio(str(wav_path))

            try:
                wav_path.unlink()
            except Exception:
                pass

            if result.get("status") == "success":
                self.award_points(15, "live_audio_transcribed")

            return result

        except ImportError:
            return {"status": "error", "message": "sounddevice not installed"}
        except Exception as e:
            logger.error(f"[VECTOR][transcription_bot] Live transcription failed: {e}")
            return {"status": "error", "message": str(e)}

    def summarize_transcript(self, text: str, style: str = "concise") -> dict:
        """
        Summarize transcribed text using Ollama.
        Styles: concise, detailed, bullet_points, executive
        """
        style_instructions = {
            "concise": "Provide a brief 2-3 sentence summary",
            "detailed": "Provide a comprehensive summary with key details",
            "bullet_points": "Summarize in 5-7 bullet points covering main topics",
            "executive": "Provide an executive summary suitable for business context"
        }

        instruction = style_instructions.get(style, style_instructions["concise"])

        prompt = f"""{instruction}.

Transcript:
{text}

Summary:"""

        try:
            import httpx

            ollama_host = CONFIG["ollama_host"]
            if not ollama_host.startswith("http"):
                ollama_host = "http://" + ollama_host

            model = CONFIG["models"]["focus"]

            response = httpx.post(
                f"{ollama_host}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()
            summary = result.get("response", "").strip()

            self.award_points(10, "transcript_summarized")
            logger.info(f"[VECTOR][transcription_bot] Summarized transcript ({style})")

            return {
                "status": "success",
                "original_length": len(text.split()),
                "summary_length": len(summary.split()),
                "summary": summary,
                "style": style
            }

        except Exception as e:
            logger.error(f"[VECTOR][transcription_bot] Summarization failed: {e}")
            return {"status": "error", "message": str(e)}

    def extract_action_items(self, text: str) -> list[dict]:
        """
        Extract action items and tasks from transcribed text.
        """
        prompt = f"""Extract all action items, tasks, and commitments from this transcript.
For each item include:
1. Task description
2. Who it's assigned to (if mentioned)
3. Any deadline mentioned

Format as a numbered list. If no action items, say "No action items found."

Transcript:
{text}
"""

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
            actions_text = result.get("response", "").strip()

            action_items = self._parse_action_items(actions_text)

            self.award_points(5, "action_items_extracted")
            return action_items

        except Exception as e:
            logger.error(f"[VECTOR][transcription_bot] Action item extraction failed: {e}")
            return []

    def _parse_action_items(self, text: str) -> list[dict]:
        """Parse LLM response into structured action items."""
        items = []
        lines = text.split("\n")

        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                content = line.lstrip("0123456789.- )")
                if content and "no action items" not in content.lower():
                    items.append({
                        "description": content,
                        "status": "pending",
                        "extracted_at": self._get_timestamp()
                    })

        return items

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    bot = TranscriptionBot()

    print(f"Whisper model: {bot._whisper_model}")
    print(f"Status: {'ready' if bot._whisper else 'unavailable'}")

    print("✅ transcription_bot.py OK")
