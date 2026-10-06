"""STT tool — speech-to-text transcription with multiple providers."""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


async def transcribe_audio(
    audio_path: str,
    *,
    provider: str = "local",
    language: str = "en",
) -> dict:
    """Transcribe audio file to text."""
    try:
        if provider == "local":
            try:
                import whisper
                model = whisper.load_model("base")
                result = model.transcribe(audio_path, language=language)
                return {"success": True, "text": result["text"].strip(), "provider": "local"}
            except ImportError:
                return {"error": "whisper not installed. Run: pip install openai-whisper", "success": False}

        elif provider == "openai":
            import httpx
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key: return {"error": "OPENAI_API_KEY not set", "success": False}
            async with httpx.AsyncClient() as c:
                with open(audio_path, "rb") as f:
                    resp = await c.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        files={"file": f},
                        data={"model": "whisper-1", "language": language},
                    )
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "text": data.get("text", "").strip(), "provider": "openai"}

        elif provider == "groq":
            import httpx
            api_key = os.environ.get("GROQ_API_KEY", "")
            if not api_key: return {"error": "GROQ_API_KEY not set", "success": False}
            async with httpx.AsyncClient() as c:
                with open(audio_path, "rb") as f:
                    resp = await c.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        files={"file": f},
                        data={"model": "whisper-large-v3", "language": language},
                    )
                resp.raise_for_status()
                data = resp.json()
                return {"success": True, "text": data.get("text", "").strip(), "provider": "groq"}

        return {"error": f"Unknown provider: {provider}", "success": False}

    except Exception as e:
        return {"error": str(e), "success": False}
