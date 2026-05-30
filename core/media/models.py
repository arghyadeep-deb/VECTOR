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


# ── Text-to-Image ─────────────────────────────────────────────────────────────

T2I_MODELS: list[MediaModel] = [
    MediaModel(
        id="flux-dev", name="Flux Dev", endpoint="flux-dev-image", category="t2i",
        aspect_ratios=[], supports_resolution=True, default_aspect="1:1",
    ),
    MediaModel(
        id="flux-pro", name="Flux Pro", endpoint="flux-pro-image", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "9:21"],
    ),
    MediaModel(
        id="flux-kontext-dev-t2i", name="Flux Kontext Dev", endpoint="flux-kontext-dev-t2i", category="t2i",
        aspect_ratios=["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9"],
    ),
    MediaModel(
        id="nano-banana", name="Nano Banana 2", endpoint="nano-banana", category="t2i",
        aspect_ratios=["1:1", "3:4", "4:3", "9:16", "16:9", "3:2", "2:3", "5:4", "4:5", "21:9"],
    ),
    MediaModel(
        id="seedream-5", name="Seedream 5.0", endpoint="seedream-5", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        supports_quality=True,
    ),
    MediaModel(
        id="ideogram-v3", name="Ideogram v3", endpoint="ideogram-v3", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        supports_quality=True,
    ),
    MediaModel(
        id="midjourney-v7", name="Midjourney v7", endpoint="midjourney-v7", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4", "3:2"],
    ),
    MediaModel(
        id="gpt-4o-image", name="GPT-4o Image", endpoint="gpt-4o-image", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16"],
        supports_negative=False,
    ),
    MediaModel(
        id="sdxl", name="Stable Diffusion XL", endpoint="sdxl-image", category="t2i",
        aspect_ratios=[], supports_resolution=True,
    ),
    MediaModel(
        id="qwen-image", name="Qwen Image", endpoint="qwen-image", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
    ),
    MediaModel(
        id="minimax-image", name="MiniMax Image 01", endpoint="minimax-image", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16"],
    ),
    MediaModel(
        id="hailuo-image", name="Hailuo Image", endpoint="hailuo-image", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16"],
    ),
    MediaModel(
        id="dalle-3", name="DALL-E 3", endpoint="dalle-3", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16"],
        supports_negative=False, supports_quality=True,
    ),
    MediaModel(
        id="recraft-v3", name="Recraft v3", endpoint="recraft-v3", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
    ),
    MediaModel(
        id="imagen-4", name="Imagen 4", endpoint="imagen-4", category="t2i",
        aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        supports_negative=False,
    ),
]

# ── Image-to-Image ────────────────────────────────────────────────────────────

I2I_MODELS: list[MediaModel] = [
    MediaModel(
        id="nano-banana-edit", name="Nano Banana Edit", endpoint="nano-banana-edit", category="i2i",
        aspect_ratios=["1:1", "16:9", "9:16", "4:3", "3:4"],
        max_images=14, image_field="images_list",
    ),
    MediaModel(
        id="flux-kontext-pro", name="Flux Kontext Pro", endpoint="flux-kontext-pro", category="i2i",
        aspect_ratios=["16:9", "9:16", "1:1", "4:3", "3:4"],
        max_images=1,
    ),
    MediaModel(
        id="gpt-4o-edit", name="GPT-4o Edit", endpoint="gpt-4o-edit", category="i2i",
        aspect_ratios=["1:1", "16:9", "9:16"],
        max_images=3, supports_negative=False,
    ),
    MediaModel(
        id="background-remover", name="Background Remover", endpoint="background-remover", category="i2i",
        has_prompt=False, max_images=1, supports_negative=False,
    ),
    MediaModel(
        id="upscaler", name="4x Upscaler", endpoint="upscaler", category="i2i",
        has_prompt=False, max_images=1, supports_negative=False,
    ),
    MediaModel(
        id="seededit", name="Seededit", endpoint="seededit", category="i2i",
        aspect_ratios=["1:1", "16:9", "9:16"],
        max_images=1,
    ),
    MediaModel(
        id="qwen-image-edit", name="Qwen Image Edit Plus", endpoint="qwen-image-edit", category="i2i",
        aspect_ratios=["1:1", "16:9", "9:16"],
        max_images=4, image_field="images_list",
    ),
    MediaModel(
        id="flux-fill", name="Flux Fill (Inpainting)", endpoint="flux-fill", category="i2i",
        aspect_ratios=[], supports_resolution=True, max_images=1,
    ),
    MediaModel(
        id="ideogram-v3-edit", name="Ideogram v3 Edit", endpoint="ideogram-v3-edit", category="i2i",
        aspect_ratios=["1:1", "16:9", "9:16"],
        max_images=1,
    ),
    MediaModel(
        id="minimax-image-edit", name="MiniMax Image Edit", endpoint="minimax-image-edit", category="i2i",
        aspect_ratios=["1:1", "16:9", "9:16"],
        max_images=1,
    ),
]

