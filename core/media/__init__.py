"""
VECTOR Media Studio
AI creative media generation: 200+ image/video/lipsync models.

Backends:
  Wan2GP      — free local GPU (user runs Wan2GP server, set WAN2GP_URL)
  LocalInf    — offline sd.cpp (download binary once, no server needed)
  Muapi.ai    — 200+ cloud models (set MUAPI_API_KEY, costs credits)

Priority: Wan2GP → local → Muapi (prefer free/local, fall back to cloud)
"""
__version__ = "1.0.0"

from core.media.models import (
    MediaModel,
    get_model,
    list_by_category,
    models_for_aspect,
    all_models,
    T2I_MODELS,
    I2I_MODELS,
    T2V_MODELS,
    I2V_MODELS,
    LIPSYNC_MODELS,
    V2V_MODELS,
)
from core.media.muapi_client import MuapiClient
from core.media.wan2gp_client import Wan2GPClient, WAN2GP_CATALOG, Wan2GPModel
from core.media.local_inference import LocalInference, LOCAL_MODEL_CATALOG
from core.media.generative_studio import GenerativeStudio

__all__ = [
    "GenerativeStudio",
    "MuapiClient",
    "Wan2GPClient",
    "LocalInference",
    "MediaModel",
    "Wan2GPModel",
    "get_model",
    "list_by_category",
    "models_for_aspect",
    "all_models",
    "WAN2GP_CATALOG",
    "LOCAL_MODEL_CATALOG",
    "T2I_MODELS",
    "I2I_MODELS",
    "T2V_MODELS",
    "I2V_MODELS",
    "LIPSYNC_MODELS",
    "V2V_MODELS",
]
