"""Media router — /media/models."""

import sys

__all__ = [
    "media_models",
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

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ media.py OK")
