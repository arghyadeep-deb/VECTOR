"""Optional config-selectable live-conversation TTS engine (Supertonic 3).

docs/repo_analysis/supertonic.md: a CPU-only, zero-VRAM alternative to
Kokoro for live conversation — does not touch the cloning role (VoxCPM/
Chatterbox). Mirrors core/voice/cloning.py's get_cloner() factory pattern:
"kokoro" stays the existing tts.py code path unchanged; "supertonic" routes
through this wrapper. bn/as are not in Supertonic's language set and stay
on the existing gTTS fallback in tts.py — never fed to this engine.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "SupertonicTTS",
    "get_live_tts",
    "map_lang_code",
    "SUPERTONIC_SUPPORTED_LANGS",
    "SUPERTONIC_UNSUPPORTED_LANGS",
]

# Supertonic's 31-language set includes en/hi/ja directly (README.md:31-35).
# bn/as are not supported — same gap as Kokoro; stays on tts.py's gTTS route.
SUPERTONIC_SUPPORTED_LANGS = {"en", "hi", "ja"}
SUPERTONIC_UNSUPPORTED_LANGS = {"bn", "as"}


def map_lang_code(lang: str) -> str | None:
    """Map a VECTOR language code to Supertonic's code set, or None if
    Supertonic doesn't support it (caller should keep that lang on gTTS)."""
    if lang in SUPERTONIC_SUPPORTED_LANGS:
        return lang
    return None


class SupertonicTTS:
    """Lazy, guarded-import wrapper around the optional `supertonic` package."""

    def __init__(self, enabled: bool = False, model_dir: str = "",
                 total_steps: int = 8, voice_style: str = "", auto_download: bool = False):
        self.enabled = enabled
        self.model_dir = model_dir
        self.total_steps = total_steps
        self.voice_style = voice_style
        # Defaults to False -- ~260MB of model weights is a separate,
        # explicit owner action (docs/repo_analysis/OWNER_ACTIONS_NEEDED.md),
        # distinct from installing the pip package. Never silently download
        # on the first real synthesis call; raise a clear, actionable error
        # instead and let the owner opt in explicitly.
        self.auto_download = auto_download
        self._engine = None

    def available(self) -> bool:
        if not self.enabled:
            return False
        try:
            import supertonic  # noqa: F401
            return True
        except Exception:
            return False

    def _load(self):
        if not self.enabled:
            raise RuntimeError("supertonic is disabled; set voice.live_engine=\"supertonic\" to enable")
        if self._engine is None:
            import supertonic  # type: ignore

            try:
                # Real API confirmed against the installed package (no
                # module-level load_model() exists -- supertonic.TTS is
                # the actual entry point). auto_download=False unless the
                # owner explicitly opted in (see __init__).
                self._engine = supertonic.TTS(
                    model_dir=self.model_dir or None,
                    auto_download=self.auto_download,
                )
            except Exception as exc:
                raise RuntimeError(
                    "supertonic model weights not found locally and auto_download is "
                    "disabled by default (~260MB download is a separate, explicit owner "
                    "action — see docs/repo_analysis/OWNER_ACTIONS_NEEDED.md). "
                    f"Set SupertonicTTS(auto_download=True) to allow it. Original error: {exc}"
                ) from exc
        return self._engine

    # Real bug found 2026-06-24 (model weights confirmed downloaded, live
    # verification run): "default" is not a real preset name. The package's
    # own usage example (supertonic/__init__.py) uses "M1" -- the 10 real
    # built-in presets are M1-M5/F1-F5, confirmed via the package's own
    # FileNotFoundError message when "default" was tried.
    DEFAULT_VOICE_PRESET = "M1"

    def _resolve_voice_style(self, engine):
        """synthesize() requires a real Style object, not a bare path
        string. A configured voice_style is treated as a path to a
        Voice-Builder persona JSON; otherwise fall back to a real preset."""
        if self.voice_style:
            return engine.get_voice_style_from_path(self.voice_style)
        return engine.get_voice_style(self.DEFAULT_VOICE_PRESET)

    def create(self, text: str, lang: str = "en", speed: float = 1.0) -> tuple:
        """Synthesize `text`. Returns (samples, sample_rate) — same shape
        Kokoro is used through (tts.py's `self._kokoro.create(...)`).

        Real bug found 2026-06-24 (live verification after weights
        downloaded): engine.synthesize() returns (waveform,
        duration_in_seconds), NOT (samples, sample_rate) — confirmed
        directly (the second value was a float like 4.23, not an integer
        sample rate). The real fixed rate lives on engine.sample_rate.
        """
        if not self.available():
            raise RuntimeError("supertonic package not installed or disabled")
        mapped_lang = map_lang_code(lang)
        if mapped_lang is None:
            raise RuntimeError(f"supertonic does not support lang={lang!r} — route to gTTS instead")
        engine = self._load()
        voice_style = self._resolve_voice_style(engine)
        waveform, _duration_secs = engine.synthesize(
            text=text,
            voice_style=voice_style,
            lang=mapped_lang,
            total_steps=self.total_steps,
            speed=speed,
        )
        return waveform, engine.sample_rate


def get_live_tts(live_engine: str | None = None) -> tuple[str, SupertonicTTS | None]:
    """Return (engine_name, engine) per CONFIG["voice"]["live_engine"].

    "kokoro" (default) returns (name, None) — tts.py's existing Kokoro code
    path needs zero changes, it's the engine when this factory returns None.
    "supertonic" returns a live SupertonicTTS instance.
    """
    if live_engine is None:
        from core.config import CONFIG
        live_engine = (CONFIG.get("voice", {}) or {}).get("live_engine", "kokoro")

    if live_engine == "supertonic":
        from core.config import CONFIG
        voice_cfg = CONFIG.get("voice", {}) or {}
        return "supertonic", SupertonicTTS(
            enabled=True,
            model_dir=voice_cfg.get("supertonic_model_dir", ""),
            total_steps=int(voice_cfg.get("supertonic_total_steps", 8)),
            voice_style=voice_cfg.get("supertonic_voice_style", ""),
            auto_download=bool(voice_cfg.get("supertonic_auto_download", False)),
        )
    return "kokoro", None
