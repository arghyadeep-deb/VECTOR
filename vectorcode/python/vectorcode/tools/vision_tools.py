# Ported from GitHub/NousResearch_hermes-agent/repo/tools/vision_tools.py
"""Vision analysis tool — analyze images using multimodal models."""
import base64
import json
import os
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from .registry import registry


def vision_analyze(
    image_path: Optional[str] = None,
    image_url: Optional[str] = None,
    prompt: str = "Describe this image in detail.",
    context: Any = None,
) -> str:
    """Analyze an image using a vision-capable model."""
    if not image_path and not image_url:
        return json.dumps({"error": "Provide image_path or image_url"})

    # Build image data
    if image_path:
        p = Path(image_path).expanduser()
        if not p.exists():
            return json.dumps({"error": f"Image not found: {image_path}"})
        try:
            data = base64.b64encode(p.read_bytes()).decode()
            ext = p.suffix.lower().lstrip(".")
            media_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                          "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
            image_source = {"type": "base64", "media_type": media_type, "data": data}
        except Exception as e:
            return json.dumps({"error": f"Failed to read image: {e}"})
    else:
        image_source = {"type": "url", "url": image_url}

    # Try Anthropic vision
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            content = [
                {"type": "image", "source": image_source},
                {"type": "text", "text": prompt},
            ]
            msg = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=1024,
                messages=[{"role": "user", "content": content}],
            )
            return json.dumps({"description": msg.content[0].text})
        except Exception as e:
            logger.warning(f"Anthropic vision failed: {e}")

    return json.dumps({"error": "No vision-capable provider available. Set ANTHROPIC_API_KEY."})


registry.register(
    name="vision_analyze",
    handler=vision_analyze,
    schema={
        "description": "Analyze an image using a vision-capable model.",
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Local path to image file"},
                "image_url": {"type": "string", "description": "URL of image"},
                "prompt": {"type": "string", "description": "What to analyze (default: describe the image)"},
            },
        },
    },
    toolset="research",
    risk_level="safe",
    emoji="👁️",
)
