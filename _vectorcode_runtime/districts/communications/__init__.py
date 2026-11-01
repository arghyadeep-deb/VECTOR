"""
V.E.C.T.O.R. communications district.
Person model, style model, VectorCode comms adapter.
"""
from loguru import logger

from .person_model import PersonModel

logger.info("[VECTOR] communications district loaded")

__all__ = ["PersonModel"]