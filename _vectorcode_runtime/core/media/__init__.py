"""
VECTOR Media Studio — LOCAL-ONLY AI creative media generation (free, on-device).

Backends (paid cloud removed 2026-07-04):
  Wan2GP      — free local GPU video+image (run Wan2GP server, set WAN2GP_URL)
  LocalInf    — offline sd.cpp images (download binary once, no server needed)

Priority: Wan2GP -> local sd.cpp. No per-generation cost.
"""
__version__ = "2.0.0"

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
from core.media.wan2gp_client import Wan2GPClient, WAN2GP_CATALOG, Wan2GPModel
from core.media.local_inference import LocalInference, LOCAL_MODEL_CATALOG
from core.media.generative_studio import GenerativeStudio

__all__ = [
    "GenerativeStudio",
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
