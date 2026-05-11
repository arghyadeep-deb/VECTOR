"""
V.E.C.T.O.R. AirLLM integration package.
Layer-wise gradient compression for running 70B+ models in 16GB.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

from . import airllm_runner

logger.info("[VECTOR] airllm package loaded")

__all__ = ["airllm_runner"]