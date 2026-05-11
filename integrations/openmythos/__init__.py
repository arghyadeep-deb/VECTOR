"""
V.E.C.T.O.R. OpenMythos package.
Model training, data preparation, Ollama export.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

from . import train, data_prep, export_to_ollama, forward

logger.info("[VECTOR] openmythos package loaded")

__all__ = ["train", "data_prep", "export_to_ollama", "forward"]