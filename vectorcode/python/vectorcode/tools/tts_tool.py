"""TTS tool — text-to-speech with multiple provider backends."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def text_to_speech(
    text: str,
    *,
    provider: str = "edge",
    voice: str = "",
    output_path: Optional[str] = None,
) -> dict:
    """Convert text to speech using the specified provider."""
    try:
        if provider == "edge":
            import edge_tts
            voice = voice or "en-US-JennyNeural"
            communicate = edge_tts.Communicate(text, voice)
            path = output_path or "/tmp/vector_tts.mp3"
            await communicate.save(path)
            return {"success": True, "path": path, "provider": "edge"}

        elif provider == "openai":
            import httpx
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key: return {"error": "OPENAI_API_KEY not set", "success": False}
            voice = voice or "alloy"
            async with httpx.AsyncClient() as c:
                resp = await c.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": "tts-1", "input": text, "voice": voice},
                )
                path = output_path or "/tmp/vector_tts.mp3"
                with open(path, "wb") as f:
                    f.write(resp.content)
                return {"success": True, "path": path, "provider": "openai"}

        else:
            return {"error": f"Unknown provider: {provider}", "success": False}

    except ImportError as e:
        return {"error": f"Missing dependency: {e}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


import os
