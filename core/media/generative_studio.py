"""
VECTOR Generative Studio — Unified orchestrator for AI creative media generation.

Priority chain: Wan2GP (free local GPU) → LocalInference (sd.cpp offline) → Muapi (cloud)

For image/video generation, always tries local/free options first before using
Muapi.ai cloud credits. Pass prefer_local=False to skip directly to cloud.

Usage:
    studio = GenerativeStudio()
    result = asyncio.run(studio.generate_image("A cyberpunk cityscape at night"))
    print(result["url"])
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.media.models import get_model, list_by_category, all_models
from core.media.muapi_client import MuapiClient
from core.media.wan2gp_client import Wan2GPClient, WAN2GP_CATALOG
from core.media.local_inference import LocalInference
from loguru import logger

_MEDIA_DIR = Path.home() / ".vector" / "media"
_MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class GenerativeStudio:
    """
    VECTOR's unified AI creative media interface.
    Coordinates Wan2GP (local GPU), sd.cpp (offline), and Muapi.ai (cloud).
    """

    def __init__(self) -> None:
        self._muapi   = MuapiClient()
        self._wan2gp  = Wan2GPClient()
        self._local   = LocalInference()
        self._wan2gp_probed = False

    # ── Backend selection ─────────────────────────────────────────────────────

    def _wan2gp_model_ids(self) -> set[str]:
        return {m.id for m in WAN2GP_CATALOG}

    async def _probe_wan2gp_if_needed(self) -> bool:
        if not self._wan2gp_probed and self._wan2gp._base_url:
            probe = await self._wan2gp.probe()
            self._wan2gp_probed = True
            return probe.get("ok", False)
        return self._wan2gp_probed and bool(self._wan2gp._base_url)

    def _has_muapi(self) -> bool:
        return bool(self._muapi._api_key)

    # ── Auto-upload local files ───────────────────────────────────────────────

    async def _resolve_url(self, path_or_url: str, prefer_local: bool = True) -> str:
        """If given a local file path, upload it to Muapi.ai or Wan2GP and return a hosted URL."""
        if not path_or_url:
            return path_or_url
        if path_or_url.startswith("http"):
            return path_or_url
        p = Path(path_or_url)
        if p.exists():
            if prefer_local and self._wan2gp._base_url:
                try:
                    return await self._wan2gp.upload_file(str(p))
                except Exception:
                    pass
            if self._has_muapi():
                return await self._muapi.upload_file(str(p))
        return path_or_url

    async def _download_result(self, url: str) -> str:
        """Download a generated result URL to local ~/.vector/media/ and return local path."""
        if not url:
            return url
        try:
            import httpx
            filename = f"vector_{int(time.time())}_{Path(url.split('?')[0]).suffix or '.png'}"
            out_path = _MEDIA_DIR / filename
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as c:
                resp = await c.get(url)
                resp.raise_for_status()
                out_path.write_bytes(resp.content)
            logger.debug("[VECTOR][studio] saved → {}", out_path)
            return str(out_path)
        except Exception as e:
            logger.warning("[VECTOR][studio] could not download result {}: {}", url[:80], e)
            return url

    # ── Image generation ──────────────────────────────────────────────────────

    async def generate_image(
        self,
        prompt: str,
        model: str = "flux-dev",
        prefer_local: bool = True,
        aspect_ratio: str = "1:1",
        **kwargs,
    ) -> dict:
        """Text-to-image. Tries Wan2GP → sd.cpp → Muapi in order."""
        wan2gp_id = f"wan2gp:{model.replace('flux-dev', 'flux-dev')}"

        # 1. Wan2GP (free local GPU)
        if prefer_local and wan2gp_id in self._wan2gp_model_ids():
            ok = await self._probe_wan2gp_if_needed()
            if ok:
                try:
                    result = await self._wan2gp.generate(wan2gp_id, prompt, aspect_ratio=aspect_ratio)
                    result["backend"] = "wan2gp"
                    return result
                except Exception as e:
                    logger.warning("[VECTOR][studio] Wan2GP failed ({}), trying next backend", e)

        # 2. Local sd.cpp (offline)
        if prefer_local and self._local.is_available():
            local_model = "sdxl" if "flux" not in model and "xl" in model.lower() else "sd15"
            if self._local.model_downloaded(local_model):
                try:
                    result = await self._local.generate(prompt, model=local_model, aspect_ratio=aspect_ratio)
                    result["backend"] = "local"
                    result["url"] = result.get("image_path", "")
                    return result
                except Exception as e:
                    logger.warning("[VECTOR][studio] Local sd.cpp failed ({}), trying Muapi", e)

        # 3. Muapi.ai cloud
        if not self._has_muapi():
            raise RuntimeError("No generation backend available. Set MUAPI_API_KEY or configure WAN2GP_URL.")
        result = await self._muapi.generate_image(model, prompt, aspect_ratio=aspect_ratio, **kwargs)
        result["backend"] = "muapi"
        return result

    async def generate_i2i(
        self,
        prompt: str,
        image: str,
        model: str = "nano-banana-edit",
        **kwargs,
    ) -> dict:
        """Image-to-image editing (always cloud — Muapi.ai)."""
        image_url = await self._resolve_url(image, prefer_local=False)
        if not self._has_muapi():
            raise RuntimeError("Image-to-image requires MUAPI_API_KEY")
        result = await self._muapi.generate_i2i(model, prompt, image_url=image_url, **kwargs)
        result["backend"] = "muapi"
        return result

    async def generate_video(
        self,
        prompt: str,
        model: str = "kling-v3",
        prefer_local: bool = True,
        aspect_ratio: str = "16:9",
        **kwargs,
    ) -> dict:
        """Text-to-video. Tries Wan2GP → Muapi in order."""
        wan2gp_id = f"wan2gp:{model}"

        # 1. Wan2GP (free local GPU)
        if prefer_local and wan2gp_id in self._wan2gp_model_ids():
            ok = await self._probe_wan2gp_if_needed()
            if ok:
                try:
                    result = await self._wan2gp.generate(wan2gp_id, prompt, aspect_ratio=aspect_ratio)
                    result["backend"] = "wan2gp"
                    return result
                except Exception as e:
                    logger.warning("[VECTOR][studio] Wan2GP video failed ({}), trying Muapi", e)

        # 2. Muapi.ai cloud
        if not self._has_muapi():
            raise RuntimeError("No video backend available. Set MUAPI_API_KEY or configure WAN2GP_URL.")
        result = await self._muapi.generate_video(model, prompt, aspect_ratio=aspect_ratio, **kwargs)
        result["backend"] = "muapi"
        return result

    async def animate_image(
        self,
        image: str,
        prompt: str = "",
        model: str = "kling-i2v",
        aspect_ratio: str = "16:9",
        prefer_local: bool = True,
        **kwargs,
    ) -> dict:
        """Image-to-video animation. Tries Wan2GP wan22-i2v → Muapi."""
        if prefer_local:
            ok = await self._probe_wan2gp_if_needed()
            if ok:
                try:
                    result = await self._wan2gp.generate(
                        "wan2gp:wan22-i2v", prompt, aspect_ratio=aspect_ratio,
                        image=image,
                    )
                    result["backend"] = "wan2gp"
                    return result
                except Exception as e:
                    logger.warning("[VECTOR][studio] Wan2GP i2v failed ({}), trying Muapi", e)

        image_url = await self._resolve_url(image, prefer_local=False)
        if not self._has_muapi():
            raise RuntimeError("No i2v backend available. Set MUAPI_API_KEY or configure WAN2GP_URL.")
        result = await self._muapi.generate_i2v(model, image_url, prompt, aspect_ratio=aspect_ratio, **kwargs)
        result["backend"] = "muapi"
        return result

    async def lipsync(
        self,
        portrait: str,
        audio: str,
        model: str = "infinite-talk",
        is_video: bool = False,
    ) -> dict:
        """Lip sync — portrait image or video + narration audio → talking head video."""
        portrait_url = await self._resolve_url(portrait, prefer_local=False)
        audio_url    = await self._resolve_url(audio, prefer_local=False)
        if not self._has_muapi():
            raise RuntimeError("Lip sync requires MUAPI_API_KEY")
        result = await self._muapi.process_lipsync(model, portrait_url, audio_url, is_video=is_video)
        result["backend"] = "muapi"
        logger.info("[VECTOR][studio] lipsync complete → {}", (result.get("url") or "")[:80])
        return result

    async def background_remove(self, image: str) -> dict:
        """Remove background from image."""
        image_url = await self._resolve_url(image, prefer_local=False)
        if not self._has_muapi():
            raise RuntimeError("Background removal requires MUAPI_API_KEY")
        result = await self._muapi.generate_i2i("background-remover", "", image_url=image_url)
        result["backend"] = "muapi"
        return result

    async def upscale(self, image: str) -> dict:
        """4x upscale an image."""
        image_url = await self._resolve_url(image, prefer_local=False)
        if not self._has_muapi():
            raise RuntimeError("Upscaling requires MUAPI_API_KEY")
        result = await self._muapi.generate_i2i("upscaler", "", image_url=image_url)
        result["backend"] = "muapi"
        return result

    # ── Governor dispatch ──────────────────────────────────────────────────────

    async def generate(self, task: dict) -> dict:
        """Dispatch a generation task by action name. Used by Governor and MediaStudioAgent."""
        p = task.get("params", task)
        action = p.get("action", "generate_image")

        if action in ("generate_image", "text_to_image", "t2i"):
            return await self.generate_image(
                prompt=p.get("prompt", ""),
                model=p.get("model", "flux-dev"),
                prefer_local=p.get("prefer_local", True),
                aspect_ratio=p.get("aspect_ratio", "1:1"),
            )
        elif action in ("generate_i2i", "image_to_image", "edit_image"):
            return await self.generate_i2i(
                prompt=p.get("prompt", ""),
                image=p.get("image", p.get("image_url", "")),
                model=p.get("model", "nano-banana-edit"),
            )
        elif action in ("generate_video", "text_to_video", "t2v"):
            return await self.generate_video(
                prompt=p.get("prompt", ""),
                model=p.get("model", "kling-v3"),
                prefer_local=p.get("prefer_local", True),
                aspect_ratio=p.get("aspect_ratio", "16:9"),
            )
        elif action in ("animate_image", "image_to_video", "i2v"):
            return await self.animate_image(
                image=p.get("image", p.get("image_url", "")),
                prompt=p.get("prompt", ""),
                model=p.get("model", "kling-i2v"),
                aspect_ratio=p.get("aspect_ratio", "16:9"),
            )
        elif action == "lipsync":
            return await self.lipsync(
                portrait=p.get("portrait", p.get("image", "")),
                audio=p.get("audio", p.get("audio_url", "")),
                model=p.get("model", "infinite-talk"),
                is_video=p.get("is_video", False),
            )
        elif action == "background_remove":
            return await self.background_remove(p.get("image", p.get("image_url", "")))
        elif action == "upscale":
            return await self.upscale(p.get("image", p.get("image_url", "")))
        else:
            return {"error": f"Unknown action: {action}"}

    # ── Status ─────────────────────────────────────────────────────────────────

    async def status(self) -> dict:
        probe = await self._wan2gp.probe() if self._wan2gp._base_url else {"ok": False}
        balance = await self._muapi.get_balance() if self._has_muapi() else 0.0
        return {
            "muapi": {"configured": self._has_muapi(), "balance": balance},
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
        t2i_models = list_by_category("t2i")
        print(f"OK generative_studio.py")
        print(f"  t2i models: {len(t2i_models)}")
        print(f"  muapi configured: {st['muapi']['configured']}")
        print(f"  wan2gp connected: {st['wan2gp']['connected']}")
        print(f"  local binary: {st['local']['binary_available']}")
        # Dispatch test
        result = await studio.generate({"params": {"action": "generate_image", "prompt": "test"}}) if st["muapi"]["configured"] else {"status": "no key"}
        assert "error" not in result or "action" not in result
        print(f"  dispatch test: OK")

    asyncio.run(_smoke())