# ── Text-to-Video ─────────────────────────────────────────────────────────────

T2V_MODELS: list[MediaModel] = [
    MediaModel(
        id="kling-v3", name="Kling v3", endpoint="kling-v3", category="t2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="sora-2", name="Sora 2", endpoint="sora-2", category="t2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
        supports_negative=False,
    ),
    MediaModel(
        id="veo3", name="Veo 3", endpoint="veo3", category="t2v",
        aspect_ratios=["16:9", "9:16"],
        supports_negative=False,
    ),
    MediaModel(
        id="wan-2.6", name="Wan 2.6", endpoint="wan-2.6", category="t2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="seedance-2", name="Seedance 2.0", endpoint="seedance-2", category="t2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
        supports_quality=True,
    ),
    MediaModel(
        id="hailuo-2", name="Hailuo 2.3", endpoint="hailuo-2", category="t2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="runway-gen3", name="Runway Gen-3 Alpha", endpoint="runway-gen3", category="t2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="ltx-video", name="LTX Video", endpoint="ltx-video", category="t2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="hunyuan-video", name="Hunyuan Video", endpoint="hunyuan-video", category="t2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="minimax-hailuo", name="MiniMax Hailuo", endpoint="minimax-hailuo", category="t2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
        supports_negative=False,
    ),
]

# ── Image-to-Video ────────────────────────────────────────────────────────────

I2V_MODELS: list[MediaModel] = [
    MediaModel(
        id="kling-i2v", name="Kling v2.1 I2V", endpoint="kling-i2v", category="i2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="veo3-i2v", name="Veo 3 I2V", endpoint="veo3-i2v", category="i2v",
        aspect_ratios=["16:9"],
        supports_negative=False,
    ),
    MediaModel(
        id="runway-i2v", name="Runway I2V", endpoint="runway-i2v", category="i2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="seedance-i2v", name="Seedance 2.0 I2V", endpoint="seedance-i2v", category="i2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="midjourney-i2v", name="Midjourney I2V", endpoint="midjourney-i2v", category="i2v",
        aspect_ratios=["16:9", "9:16"],
        supports_negative=False,
    ),
    MediaModel(
        id="wan-i2v", name="Wan I2V", endpoint="wan-i2v", category="i2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="ltx-i2v", name="LTX I2V", endpoint="ltx-i2v", category="i2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
    MediaModel(
        id="hailuo-i2v", name="Hailuo I2V", endpoint="hailuo-i2v", category="i2v",
        aspect_ratios=["16:9", "9:16", "1:1"],
    ),
]

# ── Lip Sync ──────────────────────────────────────────────────────────────────

LIPSYNC_MODELS: list[MediaModel] = [
    MediaModel(
        id="infinite-talk", name="Infinite Talk", endpoint="infinite-talk", category="lipsync",
        has_prompt=False, supports_negative=False,
    ),
    MediaModel(
        id="wan-speech-to-video", name="Wan 2.2 Speech to Video", endpoint="wan-speech-to-video", category="lipsync",
        has_prompt=False, supports_negative=False,
    ),
    MediaModel(
        id="ltx-lipsync", name="LTX 2.3 Lipsync", endpoint="ltx-lipsync", category="lipsync",
        has_prompt=False, supports_negative=False,
    ),
    MediaModel(
        id="ltx-2-lipsync", name="LTX 2 19B Lipsync", endpoint="ltx-2-lipsync", category="lipsync",
        has_prompt=False, supports_negative=False,
    ),
    MediaModel(
        id="sync-lipsync", name="Sync Lipsync", endpoint="sync-lipsync", category="lipsync",
        has_prompt=False, supports_negative=False,
    ),
    MediaModel(
        id="latentsync", name="LatentSync", endpoint="latentsync", category="lipsync",
        has_prompt=False, supports_negative=False,
    ),
    MediaModel(
        id="infinite-talk-v2v", name="Infinite Talk V2V", endpoint="infinite-talk-v2v", category="lipsync",
        has_prompt=False, supports_negative=False,
    ),
]

# ── V2V ───────────────────────────────────────────────────────────────────────

V2V_MODELS: list[MediaModel] = [
    MediaModel(
        id="wan-v2v", name="Wan V2V", endpoint="wan-v2v", category="v2v",
        has_prompt=True,
    ),
    MediaModel(
        id="runway-v2v", name="Runway V2V", endpoint="runway-v2v", category="v2v",
        has_prompt=True,
    ),
]

# ── Combined index ────────────────────────────────────────────────────────────

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
