"""
V.E.C.T.O.R. control security package.
Security controls, threat detection integration.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from loguru import logger

logger.info("[VECTOR] control/security loaded")

__all__ = []