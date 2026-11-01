"""
VECTOR Generative Studio — LOCAL-ONLY AI creative media orchestrator.

Free, on-device generation only (owner decision 2026-07-04: paid cloud
backends removed). Priority chain: Wan2GP (local GPU) → LocalInference
(sd.cpp offline). No per-generation cost, ever.

Backends:
  Wan2GP        — text/image-to-video (ltx/wan2.2/hunyuan) + flux/qwen images
  LocalInference— sd.cpp offline image fallback

Text-to-image, text-to-video, and image-to-video run fully local. Cloud-only
extras (i2i edit, lipsync, background-remove, upscale) return a clear
"local-only mode" notice instead of calling any paid API — wire a local
backend (ComfyUI / SadTalker / Real-ESRGAN) later if you want them.

Usage:
    studio = GenerativeStudio()
    result = asyncio.run(studio.generate_video("A neon city flythrough",
                                               model="ltx-video"))
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from core.media.models import get_model, list_by_category, all_models
from core.media.wan2gp_client import Wan2GPClient, WAN2GP_CATALOG
from core.media.local_inference import LocalInference
from loguru import logger

_MEDIA_DIR = Path.home() / ".vector" / "media"
_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Free local defaults (were the paid kling-* cloud models).
_DEFAULT_IMAGE = "flux-dev"
_DEFAULT_VIDEO = "ltx-video"      # fastest free local text-to-video
_DEFAULT_I2V   = "wan22-i2v"      # free local image-to-video

_LOCAL_ONLY_MSG = ("local-only mode — this action needs a cloud backend that "
                   "was removed. Wire a local backend (ComfyUI/SadTalker/"
                   "Real-ESRGAN) to enable it.")


class GenerativeStudio:
    """VECTOR's unified LOCAL AI creative media interface (Wan2GP + sd.cpp)."""

    def __init__(self) -> None:
        self._wan2gp  = Wan2GPClient()
        self._local   = LocalInference()
        self._wan2gp_probed = False

    # ── Backend selection ────────────────────────────────────────────────────

    def _wan2gp_model_ids(self) -> set[str]:
        return {m.id for m in WAN2GP_CATALOG}

    async def _probe_wan2gp_if_needed(self) -> bool:
        if not self._wan2gp_probed and self._wan2gp._base_url:
            probe = await self._wan2gp.probe()
            self._wan2gp_probed = True
            return probe.get("ok", False)
        return self._wan2gp_probed and bool(self._wan2gp._base_url)

    async def _download_result(self, url: str) -> str:
        """Download a generated result URL to ~/.vector/media/ (Wan2GP may
        return a hosted URL for large video)."""
        if not url or not url.startswith("http"):
            return url
        try:
            import httpx
            filename = f"vector_{int(time.time())}{Path(url.split('?')[0]).suffix or '.png'}"
            out_path = _MEDIA_DIR / filename
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as c:
                resp = await c.get(url)
                resp.raise_for_status()
                out_path.write_bytes(resp.content)
            logger.debug("[VECTOR][studio] saved -> {}", out_path)
            return str(out_path)
        except Exception as e:
            logger.warning("[VECTOR][studio] could not download result {}: {}", url[:80], e)
            return url

    def _no_backend(self, kind: str) -> RuntimeError:
        return RuntimeError(
            f"No local {kind} backend available. Start Wan2GP and set its URL "
            f"(CONFIG['media']['wan2gp_url'] / WAN2GP_URL), or install a local "
            f"sd.cpp model.")

    # ── Image generation ─────────────────────────────────────────────────────

    async def generate_image(
        self,
        prompt: str,
        model: str = _DEFAULT_IMAGE,
        prefer_local: bool = True,   # kept for call-site compat; always local now
        aspect_ratio: str = "1:1",
        **kwargs,
    ) -> dict:
        """Text-to-image: Wan2GP (flux/qwen) → sd.cpp offline."""
        wan2gp_id = f"wan2gp:{model}"

        if wan2gp_id in self._wan2gp_model_ids():
            if await self._probe_wan2gp_if_needed():
                try:
                    result = await self._wan2gp.generate(wan2gp_id, prompt, aspect_ratio=aspect_ratio)
                    result["backend"] = "wan2gp"
                    return result
                except Exception as e:
                    logger.warning("[VECTOR][studio] Wan2GP failed ({}), trying sd.cpp", e)

        if self._local.is_available():
            local_model = "sdxl" if "flux" not in model and "xl" in model.lower() else "sd15"
            if self._local.model_downloaded(local_model):
                try:
                    result = await self._local.generate(prompt, model=local_model, aspect_ratio=aspect_ratio)
                    result["backend"] = "local"
                    result["url"] = result.get("image_path", "")
                    return result
                except Exception as e:
                    logger.warning("[VECTOR][studio] Local sd.cpp failed ({})", e)

        raise self._no_backend("image")

    async def generate_video(
        self,
        prompt: str,
        model: str = _DEFAULT_VIDEO,
        prefer_local: bool = True,
        aspect_ratio: str = "16:9",
        **kwargs,
    ) -> dict:
        """Text-to-video: Wan2GP (ltx / wan2.2 / hunyuan), fully local."""
        wan2gp_id = f"wan2gp:{model}"
        if wan2gp_id in self._wan2gp_model_ids():
            if await self._probe_wan2gp_if_needed():
                try:
                    result = await self._wan2gp.generate(wan2gp_id, prompt, aspect_ratio=aspect_ratio)
                    result["backend"] = "wan2gp"
                    return result
                except Exception as e:
                    logger.warning("[VECTOR][studio] Wan2GP video failed ({})", e)
        raise self._no_backend("video")

    async def animate_image(
        self,
        image: str,
        prompt: str = "",
        model: str = _DEFAULT_I2V,
        aspect_ratio: str = "16:9",
        prefer_local: bool = True,
        **kwargs,
    ) -> dict:
        """Image-to-video: Wan2GP wan22-i2v, fully local."""
        if await self._probe_wan2gp_if_needed():
            try:
                result = await self._wan2gp.generate(
                    "wan2gp:wan22-i2v", prompt, aspect_ratio=aspect_ratio, image=image)
                result["backend"] = "wan2gp"
                return result
            except Exception as e:
                logger.warning("[VECTOR][studio] Wan2GP i2v failed ({})", e)
        raise self._no_backend("image-to-video")

    # ── Cloud-only extras (removed) — graceful notice, no paid calls ─────────

    async def generate_i2i(self, prompt: str, image: str, model: str = "", **kwargs) -> dict:
        return {"error": f"generate_i2i {_LOCAL_ONLY_MSG}", "backend": "local_only"}

    async def lipsync(self, portrait: str, audio: str, model: str = "", is_video: bool = False) -> dict:
        # A local SadTalker path exists at districts/content/ — route there later.
        return {"error": f"lipsync {_LOCAL_ONLY_MSG} (SadTalker is the local option)",
                "backend": "local_only"}

    async def background_remove(self, image: str) -> dict:
        """Remove background — LOCAL rembg-style ONNX (core/video/background_remover)."""
        try:
            from core.video.background_remover import remove_background
            src = Path(image)
            if not src.exists():
                return {"error": f"background_remove: file not found: {image}", "backend": "local"}
            out = _MEDIA_DIR / f"nobg_{int(time.time())}_{src.stem}.png"
            res = await asyncio.to_thread(remove_background, str(src), str(out))
            ok = getattr(res, "ok", None)
            path = getattr(res, "output_path", str(out)) or str(out)
            if ok is False:
                return {"error": f"background_remove failed: {getattr(res,'error','')}", "backend": "local"}
            return {"url": path, "image_path": path, "backend": "local"}
        except Exception as e:
            logger.warning("[VECTOR][studio] local background_remove failed: {}", e)
            return {"error": f"background_remove (local) errored: {e}", "backend": "local"}

    async def upscale(self, image: str) -> dict:
        return {"error": f"upscale {_LOCAL_ONLY_MSG}", "backend": "local_only"}

    # ── Governor dispatch ────────────────────────────────────────────────────

    async def generate(self, task: dict) -> dict:
        """Dispatch a generation task by action name (Governor / MediaStudioAgent)."""
        p = task.get("params", task)
        action = p.get("action", "generate_image")

        if action in ("generate_image", "text_to_image", "t2i"):
            return await self.generate_image(
                prompt=p.get("prompt", ""), model=p.get("model", _DEFAULT_IMAGE),
                aspect_ratio=p.get("aspect_ratio", "1:1"))
        elif action in ("generate_video", "text_to_video", "t2v"):
            return await self.generate_video(
                prompt=p.get("prompt", ""), model=p.get("model", _DEFAULT_VIDEO),
                aspect_ratio=p.get("aspect_ratio", "16:9"))
        elif action in ("animate_image", "image_to_video", "i2v"):
            return await self.animate_image(
                image=p.get("image", p.get("image_url", "")), prompt=p.get("prompt", ""),
                model=p.get("model", _DEFAULT_I2V), aspect_ratio=p.get("aspect_ratio", "16:9"))
        elif action in ("generate_i2i", "image_to_image", "edit_image"):
            return await self.generate_i2i(p.get("prompt", ""), p.get("image", ""))
        elif action == "lipsync":
            return await self.lipsync(p.get("portrait", p.get("image", "")),
                                      p.get("audio", p.get("audio_url", "")))
        elif action == "background_remove":
            return await self.background_remove(p.get("image", p.get("image_url", "")))
        elif action == "upscale":
            return await self.upscale(p.get("image", p.get("image_url", "")))
        else:
            return {"error": f"Unknown action: {action}"}

    # ── Status ───────────────────────────────────────────────────────────────

    async def status(self) -> dict:
        probe = await self._wan2gp.probe() if self._wan2gp._base_url else {"ok": False}
        return {
            "mode": "local_only",
            "wan2gp": {"configured": bool(self._wan2gp._base_url), "connected": probe.get("ok", False),
                       "matched_models": probe.get("matched_models", 0)},
            "local": {"binary_available": self._local.is_available(),
                      "models": self._local.list_models()},
        }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        studio = GenerativeStudio()
        st = await studio.status()
        print("OK generative_studio.py (LOCAL-ONLY)")
        print(f"  mode: {st['mode']}")
        print(f"  wan2gp connected: {st['wan2gp']['connected']}")
        print(f"  local binary: {st['local']['binary_available']}")
        # cloud-only action returns a graceful notice, never a paid call
        r = await studio.generate({"params": {"action": "upscale", "image": "x.png"}})
        assert r.get("backend") == "local_only", r
        print("  cloud-only action correctly disabled:", "OK")

    asyncio.run(_smoke())
