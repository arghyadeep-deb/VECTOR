"""
VECTOR Muapi Client — Python async port of Open-Generative-AI/packages/studio/src/muapi.js

Provides access to 200+ AI image, video, and lip-sync generation models
via the Muapi.ai unified API. No content filters. One API key.

Usage:
    client = MuapiClient()
    result = asyncio.run(client.generate_image("flux-dev", "A cyberpunk cityscape"))
    print(result["url"])  # hosted image URL
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from core.media.models import get_model
from loguru import logger

BASE_URL = "https://api.muapi.ai/api/v1"
_DEFAULT_POLL_ATTEMPTS = 900
_DEFAULT_POLL_INTERVAL = 2.0   # seconds between polls


def _load_api_key() -> str:
    key = CONFIG.get("api_keys", {}).get("muapi_api_key", "") or os.environ.get("MUAPI_API_KEY", "")
    return key.strip()


class MuapiClient:
    """
    VECTOR's unified creative media client — 200+ models via Muapi.ai.
    Covers image, video, image-to-video, and lip sync generation.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or _load_api_key()
        if not self._api_key:
            logger.debug("[VECTOR][muapi] No API key set — set MUAPI_API_KEY in .env to enable cloud generation")
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict:
        return {"Content-Type": "application/json", "x-api-key": self._api_key}

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        return self._client

    # ── Core request helpers ──────────────────────────────────────────────────

    async def _post(self, endpoint: str, payload: dict) -> dict:
        if not self._api_key:
            raise RuntimeError("MUAPI_API_KEY not configured — add it to .env")
        client = await self._ensure_client()
        url = f"{BASE_URL}/{endpoint}"
        resp = await client.post(url, json=payload, headers=self._headers())
        if not resp.is_success:
            raise RuntimeError(f"Muapi POST {endpoint} → HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def _get(self, path: str) -> dict:
        client = await self._ensure_client()
        url = f"{BASE_URL}/{path}"
        resp = await client.get(url, headers=self._headers())
        if not resp.is_success:
            raise RuntimeError(f"Muapi GET {path} → HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def _poll(
        self,
        request_id: str,
        max_attempts: int = _DEFAULT_POLL_ATTEMPTS,
        interval: float = _DEFAULT_POLL_INTERVAL,
    ) -> dict:
        poll_url = f"predictions/{request_id}/result"
        for attempt in range(1, max_attempts + 1):
            await asyncio.sleep(interval)
            try:
                data = await self._get(poll_url)
                status = (data.get("status") or "").lower()
                if status in ("completed", "succeeded", "success"):
                    return data
                if status in ("failed", "error"):
                    raise RuntimeError(f"Generation failed: {data.get('error', 'unknown')}")
            except RuntimeError:
                raise
            except Exception as e:
                if attempt == max_attempts:
                    raise RuntimeError(f"Poll failed after {max_attempts} attempts: {e}") from e
        raise RuntimeError("Generation timed out after polling")

    async def _submit_and_poll(
        self,
        endpoint: str,
        payload: dict,
        max_attempts: int = 60,
    ) -> dict:
        submit = await self._post(endpoint, payload)
        request_id = submit.get("request_id") or submit.get("id")
        if not request_id:
            return submit
        result = await self._poll(request_id, max_attempts=max_attempts)
        output_url = (
            (result.get("outputs") or [None])[0]
            or result.get("url")
            or (result.get("output") or {}).get("url")
        )
        return {**result, "url": output_url}

    # ── Image generation ──────────────────────────────────────────────────────

    async def generate_image(self, model_id: str, prompt: str, **kwargs) -> dict:
        """Text-to-image generation."""
        model = get_model(model_id)
        endpoint = model.endpoint if model else model_id
        payload: dict = {"prompt": prompt}
        for k in ("aspect_ratio", "resolution", "quality", "seed", "width", "height", "num_images"):
            if kwargs.get(k) is not None:
                payload[k] = kwargs[k]
        payload["image_url"] = kwargs.get("image_url") or None
        logger.info("[VECTOR][muapi] t2i {} prompt={!r:.60}", model_id, prompt)
        return await self._submit_and_poll(endpoint, payload, max_attempts=60)

    async def generate_i2i(self, model_id: str, prompt: str, image_url: str | None = None, **kwargs) -> dict:
        """Image-to-image editing."""
        model = get_model(model_id)
        endpoint = model.endpoint if model else model_id
        payload: dict = {}
        if prompt:
            payload["prompt"] = prompt
        images_list = kwargs.get("images_list")
        if images_list:
            img_field = model.image_field if model else "image_url"
            if img_field == "images_list":
                payload["images_list"] = images_list
            else:
                payload[img_field] = images_list[0]
        elif image_url:
            img_field = model.image_field if model else "image_url"
            payload[img_field] = image_url
        for k in ("aspect_ratio", "resolution", "quality"):
            if kwargs.get(k) is not None:
                payload[k] = kwargs[k]
        logger.info("[VECTOR][muapi] i2i {} image={!r:.60}", model_id, image_url or "list")
        return await self._submit_and_poll(endpoint, payload, max_attempts=60)

    async def generate_video(self, model_id: str, prompt: str, **kwargs) -> dict:
        """Text-to-video generation."""
        model = get_model(model_id)
        endpoint = model.endpoint if model else model_id
        payload: dict = {"prompt": prompt}
        for k in ("aspect_ratio", "duration", "resolution", "quality", "mode", "image_url"):
            if kwargs.get(k) is not None:
                payload[k] = kwargs[k]
        logger.info("[VECTOR][muapi] t2v {} prompt={!r:.60}", model_id, prompt)
        return await self._submit_and_poll(endpoint, payload, max_attempts=_DEFAULT_POLL_ATTEMPTS)

    async def generate_i2v(self, model_id: str, image_url: str, prompt: str = "", **kwargs) -> dict:
        """Image-to-video (animate a still image)."""
        model = get_model(model_id)
        endpoint = model.endpoint if model else model_id
        img_field = model.image_field if model else "image_url"
        payload: dict = {}
        if prompt:
            payload["prompt"] = prompt
        if img_field == "images_list":
            payload["images_list"] = [image_url]
        else:
            payload[img_field] = image_url
        for k in ("aspect_ratio", "duration", "resolution", "quality", "mode"):
            if kwargs.get(k) is not None:
                payload[k] = kwargs[k]
        logger.info("[VECTOR][muapi] i2v {} image={!r:.60}", model_id, image_url)
        return await self._submit_and_poll(endpoint, payload, max_attempts=_DEFAULT_POLL_ATTEMPTS)

    async def process_v2v(self, model_id: str, video_url: str, **kwargs) -> dict:
        """Video-to-video processing."""
        model = get_model(model_id)
        endpoint = model.endpoint if model else model_id
        payload: dict = {"video_url": video_url}
        if kwargs.get("prompt"):
            payload["prompt"] = kwargs["prompt"]
        if kwargs.get("image_url"):
            payload["image_url"] = kwargs["image_url"]
        return await self._submit_and_poll(endpoint, payload, max_attempts=_DEFAULT_POLL_ATTEMPTS)

    async def process_lipsync(self, model_id: str, portrait_url: str, audio_url: str, **kwargs) -> dict:
        """Lip sync — portrait/video + audio → talking head video."""
        model = get_model(model_id)
        endpoint = model.endpoint if model else model_id
        payload: dict = {"audio_url": audio_url}
        # Portrait image or video as input
        if kwargs.get("is_video"):
            payload["video_url"] = portrait_url
        else:
            payload["image_url"] = portrait_url
        if kwargs.get("prompt") and model and model.has_prompt:
            payload["prompt"] = kwargs["prompt"]
        if kwargs.get("resolution"):
            payload["resolution"] = kwargs["resolution"]
        if kwargs.get("seed") is not None and kwargs["seed"] != -1:
            payload["seed"] = kwargs["seed"]
        logger.info("[VECTOR][muapi] lipsync {} portrait={!r:.60}", model_id, portrait_url)
        return await self._submit_and_poll(endpoint, payload, max_attempts=_DEFAULT_POLL_ATTEMPTS)

    # ── File upload ───────────────────────────────────────────────────────────

    async def upload_file(self, file_path: str) -> str:
        """Upload a local file to Muapi.ai CDN. Returns the hosted URL."""
        if not self._api_key:
            raise RuntimeError("MUAPI_API_KEY not configured")
        client = await self._ensure_client()
        path = Path(file_path)
        with path.open("rb") as f:
            content = f.read()
        files = {"file": (path.name, content)}
        resp = await client.post(
            f"{BASE_URL}/upload_file",
            headers={"x-api-key": self._api_key},
            files=files,
            timeout=120.0,
        )
        if not resp.is_success:
            raise RuntimeError(f"Upload failed: HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        url = data.get("url") or data.get("file_url") or (data.get("data") or {}).get("url")
        if not url:
            raise RuntimeError("Upload response contained no URL")
        logger.info("[VECTOR][muapi] uploaded {} → {}", path.name, url[:80])
        return url

    # ── Account ───────────────────────────────────────────────────────────────

    async def get_balance(self) -> float:
        """Fetch remaining Muapi.ai credit balance."""
        try:
            data = await self._get("account/balance")
            return float(data.get("balance") or data.get("credits") or 0.0)
        except Exception as e:
            logger.warning("[VECTOR][muapi] get_balance failed: {}", e)
            return 0.0

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        client = MuapiClient()
        key_status = "set" if client._api_key else "not set (add MUAPI_API_KEY to .env)"
        balance = await client.get_balance() if client._api_key else 0.0
        await client.close()
        print(f"OK muapi_client.py — api_key={key_status} balance={balance}")

    asyncio.run(_smoke())
