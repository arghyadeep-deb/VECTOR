# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Image generation tool — generate images via OpenAI DALL-E."""

from __future__ import annotations

import os
import tempfile
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
        output: Path | None = None
        if output_path:
            # OWNER DECISION: output paths have no configured allowed-root
            # policy. Align this with file_write's open confinement decision;
            # do not silently choose a root that may break legitimate callers.
            output = Path(output_path).resolve()
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

        # OWNER DECISION: direct DALL-E billing conflicts with VECTOR's
        # free-tier-only runtime rule. Decide whether to disable this legacy
        # provider or route generation through the approved provider stack.
        try:
            import openai
        except ImportError:
            return ToolResult(
                tool_name="image_generate",
                content=(
                    "openai package not installed. Install with: pip install openai"
                ),
                success=False,
            )

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return ToolResult(
                tool_name="image_generate",
                content="No API key configured. Set OPENAI_API_KEY.",
                success=False,
            )

        try:
            client = openai.OpenAI()
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                n=1,
            )
            url = response.data[0].url
        except Exception as exc:
            return ToolResult(
                tool_name="image_generate",
                content=f"Image generation error: {exc}",
                success=False,
            )

        # Optionally save to file
        if output_path:
            try:
                import httpx

                resp = httpx.get(url, follow_redirects=True, timeout=60.0)
                resp.raise_for_status()
                if output is None:  # pragma: no cover - guarded by output_path
                    raise ValueError("No output path")
                output.parent.mkdir(parents=False, exist_ok=True)
                temp_path: str | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        dir=output.parent,
                        prefix=f".{output.name}.",
                        suffix=".tmp",
                        delete=False,
                    ) as temp_file:
                        temp_path = temp_file.name
                        temp_file.write(resp.content)
                        temp_file.flush()
                        os.fsync(temp_file.fileno())
                    os.replace(temp_path, output)
                    temp_path = None
                finally:
                    if temp_path is not None:
                        try:
                            os.unlink(temp_path)
                        except FileNotFoundError:
                            pass
            except Exception as exc:
                return ToolResult(
                    tool_name="image_generate",
                    content=(f"Image generated but failed to save: {exc}. URL: {url}"),
                    success=False,
                    metadata={"url": url, "size": size, "provider": provider},
                )

        return ToolResult(
            tool_name="image_generate",
            content=url,
            success=True,
            metadata={"url": url, "size": size, "provider": provider},
        )

__all__ = ["ImageGenerateTool"]
