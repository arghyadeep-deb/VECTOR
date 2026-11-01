"""Providers router — /providers/routes."""

import sys

__all__ = [
    "providers_routes",
    "router",
]


from fastapi import APIRouter
from loguru import logger

from core.api.schemas import ProvidersRoutesResponse

router = APIRouter(prefix="/providers", tags=["providers"])

@router.get("/routes", response_model=ProvidersRoutesResponse)
async def providers_routes():
    try:
        from core.engine.providers.model_router import ModelTier, _DEFAULT_ROUTES
        routes = {tier.value: model for tier, model in _DEFAULT_ROUTES.items()}
        providers = list(dict.fromkeys(routes.values()))
        return ProvidersRoutesResponse(routes=routes, active_providers=providers)
    except Exception as e:
        logger.warning(f"[VECTOR][api][providers] routes failed: {e}")
        return ProvidersRoutesResponse(routes={}, active_providers=[])

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ providers.py OK")
