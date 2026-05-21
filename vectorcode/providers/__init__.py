"""
Gap 16: This root-level providers/ stub is deprecated.
All imports should use vectorcode.src.providers or vectorcode.src.engine.providers directly.
Kept as a thin redirect to avoid breaking any existing imports.
"""
from vectorcode.src.engine.providers.model_router import ModelRouter  # noqa: F401

def get_model_router():
    from vectorcode.src.router import GNNRouter
    return GNNRouter()
