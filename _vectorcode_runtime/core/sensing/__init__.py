"""
V.E.C.T.O.R. sensing package.
Ambient listening, screen sensing, phone bridge, wearable integration.
"""
from loguru import logger

logger.info("[VECTOR] sensing package loaded")

__all__ = ["PresenceDetector", "PresenceResult"]


def __getattr__(name: str):
    if name in {"PresenceDetector", "PresenceResult"}:
        from core.sensing.presence_detector import PresenceDetector, PresenceResult
        return {"PresenceDetector": PresenceDetector, "PresenceResult": PresenceResult}[name]
    raise AttributeError(name)
