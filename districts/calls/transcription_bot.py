
import sys
import uuid
import tempfile
import wave
import asyncio
from pathlib import Path
from typing import Optional

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

class TranscriptionBot(AgentBase):
    """
    Transcribes audio to text using Whisper and provides
    summarization capabilities via Ollama.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "TranscriptionBot", "calls")
        if ghost:
            self.inherit_ghost(ghost)

        self._whisper_model = CONFIG.get("voice", {}).get("whisper_model", "base")
        self._sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
        self._whisper = None
        self._whisper_init_attempted = False
        # Whisper is loaded lazily on first real transcription, NOT here:
        # whisper.load_model() is heavy (and downloads ~140MB on first ever use),
        # so eager loading in __init__ made every TranscriptionBot() construction
        # block for seconds-to-minutes — flaky under the 60s test timeout.
        logger.info(f"[VECTOR][transcription_bot] TranscriptionBot initialized - model: {self._whisper_model}")

    def _init_whisper(self) -> None:
        """Lazily load the Whisper model once, on first use."""
        if self._whisper is not None or self._whisper_init_attempted:
            return
        self._whisper_init_attempted = True
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
        # Check the file first so a missing path fails fast without paying the
        # cost of loading the Whisper model.
        audio_file = Path(audio_path)
        if not audio_file.exists():
            return {"status": "error", "message": "Audio file not found"}

        self._init_whisper()
        if not self._whisper:
            return {"status": "error", "message": "Whisper not available"}

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
                logger.debug("[VECTOR] suppressed exception", exc_info=True)

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
            import asyncio as _asyncio
            import concurrent.futures as _cf
            from core.inference.provider_client import ProviderClient as _PC

            async def _call():
                r = await _PC().chat(
                    messages=[{"role": "user", "content": prompt}],
                    tier="summarization",
                    temperature=0.4,
                    max_tokens=600,
                    caller_id="transcription_bot",
                )
                return r.content

            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                summary = pool.submit(_asyncio.run, _call()).result(timeout=60).strip()

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
            import asyncio as _asyncio
            import concurrent.futures as _cf
            from core.inference.provider_client import ProviderClient as _PC

            async def _call():
                r = await _PC().chat(
                    messages=[{"role": "user", "content": prompt}],
                    tier="summarization",
                    temperature=0.3,
                    max_tokens=600,
                    caller_id="transcription_bot",
                )
                return r.content

            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                actions_text = pool.submit(_asyncio.run, _call()).result(timeout=30).strip()

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

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = [
            "transcribe_audio", "transcribe_live", "summarize_transcript", "extract_action_items",
        ]

        if task_type == "transcribe_audio":
            return self.transcribe_audio(p.get("audio_path", ""), p.get("language"))
        if task_type == "transcribe_live":
            result = await self.transcribe_live(p.get("duration_sec", 5.0))
            return result
        if task_type == "summarize_transcript":
            return self.summarize_transcript(p.get("text", ""), p.get("style", "concise"))
        if task_type == "extract_action_items":
            items = self.extract_action_items(p.get("text", ""))
            return {"status": "ok", "action_items": items}

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    bot = TranscriptionBot()

    print(f"Whisper model: {bot._whisper_model}")
    print(f"Status: {'ready' if bot._whisper else 'unavailable'}")

    print("✅ transcription_bot.py OK")
