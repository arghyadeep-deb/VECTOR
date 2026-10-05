"""Transport registry for VectorCode provider transports.

Usage:
    from transports import get_transport, register_transport

    transport = get_transport("anthropic_messages")()
    kwargs = transport.build_kwargs(model, messages, tools)

The registry maps api_mode strings → transport classes (not instances).
Transports register themselves on import by calling register_transport().
"""

# ── Guard: strip transports/ from sys.path to prevent types.py shadowing stdlib.
import sys
import os as _os
_this_dir = _os.path.dirname(_os.path.abspath(__file__))
sys.path = [p for p in sys.path if _os.path.abspath(p) != _this_dir]
del _os, _this_dir

# ── stdlib ────────────────────────────────────────────────────────────────────
from typing import Dict, Optional, Type

# ── sys.path inserts (exactly 2) ─────────────────────────────────────────────

from loguru import logger

try:
    from core.config import CONFIG  # type: ignore
except ImportError:
    CONFIG = {}

# ── Registry ─────────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, Type] = {}


def register_transport(api_mode: str, cls: Type) -> None:
    """Register a transport class under an api_mode string.

    Called automatically by each transport module on import.
    """
    if api_mode in _REGISTRY:
        logger.debug(f"[VECTOR][transports] re-registering transport for api_mode={api_mode!r}")
    _REGISTRY[api_mode] = cls
    logger.debug(f"[VECTOR][transports] registered {cls.__name__} for api_mode={api_mode!r}")


def get_transport(api_mode: str) -> Optional[Type]:
    """Return the transport class registered for api_mode, or None.

    The caller is responsible for instantiating (calling with no args or
    with any constructor params the transport requires).
    """
    cls = _REGISTRY.get(api_mode)
    if cls is None:
        logger.warning(f"[VECTOR][transports] no transport registered for api_mode={api_mode!r}")
    return cls


def list_transports() -> Dict[str, Type]:
    """Return a copy of the current registry."""
    return dict(_REGISTRY)


# ── Auto-import to trigger registration ──────────────────────────────────────
# Import order matters: types and base must be importable before the
# transport modules run their module-level register_transport() calls.

def _auto_register() -> None:
    """Import all built-in transports so they self-register."""
    try:
        from . import anthropic as _ant  # noqa: F401
    except Exception as e:
        logger.warning(f"[VECTOR][transports] failed to load anthropic transport: {e}")

    try:
        from . import chat_completions as _cc  # noqa: F401
    except Exception as e:
        logger.warning(f"[VECTOR][transports] failed to load chat_completions transport: {e}")

    # No ollama transport: local Ollama models are served by providers.router.ModelRouter. Importing a
    # non-existent transports.ollama module only logged a warning on every start.


_auto_register()

__all__ = [
    "register_transport",
    "get_transport",
    "list_transports",
    "_REGISTRY",
]
