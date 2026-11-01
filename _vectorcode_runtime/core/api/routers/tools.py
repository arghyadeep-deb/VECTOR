"""Tools router — /tools/registry."""

import sys

__all__ = [
    "router",
    "tools_registry",
]


from fastapi import APIRouter
from loguru import logger

from core.api.schemas import ToolsRegistryResponse

router = APIRouter(prefix="/tools", tags=["tools"])

@router.get("/registry", response_model=ToolsRegistryResponse)
async def tools_registry():
    try:
        from core.engine.tools.dispatcher import ToolScope, PermissionLevel
        scopes = [s.value for s in ToolScope]
        perm_levels = {p.name: p.value for p in PermissionLevel}
        return ToolsRegistryResponse(
            total_tools=len(perm_levels),
            scopes=scopes,
            permission_levels=perm_levels,
        )
    except Exception as e:
        logger.warning(f"[VECTOR][api][tools] registry failed: {e}")
        return ToolsRegistryResponse(total_tools=0, scopes=[], permission_levels={})

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ tools.py OK")
