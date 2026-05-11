"""
V.E.C.T.O.R. integrations package.
Exposes: hermes, openmythos, opencli, airllm, ruflo
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger

from .hermes import hermes_adapter
from .openmythos import train, data_prep, export_to_ollama, forward
from .opencli import tool_registry
from .airllm import airllm_runner

logger.info("[VECTOR] integrations package loaded")

__all__ = [
    "hermes_adapter",
    "train",
    "data_prep",
    "export_to_ollama",
    "forward",
    "tool_registry",
    "airllm_runner",
]