"""
V.E.C.T.O.R. core package.
Core systems: config, memory, inference, loop, voice, city, sensing, control, brain.
"""
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
