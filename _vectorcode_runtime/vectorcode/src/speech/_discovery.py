# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Auto-discover available speech-to-text backends."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

from loguru import logger

if TYPE_CHECKING:
    from vectorcode.src.vc_core.config import VectorConfig
    from vectorcode.src.speech._abc import SpeechBackend

# Priority order: local first, then cloud
DISCOVERY_ORDER = [
    "faster-whisper",
    "openai",
    "deepgram",
]

def _create_backend(
    key: str,
    config: "VectorConfig",
) -> Optional["SpeechBackend"]:
    """Try to instantiate a speech backend by registry key."""
    from vectorcode.src.vc_core.registry import SpeechRegistry

    if not SpeechRegistry.contains(key):
        return None

    try:
        backend_cls = SpeechRegistry.get(key)

        if key == "faster-whisper":
            return backend_cls(
                model_size=config.speech.model,
                device=config.speech.device,
                compute_type=config.speech.compute_type,
            )
        elif key == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                return None
            return backend_cls(api_key=api_key)
        elif key == "deepgram":
            api_key = os.environ.get("DEEPGRAM_API_KEY", "")
            if not api_key:
                return None
            return backend_cls(api_key=api_key)
        else:
            return backend_cls()
    except Exception as exc:
        logger.debug("[VECTOR][speech] failed to create backend {}: {}", key, exc)
        return None

def get_speech_backend(config: "VectorConfig") -> Optional["SpeechBackend"]:
    """Resolve the speech backend from config.

    If ``config.speech.backend`` is ``"auto"``, tries backends in
    priority order and returns the first healthy one.
    """
    # Trigger registration of built-in backends
    import vectorcode.src.speech  # noqa: F401

    backend_key = config.speech.backend

    if backend_key != "auto":
        backend = _create_backend(backend_key, config)
        return backend if _is_healthy(backend, backend_key) else None

    # Auto-discovery: try each in priority order
    for key in DISCOVERY_ORDER:
        backend = _create_backend(key, config)
        if _is_healthy(backend, key):
            return backend

    return None


def _is_healthy(backend: Optional["SpeechBackend"], key: str) -> bool:
    if backend is None:
        return False
    try:
        return backend.health()
    except Exception as exc:
        logger.debug("[VECTOR][speech] health check failed for {}: {}", key, exc)
        return False
