"""
V.E.C.T.O.R. integrations package.
Exposes: vectorcode_comms, openmythos, opencli, airllm
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger

from .openmythos import train, data_prep, export_to_ollama, forward
from .opencli import tool_registry
from .airllm import airllm_runner
from . import vectorcode_bridge

logger.info("[VECTOR] integrations package loaded")

__all__ = [
    "vectorcode_bridge",
    "train",
    "data_prep",
    "export_to_ollama",
    "forward",
    "tool_registry",
    "airllm_runner",
]