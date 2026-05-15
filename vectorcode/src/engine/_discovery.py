"""Engine discovery utilities."""
from __future__ import annotations
from typing import List

_discovery = None  # sentinel for import compat

def list_engines() -> List[str]:
    return []

def get_default_engine() -> str:
    return "ollama"

def get_engine(name: str = ""):
    return None
