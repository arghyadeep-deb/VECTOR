"""
VECTOR Media Model Catalog
Python port of Open-Generative-AI/packages/studio/src/models.js

~50 curated models across all categories. Add more by appending to the lists.
"""
from __future__ import annotations

__all__ = [
    "all_models",
    "get_model",
    "list_by_category",
    "MediaModel",
    "models_for_aspect",
]


from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MediaModel:
    id: str
    name: str
    endpoint: str
    category: str                         # t2i | i2i | t2v | i2v | v2v | lipsync
    aspect_ratios: list[str] = field(default_factory=lambda: ["1:1", "16:9", "9:16", "4:3", "3:4"])
    max_images: int = 1                   # i2i: up to 14 reference images
    supports_negative: bool = True
    supports_quality: bool = False
    supports_resolution: bool = False
    supports_seed: bool = True
    default_aspect: str = "1:1"
    image_field: str = "image_url"        # field name for input image(s)
    has_prompt: bool = True


# ── FREE LOCAL models only (paid cloud catalog removed 2026-07-04) ────────────
# All served on-device: Wan2GP (GPU) or sd.cpp (offline). No per-gen cost.

def _m(id, name, cat, ar=None):
    return MediaModel(id=id, name=name, endpoint=id, category=cat,
                      aspect_ratios=ar or ["1:1", "16:9", "9:16"])

# Text-to-Image (Wan2GP + sd.cpp)
T2I_MODELS: list[MediaModel] = [
    _m("flux-dev", "FLUX.1 dev (Wan2GP)", "t2i"),
    _m("qwen-image", "Qwen-Image (Wan2GP)", "t2i"),
    _m("sdxl", "Stable Diffusion XL (sd.cpp)", "t2i"),
    _m("sd15", "Stable Diffusion 1.5 (sd.cpp)", "t2i"),
]

# Image-to-Image — no local backend wired yet (ComfyUI img2img is the option)
I2I_MODELS: list[MediaModel] = []

# Text-to-Video (Wan2GP, free local GPU)
T2V_MODELS: list[MediaModel] = [
    _m("ltx-video", "LTX-Video (Wan2GP, fastest)", "t2v", ["16:9", "9:16", "1:1"]),
    _m("wan22-t2v", "Wan 2.2 T2V (Wan2GP)", "t2v", ["16:9", "9:16", "1:1"]),
    _m("hunyuan-video", "Hunyuan Video (Wan2GP)", "t2v", ["16:9", "9:16"]),
]

# Image-to-Video (Wan2GP, free local GPU)
I2V_MODELS: list[MediaModel] = [
    _m("wan22-i2v", "Wan 2.2 I2V (Wan2GP)", "i2v", ["16:9", "9:16", "1:1"]),
]

# Lipsync — SadTalker is the local option (districts/content), not in this catalog
LIPSYNC_MODELS: list[MediaModel] = []

# Video-to-Video — no local backend wired
V2V_MODELS: list[MediaModel] = []


_ALL_MODELS: dict[str, MediaModel] = {
    m.id: m
    for lst in [T2I_MODELS, I2I_MODELS, T2V_MODELS, I2V_MODELS, LIPSYNC_MODELS, V2V_MODELS]
    for m in lst
}

_BY_CATEGORY: dict[str, list[MediaModel]] = {
    "t2i": T2I_MODELS,
    "i2i": I2I_MODELS,
    "t2v": T2V_MODELS,
    "i2v": I2V_MODELS,
    "lipsync": LIPSYNC_MODELS,
    "v2v": V2V_MODELS,
}


def get_model(model_id: str) -> Optional[MediaModel]:
    return _ALL_MODELS.get(model_id)


def list_by_category(category: str) -> list[MediaModel]:
    return _BY_CATEGORY.get(category, [])


def models_for_aspect(aspect_ratio: str) -> list[MediaModel]:
    return [m for m in _ALL_MODELS.values() if not m.aspect_ratios or aspect_ratio in m.aspect_ratios]


def all_models() -> list[MediaModel]:
    return list(_ALL_MODELS.values())


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Total models: {len(_ALL_MODELS)}")
    for cat, lst in _BY_CATEGORY.items():
        print(f"  {cat}: {len(lst)} models — {', '.join(m.id for m in lst[:3])}...")
    assert get_model("flux-dev") is not None
    assert len(list_by_category("t2i")) >= 10
    assert len(list_by_category("lipsync")) >= 5
    print("OK models.py")
