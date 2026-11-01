"""Unified world model endpoint."""

from __future__ import annotations

import asyncio

__all__ = ["router", "world_snapshot"]

from fastapi import APIRouter, Request

from core.runtime.world_model import build_world_snapshot


router = APIRouter(prefix="/world", tags=["world"])


@router.get("/snapshot")
async def world_snapshot(request: Request, panels: str = ""):
    open_panels = [part.strip() for part in panels.split(",") if part.strip()]
    mounted_routes = [getattr(route, "path", "") for route in request.app.routes]
    snapshot = await asyncio.to_thread(
        build_world_snapshot,
        app_state=request.app.state,
        open_panels=open_panels,
        mounted_routes=mounted_routes,
    )
    return snapshot.to_dict()
