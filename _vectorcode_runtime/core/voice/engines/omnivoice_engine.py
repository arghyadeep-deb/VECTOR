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
            # Real bug found 2026-06-24 (model weights downloaded for real
            # this session, live verification): from_pretrained() forwards
            # unrecognized kwargs straight to OmniVoice.__init__(), which
            # doesn't accept device/dtype -- confirmed live:
            # "TypeError: OmniVoice.__init__() got an unexpected keyword
            # argument 'device'". Fixed: load with no device/dtype kwargs,
            # then move via .to() (the real, working pattern, also
            # confirmed live).
            import torch
            model = OmniVoice.from_pretrained(self.config.model)
            torch_dtype = getattr(torch, self.config.dtype, None)
            self._model = model.to(device=self.config.device, dtype=torch_dtype)
            self._loaded_at = time.time()
        return self._model

    def synthesize_to_file(
        self,
        text: str,
        language: str = "en",
        ref_audio: str | None = None,
        ref_text: str | None = None,
        instruct: str | None = None,
        speed: float = 1.0,
        output_path: str | Path | None = None,
    ) -> str:
        """Generate and save audio.

        Real API confirmed against the installed package: generate() takes
        no `profile`/`num_step`/`output_path` kwargs (those were guessed
        before the package was ever installed) and returns
        list[numpy.ndarray] -- it never writes a file itself, the caller
        must save it. Fixed to call only real parameters and write the
        result via soundfile (already a VECTOR dependency).
        """
        if not text.strip():
            raise ValueError("text is required")
        model = self._load()
        target = Path(output_path) if output_path else Path(tempfile.gettempdir()) / f"vector_omnivoice_{int(time.time()*1000)}.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        audio_arrays = model.generate(
            text=text,
            language=language,
            ref_audio=ref_audio,
            ref_text=ref_text,
            instruct=instruct,
            speed=speed,
        )
        audio = audio_arrays[0] if isinstance(audio_arrays, list) else audio_arrays
        import soundfile as sf

        # model.sampling_rate is the real attribute the package itself
        # documents (its own docstring shows the exact pattern:
        # soundfile.write("out.wav", audios[0], model.sampling_rate)) --
        # not guessed.
        sf.write(str(target), audio, samplerate=model.sampling_rate)
        return str(target)
