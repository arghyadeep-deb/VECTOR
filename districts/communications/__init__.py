"""
V.E.C.T.O.R. communications district.
Person model, style model, VectorCode comms adapter.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

from .person_model import PersonModel
from .style_model import StyleModel
from .communications_adapter import CommunicationsAdapter

logger.info("[VECTOR] communications district loaded")

__all__ = ["PersonModel", "StyleModel", "CommunicationsAdapter"]