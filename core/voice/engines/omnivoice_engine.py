"""Lazy optional OmniVoice adapter for VECTOR Voice Studio."""
from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = ["OmniVoiceConfig", "OmniVoiceEngine"]


@dataclass(frozen=True)
class OmniVoiceConfig:
    enabled: bool = False
    model: str = "k2-fsa/OmniVoice"
    device: str = "cuda:0"
    dtype: str = "float16"
    live_allowed: bool = False
    unload_after_seconds: int = 300


class OmniVoiceEngine:
    """Optional high-quality studio TTS engine.

    The heavy package is imported only inside ``_load`` and only when enabled.
    """

    def __init__(self, config: OmniVoiceConfig | None = None):
        self.config = config or self.from_vector_config()
        self._model = None
        self._loaded_at = 0.0

    @classmethod
    def from_vector_config(cls) -> OmniVoiceConfig:
        try:
            from core.config import CONFIG
            voice = CONFIG.get("voice", {}) or {}
        except Exception:
            voice = {}
        return OmniVoiceConfig(
            enabled=bool(voice.get("omnivoice_enabled", False)),
            model=str(voice.get("omnivoice_model", "k2-fsa/OmniVoice")),
            device=str(voice.get("omnivoice_device", "cuda:0")),
            dtype=str(voice.get("omnivoice_dtype", "float16")),
            live_allowed=bool(voice.get("omnivoice_live_allowed", False)),
            unload_after_seconds=int(voice.get("omnivoice_unload_after_seconds", 300)),
        )

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self):
        if not self.config.enabled:
            raise RuntimeError("OmniVoice is disabled; enable voice.omnivoice_enabled for Voice Studio use")
        if self._model is None:
            try:
                from omnivoice import OmniVoice  # type: ignore
            except Exception as exc:
                raise RuntimeError(f"OmniVoice package is not installed or failed to import: {exc}") from exc
            self._model = OmniVoice.from_pretrained(
                self.config.model,
                device=self.config.device,
                dtype=self.config.dtype,
            )
            self._loaded_at = time.time()
        return self._model

    def synthesize_to_file(
        self,
        text: str,
        language: str = "en",
        profile: str = "vector",
        ref_audio: str | None = None,
        ref_text: str | None = None,
        instruct: str | None = None,
        speed: float = 1.0,
        num_step: int = 16,
        output_path: str | Path | None = None,
    ) -> str:
        if not text.strip():
            raise ValueError("text is required")
        model = self._load()
        target = Path(output_path) if output_path else Path(tempfile.gettempdir()) / f"vector_omnivoice_{int(time.time()*1000)}.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        result = model.generate(
            text=text,
            language=language,
            profile=profile,
            ref_audio=ref_audio,
            ref_text=ref_text,
            instruct=instruct,
            speed=speed,
            num_step=num_step,
            output_path=str(target),
        )
        return str(result or target)
