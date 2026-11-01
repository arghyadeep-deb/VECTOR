"""
V.E.C.T.O.R. core package.
Core systems: config, memory, inference, loop, voice, city, sensing, control, brain.
"""
# --- Windows console safety -------------------------------------------------
# The code style ships an emoji status line (`print("✅ ... OK")`) at the bottom
# of nearly every module, and per-file imports route through `core.config`,
# which imports this package first. A default Windows console is cp1252, which
# raises UnicodeEncodeError the instant such a line prints. Forcing stdout/stderr
# to UTF-8 here fixes every module that touches `core` from one place — no need
# to edit hundreds of files. Idempotent, guarded, and a no-op when the stream is
# already UTF-8 (e.g. under pytest capture or on Linux/macOS).
import sys as _sys

for _stream in (_sys.stdout, _sys.stderr):
    try:
        if (
            _stream is not None
            and hasattr(_stream, "reconfigure")
            and (getattr(_stream, "encoding", "") or "").lower() not in ("utf-8", "utf8")
        ):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        # Never let console-encoding setup break an import.
        pass
# ---------------------------------------------------------------------------

# Load .env into os.environ at the earliest point of `import core`, so every
# env-gated feature (VECTOR_*_LLM flags, API keys read via os.environ.get) sees
# it reliably — previously .env only loaded when core.inference.key_pool
# happened to be imported, which many code paths never trigger. Existing
# os.environ values win (load_dotenv override defaults to False).
try:
    from pathlib import Path as _Path
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from importlib.util import find_spec

from loguru import logger

logger.info("[VECTOR] core package loaded")

_mcp_spec = find_spec("mcp")
_mcp_locations = []
if _mcp_spec is not None:
    if _mcp_spec.origin:
        _mcp_locations.append(_mcp_spec.origin)
    _mcp_locations.extend(_mcp_spec.submodule_search_locations or [])

if any("vectorcode\\src\\mcp" in p.lower() or "vectorcode/src/mcp" in p.lower() for p in _mcp_locations):
    logger.warning("[VECTOR] mcp module may be shadowed by vectorcode/src/mcp/")

__all__ = [
    "config", "memory", "inference", "loop", "voice",
    "city", "sensing", "control", "brain",
]
