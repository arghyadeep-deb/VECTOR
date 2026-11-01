"""
VECTOR Wan2GP Client — Python port of Open-Generative-AI/electron/lib/wan2gpProvider.js

Connects to a user-run Wan2GP Gradio server for FREE local GPU generation.
Supports: Flux.1 Dev, Qwen Image, Wan 2.2 T2V/I2V, Hunyuan Video, LTX Video.

Setup: Run Wan2GP on your GPU machine, set WAN2GP_URL in .env or config.
       https://github.com/deepbeepmeep/Wan2GP

Usage:
    client = Wan2GPClient()
    result = asyncio.run(client.generate("wan2gp:ltx-video", "A dragon flying", aspect_ratio="16:9"))
    logger.info(result["url"])  # served from Wan2GP server

"""
from __future__ import annotations

__all__ = [
    "Wan2GPClient",
    "Wan2GPModel",
]


import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from core.config import CONFIG
from loguru import logger


@dataclass
class Wan2GPModel:
    id: str
    name: str
    description: str
    type: str                        # "image" | "video"
    family: str
    fn: str                          # preferred Gradio api_name
    fn_aliases: list[str] = field(default_factory=list)
    aspect_ratios: list[str] = field(default_factory=lambda: ["1:1", "16:9", "9:16", "4:3", "3:4"])
    default_steps: int = 25
    default_guidance: float = 5.0
    needs_image: bool = False


WAN2GP_CATALOG: list[Wan2GPModel] = [
    Wan2GPModel(
        id="wan2gp:flux-dev", name="Flux.1 Dev (Wan2GP)",
        description="Image — FLUX.1 dev served by Wan2GP. 1024px output.",
        type="image", family="flux", fn="flux",
        fn_aliases=["flux_dev", "flux_1_dev", "flux1_dev", "flux_image"],
        aspect_ratios=["1:1", "4:3", "3:4", "16:9", "9:16"],
        default_steps=28, default_guidance=3.5,
    ),
    Wan2GPModel(
        id="wan2gp:qwen-image", name="Qwen Image (Wan2GP)",
        description="Image — Qwen-Image text-to-image served by Wan2GP.",
        type="image", family="qwen", fn="qwen_image",
        fn_aliases=["qwen", "qwen_t2i", "qwen_image_t2i"],
        aspect_ratios=["1:1", "4:3", "3:4", "16:9", "9:16"],
        default_steps=30, default_guidance=4.0,
    ),
    Wan2GPModel(
        id="wan2gp:wan22-t2v", name="Wan 2.2 (Text-to-Video)",
        description="Video — Wan 2.2 text-to-video. Slow on consumer GPUs.",
        type="video", family="wan", fn="wan22_t2v",
        fn_aliases=["wan_2_2_t2v", "wan22_text2video", "wan_t2v", "wan2_2_t2v", "t2v"],
        aspect_ratios=["16:9", "1:1", "9:16"],
        default_steps=25, default_guidance=5.0,
    ),
    Wan2GPModel(
        id="wan2gp:wan22-i2v", name="Wan 2.2 (Image-to-Video)",
        description="Video — Wan 2.2 image-to-video. Provide a start frame.",
        type="video", family="wan", fn="wan22_i2v",
        fn_aliases=["wan_2_2_i2v", "wan22_image2video", "wan_i2v", "wan2_2_i2v", "i2v"],
        aspect_ratios=["16:9", "1:1", "9:16"],
        default_steps=25, default_guidance=5.0, needs_image=True,
    ),
    Wan2GPModel(
        id="wan2gp:hunyuan-video", name="Hunyuan Video (Wan2GP)",
        description="Video — Hunyuan text-to-video via Wan2GP.",
        type="video", family="hunyuan", fn="hunyuan_video",
        fn_aliases=["hunyuan", "hunyuan_t2v", "hyvideo", "hy_video"],
        aspect_ratios=["16:9", "1:1", "9:16"],
        default_steps=30, default_guidance=6.0,
    ),
    Wan2GPModel(
        id="wan2gp:ltx-video", name="LTX Video (Wan2GP)",
        description="Video — LTX text-to-video. Fastest video option in Wan2GP.",
        type="video", family="ltx", fn="ltx_video",
        fn_aliases=["ltx", "ltx_t2v", "ltxv", "ltx_v", "ltx_2", "ltx2"],
        aspect_ratios=["16:9", "1:1", "9:16"],
        default_steps=20, default_guidance=3.0,
    ),
]

