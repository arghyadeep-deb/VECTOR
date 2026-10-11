# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Image generation tool — generate images via OpenAI DALL-E."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vectorcode.src.vc_core.registry import ToolRegistry
from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec

_VALID_SIZES = {"256x256", "512x512", "1024x1024"}

@ToolRegistry.register("image_generate")
class ImageGenerateTool(BaseTool):
    """Generate images from text descriptions via OpenAI DALL-E."""

    tool_id = "image_generate"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="image_generate",
            description=(
                "Generate an image from a text description. Returns the image URL."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Text description of the image to generate.",
                    },
                    "size": {
                        "type": "string",
                        "description": (
                            "Image size: '256x256', '512x512', or '1024x1024'."
                            " Default '1024x1024'."
                        ),
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Optional file path to save the image to.",
                    },
                    "provider": {
                        "type": "string",
                        "description": "Image generation provider. Default 'openai'.",
                    },
                },
                "required": ["prompt"],
            },
            category="media",
            required_capabilities=["network:fetch", "file:write"],
        )

    def execute(self, **params: Any) -> ToolResult:
        prompt = params.get("prompt", "")
        if not prompt:
            return ToolResult(
                tool_name="image_generate",
                content="No prompt provided.",
                success=False,
            )

        size = params.get("size", "1024x1024")
        if size not in _VALID_SIZES:
            return ToolResult(
                tool_name="image_generate",
                content=(
                    f"Invalid size '{size}'."
                    f" Must be one of: {', '.join(sorted(_VALID_SIZES))}."
                ),
                success=False,
            )

        provider = params.get("provider", "openai")
        output_path = params.get("output_path")
        if output_path:
            output = Path(output_path).resolve()
            from core.config import CONFIG

            allowed_root = Path(CONFIG["media"]["allowed_root"]).resolve()
            if output != allowed_root and not output.is_relative_to(allowed_root):
                return ToolResult(
                    tool_name="image_generate",
                    content="Path is outside the allowed media directory.",
                    success=False,
                )

            from vectorcode.src.vc_security.file_policy import is_sensitive_file

            if is_sensitive_file(str(output)):
                return ToolResult(
                    tool_name="image_generate",
                    content="Access denied: cannot write to a sensitive file.",
                    success=False,
                )

        if provider != "openai":
            return ToolResult(
                tool_name="image_generate",
                content=(
                    f"Unsupported provider '{provider}'. Only 'openai' is supported."
                ),
                success=False,
            )

        # Disabled by owner decision 2026-10-11: paid APIs conflict with the
        # free-tier-only VECTOR runtime rule.
        return ToolResult(
            tool_name="image_generate",
            content=(
                "OpenAI DALL-E is disabled because it requires a paid API, "
                "which conflicts with VECTOR's free-tier-only runtime rule."
            ),
            success=False,
        )

__all__ = ["ImageGenerateTool"]
