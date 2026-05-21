"""Backward-compatible re-export: game_development -> content. DEPRECATED."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
import importlib

SOURCE = "game_development"
TARGET = "content"

logger.warning("DEPRECATED: districts.{} is merged into districts.{}. Use districts.{} directly.", SOURCE, TARGET, TARGET)


def __getattr__(name):
    if name.startswith("_"):
        raise AttributeError(name)
    mod = importlib.import_module(f"districts.{TARGET}")
    if hasattr(mod, name):
        return getattr(mod, name)
    raise AttributeError(f"module 'districts.{SOURCE}' has no attribute '{name}'")