_CATALOG_BY_ID: dict[str, Wan2GPModel] = {m.id: m for m in WAN2GP_CATALOG}

_CONFIG_PATH = Path.home() / ".vector" / "local-ai" / "wan2gp.json"


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
    return {"url": ""}


def _save_config(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _ar_to_dimensions(ar: str) -> tuple[int, int]:
    base = 1024
    mapping = {
        "1:1":  (base, base),
        "16:9": (round(base * 16 / 9 / 64) * 64, base),
        "9:16": (base, round(base * 16 / 9 / 64) * 64),
        "4:3":  (round(base * 4 / 3 / 64) * 64, base),
        "3:4":  (base, round(base * 4 / 3 / 64) * 64),
    }
    return mapping.get(ar, (base, base))


def _resolve_output_url(base_url: str, output) -> str | None:
    first = output[0] if isinstance(output, list) and output else output
    if not first:
        return None
    if isinstance(first, str):
        return first if first.startswith("http") else f"{base_url}/file={first.lstrip('/')}"
    if isinstance(first, dict):
        if first.get("url"):
            u = first["url"]
            return u if u.startswith("http") else f"{base_url}{u}"
        if first.get("path"):
            return f"{base_url}/file={first['path'].lstrip('/')}"
    return None


class Wan2GPClient:
    """
    VECTOR's Wan2GP client — connects to user-run local GPU Gradio server.
    Free generation of image/video models (Wan 2.2, Hunyuan, LTX Video, Flux).
    """

    def __init__(self, base_url: str | None = None) -> None:
        cfg_url = (
            base_url
            or CONFIG.get("media", {}).get("wan2gp_url", "")
            or os.environ.get("WAN2GP_URL", "")
            or _load_config().get("url", "")
        )
        self._base_url = _normalize_url(cfg_url)
        self._fn_cache: dict[str, str | None] = {}  # model_id → resolved fn name
        self._known_api_names: list[str] = []
        if self._base_url:
            logger.debug("[VECTOR][wan2gp] server={}", self._base_url)
        else:
            logger.debug("[VECTOR][wan2gp] no server URL configured — set WAN2GP_URL in .env")

    def set_url(self, url: str) -> None:
        self._base_url = _normalize_url(url)
        self._fn_cache.clear()
        self._known_api_names = []
        _save_config({"url": self._base_url})

    # â”€â”€ Discovery â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _fetch_api_names(self) -> list[str]:
        if not self._base_url:
            return []
        base = self._base_url
        async with httpx.AsyncClient(timeout=8.0) as c:
            for candidate in [f"{base}/info", f"{base}/api", f"{base}/gradio_api/info"]:
                try:
                    resp = await c.get(candidate)
                    if resp.status_code == 200:
                        data = resp.json()
                        named = data.get("named_endpoints") or data.get("unnamed_endpoints") or data
                        if isinstance(named, dict):
                            keys = [k for k in named if k.startswith("/")]
                            if keys:
                                return [k.lstrip("/") for k in keys]
                except Exception:
                    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
            # Legacy fallback
            try:
                resp = await c.get(f"{base}/config")
                if resp.status_code == 200:
                    deps = resp.json().get("dependencies", [])
                    return [d["api_name"] for d in deps if isinstance(d.get("api_name"), str) and d["api_name"] != "false"]
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return []

    def _resolve_fn(self, model: Wan2GPModel, api_names: list[str]) -> str | None:
        name_set = set(api_names)
        if model.fn in name_set:
            return model.fn
        for alias in model.fn_aliases:
            if alias in name_set:
                return alias
        family = model.family.lower()
        type_hint = r"(video|t2v|i2v)" if model.type == "video" else r"(image|t2i|txt2img)"
        import re
        for name in api_names:
            if family in name.lower() and re.search(type_hint, name, re.IGNORECASE):
                return name
        for name in api_names:
            if family in name.lower():
                return name
        return None

    async def probe(self, url: str | None = None) -> dict:
        """Test connection to Wan2GP server. Returns {ok, version, matched_models}."""
        target = _normalize_url(url or self._base_url)
        if not target:
            return {"ok": False, "error": "No URL configured. Set WAN2GP_URL in .env"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                resp = await c.get(f"{target}/config")
                if resp.status_code != 200:
                    return {"ok": False, "error": f"HTTP {resp.status_code} from /config — is this a Gradio server?"}
                cfg = resp.json()
            api_names = await self._fetch_api_names()
            self._known_api_names = api_names
            for m in WAN2GP_CATALOG:
                self._fn_cache[m.id] = self._resolve_fn(m, api_names)
            matched = sum(1 for v in self._fn_cache.values() if v)
            return {
                "ok": True,
                "version": cfg.get("version", "unknown"),
                "api_names": api_names,
                "matched_models": matched,
                "total_models": len(WAN2GP_CATALOG),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def list_models(self) -> list[dict]:
        """List all Wan2GP models with availability status."""
        if not self._fn_cache and self._base_url:
            await self.probe()
        result = []
        for m in WAN2GP_CATALOG:
            fn = self._fn_cache.get(m.id)
            ready = fn is not None
            entry = {
                "id": m.id, "name": m.name, "type": m.type,
                "description": m.description, "aspect_ratios": m.aspect_ratios,
                "ready": ready,
            }
            if not ready and not self._base_url:
                entry["unavailable_reason"] = "Wan2GP URL not configured"
            elif not ready:
                entry["unavailable_reason"] = f'Server has no endpoint matching "{m.fn}"'
            result.append(entry)
        return result

    # â”€â”€ File upload â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def upload_file(self, file_path: str) -> str:
        """Upload a file to Wan2GP Gradio server. Returns the served URL."""
        if not self._base_url:
            raise RuntimeError("Wan2GP URL not configured")
        path = Path(file_path)
        upload_id = hex(int(time.time() * 1000))[2:]
        async with httpx.AsyncClient(timeout=120.0) as c:
            with path.open("rb") as f:
                resp = await c.post(
                    f"{self._base_url}/upload?upload_id={upload_id}",
                    files={"files": (path.name, f)},
                )
        if not resp.is_success:
            raise RuntimeError(f"Wan2GP upload failed: HTTP {resp.status_code}")
        paths = resp.json()
        server_path = (paths[0] if isinstance(paths, list) else paths)
        if not isinstance(server_path, str):
            raise RuntimeError("Wan2GP upload returned no path")
        return f"{self._base_url}/file={server_path.lstrip('/')}"

    # â”€â”€ Gradio SSE generation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _gradio_call(self, fn: str, payload: dict) -> object:
        """Gradio v4 protocol: POST /gradio_api/call/<fn> → event_id → SSE stream."""
        base = self._base_url
        async with httpx.AsyncClient(timeout=30.0) as c:
            post_resp = await c.post(
                f"{base}/gradio_api/call/{fn}",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if not post_resp.is_success:
                raise RuntimeError(f"Wan2GP POST /call/{fn} → HTTP {post_resp.status_code}")
            event_id = post_resp.json().get("event_id")
            if not event_id:
                raise RuntimeError("Wan2GP did not return an event_id")

        async with httpx.AsyncClient(timeout=1800.0) as stream_client:
            async with stream_client.stream("GET", f"{base}/gradio_api/call/{fn}/{event_id}") as resp:
                if not resp.is_success:
                    raise RuntimeError(f"Wan2GP stream → HTTP {resp.status_code}")
                buf = ""
                async for chunk in resp.aiter_text():
                    buf += chunk
                    blocks = buf.split("\n\n")
                    buf = blocks.pop()
                    for block in blocks:
                        lines = block.strip().split("\n")
                        evt = next((l[6:].strip() for l in lines if l.startswith("event:")), "")
                        data_str = next((l[5:].strip() for l in lines if l.startswith("data:")), "")
                        if evt in ("complete", "process_completes"):
                            try:
                                parsed = json.loads(data_str)
                                return parsed if isinstance(parsed, list) else parsed.get("data", parsed)
                            except Exception:
                                raise RuntimeError(f"Wan2GP malformed completion: {data_str[:200]}")
                        elif evt in ("error", "process_error"):
                            raise RuntimeError(f"Wan2GP error: {data_str[:200]}")
        raise RuntimeError("Wan2GP stream ended without a completion event")

    async def generate(
        self,
        model_id: str,
        prompt: str = "",
        aspect_ratio: str = "16:9",
        negative_prompt: str = "",
        steps: int | None = None,
        guidance_scale: float | None = None,
        seed: int = -1,
        image: str | None = None,      # local path or hosted URL for i2v
    ) -> dict:
        """Generate image or video using local Wan2GP server."""
        if not self._base_url:
            raise RuntimeError("Wan2GP URL not configured. Set WAN2GP_URL in .env")

        model = _CATALOG_BY_ID.get(model_id)
        if not model:
            raise RuntimeError(f"Unknown Wan2GP model: {model_id}")

        if not self._fn_cache:
            await self.probe()

        real_fn = self._fn_cache.get(model_id) or model.fn
        if self._known_api_names and not self._fn_cache.get(model_id):
            raise RuntimeError(
                f"{model.name}: server exposes no endpoint matching '{model.fn}'. "
                f"Available: {', '.join(self._known_api_names[:8])}"
            )

        if model.needs_image and not image:
            raise RuntimeError(f"{model.name} requires a start-frame image — provide image= parameter")

        width, height = _ar_to_dimensions(aspect_ratio)
        if seed == -1:
            import random
            seed = random.randint(0, 2_147_483_647)

        # Resolve image to Gradio file descriptor if local path
        image_descriptor = None
        if image:
            if image.startswith("http"):
                image_descriptor = image
            else:
                uploaded_url = await self.upload_file(image)
                image_descriptor = {"path": uploaded_url.split("/file=")[-1], "url": uploaded_url, "orig_name": Path(image).name, "meta": {"_type": "gradio.FileData"}}

        payload = {
            "data": [
                prompt,
                negative_prompt,
                width, height,
                steps or model.default_steps,
                guidance_scale or model.default_guidance,
                seed,
                image_descriptor,
            ]
        }

        logger.info("[VECTOR][wan2gp] {} fn={} prompt={!r:.60}", model_id, real_fn, prompt)
        result = await self._gradio_call(real_fn, payload)
        output_url = _resolve_output_url(self._base_url, result)
        if not output_url:
            raise RuntimeError(f"Wan2GP returned unrecognized output: {str(result)[:200]}")
        return {"url": output_url, "media_type": model.type, "seed": seed, "model": model_id}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        client = Wan2GPClient()
        url_status = client._base_url or "not configured (set WAN2GP_URL in .env)"
        probe = await client.probe()
        models = await client.list_models()
        print(f"OK wan2gp_client.py — server={url_status}")
        print(f"  probe.ok={probe.get('ok')} models={len(models)}")
        if probe.get("ok"):
            ready = [m for m in models if m["ready"]]
            print(f"  ready={len(ready)}/{len(models)}")

    asyncio.run(_smoke())
