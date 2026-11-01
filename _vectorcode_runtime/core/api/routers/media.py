"""Media router — /media/models."""

import sys

__all__ = [
    "media_models",
    "media_sidecars",
    "router",
]


from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/media", tags=["media"])

@router.get("/models")
async def media_models():
    """Get media model catalog."""
    try:
        from core.media.models import all_models, list_by_category

        models = all_models()
        categories = {}
        for m in models:
            cat = m.category if hasattr(m, "category") else "unknown"
            categories.setdefault(cat, 0)
            categories[cat] += 1

        model_list = [
            {"id": m.id, "name": m.name, "category": getattr(m, "category", "unknown")}
            for m in models
        ]
        return {
            "total_models": len(models),
            "categories": categories,
            "models": model_list,
        }
    except Exception as e:
        logger.warning(f"[VECTOR][api][media] models failed: {e}")
        return {"total_models": 0, "categories": {}, "models": []}

async def _probe(url: str) -> bool:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get(url)
            return r.status_code < 500
    except Exception:
        return False


@router.get("/sidecars")
async def media_sidecars():
    """Which local generation servers are actually listening.

    The HUD's ComfyUI / Media Studio / Hyperframes panels are windows onto separate local servers. With the
    server down they showed an empty frame; the browser CSP forbids the page probing those ports itself, so
    the backend probes them and the panels show "not running" instead of a blank.
    """
    import asyncio
    import os

    urls = {
        "comfyui": os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").strip().rstrip("/"),
        "hyperframes": "http://127.0.0.1:7421/health",
        "studio": "http://127.0.0.1:51200/",
        "librechat": os.environ.get("LIBRECHAT_URL", "http://localhost:3080").strip().rstrip("/"),
        "openwebui": os.environ.get("OPENWEBUI_URL", "http://localhost:8080").strip().rstrip("/"),
    }
    ups = await asyncio.gather(*[_probe(u) for u in urls.values()])
    return {name: {"url": u, "running": up} for (name, u), up in zip(urls.items(), ups)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ media.py OK")
