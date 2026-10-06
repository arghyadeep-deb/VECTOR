# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Audio transcription tool — transcribe audio via OpenAI Whisper."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from vectorcode.src.vc_core.registry import ToolRegistry
from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec

_SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm"}
_MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

@ToolRegistry.register("audio_transcribe")
class AudioTranscribeTool(BaseTool):
    """Transcribe audio files using OpenAI Whisper or a local provider."""

    tool_id = "audio_transcribe"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="audio_transcribe",
            description=(
                "Transcribe an audio file to text."
                " Supports mp3, wav, m4a, ogg, flac, and webm formats."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the audio file to transcribe.",
                    },
                    "language": {
                        "type": "string",
                        "description": "Optional language code (e.g. 'en', 'es').",
                    },
                    "provider": {
                        "type": "string",
                        "description": (
                            "Transcription provider: 'openai' or 'local'."
                            " Default 'openai'."
                        ),
                    },
                },
                "required": ["file_path"],
            },
            category="media",
            required_capabilities=["file:read"],
        )

    def execute(self, **params: Any) -> ToolResult:
        file_path = params.get("file_path", "")
        if not file_path:
            return ToolResult(
                tool_name="audio_transcribe",
                content="No file_path provided.",
                success=False,
            )

        path = Path(file_path)

        # OWNER DECISION: this tool has no configured allowed-root policy, so
        # any non-sensitive audio file readable by the process can be uploaded
        # to the selected provider. Align its root confinement with the open
        # file_read/file_write policy decision rather than inventing a new root.
        try:
            resolved_path = path.resolve(strict=True)
        except OSError as exc:
            return ToolResult(
                tool_name="audio_transcribe",
                content=f"Cannot resolve file: {exc}",
                success=False,
            )

        if not resolved_path.is_file():
            return ToolResult(
                tool_name="audio_transcribe",
                content=f"File not found: {file_path}",
                success=False,
            )

        from vectorcode.src.vc_security.file_policy import is_sensitive_file

        if is_sensitive_file(str(path)) or is_sensitive_file(str(resolved_path)):
            return ToolResult(
                tool_name="audio_transcribe",
                content="Access denied: sensitive files cannot be transcribed.",
                success=False,
            )

        path = resolved_path

        # Validate format
        suffix = path.suffix.lower()
        if suffix not in _SUPPORTED_FORMATS:
            return ToolResult(
                tool_name="audio_transcribe",
                content=(
                    f"Unsupported audio format '{suffix}'."
                    f" Supported: {', '.join(sorted(_SUPPORTED_FORMATS))}."
                ),
                success=False,
            )

        # Validate file size
        try:
            file_size = path.stat().st_size
        except OSError as exc:
            return ToolResult(
                tool_name="audio_transcribe",
                content=f"Cannot stat file: {exc}",
                success=False,
            )

        if file_size > _MAX_FILE_SIZE_BYTES:
            return ToolResult(
                tool_name="audio_transcribe",
                content=(
                    f"File too large: {file_size} bytes"
                    f" (max {_MAX_FILE_SIZE_BYTES} bytes / 25 MB)."
                ),
                success=False,
            )

        provider = params.get("provider", "openai")
        language = params.get("language")

        if provider == "local":
            return ToolResult(
                tool_name="audio_transcribe",
                content="Local transcription provider is not yet implemented.",
                success=False,
            )

        if provider != "openai":
            return ToolResult(
                tool_name="audio_transcribe",
                content=(
                    f"Unsupported provider '{provider}'. Supported: 'openai', 'local'."
                ),
                success=False,
            )

        # OWNER DECISION: direct OpenAI Whisper billing conflicts with VECTOR's
        # free-tier-only runtime rule. Decide whether to disable this legacy
        # provider or route transcription through the approved local/free stack.
        # OpenAI Whisper provider
        try:
            import openai
        except ImportError:
            return ToolResult(
                tool_name="audio_transcribe",
                content=(
                    "openai package not installed. Install with: pip install openai"
                ),
                success=False,
            )

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return ToolResult(
                tool_name="audio_transcribe",
                content="No API key configured. Set OPENAI_API_KEY.",
                success=False,
            )

        try:
            client = openai.OpenAI()
            kwargs: dict[str, Any] = {"model": "whisper-1"}
            if language:
                kwargs["language"] = language

            with path.open("rb") as f:
                kwargs["file"] = f
                transcription = client.audio.transcriptions.create(**kwargs)

            text = transcription.text
            metadata: dict[str, Any] = {
                "file_path": str(path.resolve()),
                "provider": provider,
            }
            if language:
                metadata["language"] = language
            if hasattr(transcription, "duration"):
                metadata["duration_ms"] = int(transcription.duration * 1000)

            return ToolResult(
                tool_name="audio_transcribe",
                content=text,
                success=True,
                metadata=metadata,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="audio_transcribe",
                content=f"Transcription error: {exc}",
                success=False,
            )

__all__ = ["AudioTranscribeTool"]
