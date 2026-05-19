"""Code Intelligence router — /code-intel/* endpoints for the CodeIntelAgent (VectorCode Intelligence)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from loguru import logger

router = APIRouter(prefix="/code-intel", tags=["code-intel"])

_PROJECT_PATH = str(Path(__file__).parent.parent.parent.parent)
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()


def _safe_path(v: str) -> str:
    """Reject paths that escape the VECTOR codebase root."""
    if not v:
        return v
    resolved = Path(v).resolve()
    if not str(resolved).startswith(str(_PROJECT_ROOT)):
        raise ValueError(f"Path '{v}' is outside the VECTOR codebase — access denied.")
    return v


def _run_intel(task_type: str, params: dict) -> dict:
    import asyncio
    from districts.coding.code_intel_agent import CodeIntelAgent
    agent = CodeIntelAgent()
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(agent.run({"type": task_type, "params": params}))
    loop.close()
    return result


# ── Request models ────────────────────────────────────────────────────────────

class _PathMixin(BaseModel):
    @field_validator("project_path", "file_path", "file", mode="before", check_fields=False)
    @classmethod
    def _confine_to_codebase(cls, v: str) -> str:
        return _safe_path(v) if v else v


class SearchRequest(_PathMixin):
    query: str
    project_path: str = _PROJECT_PATH
    limit: int = 10
    language: str | None = None
    file_filter: str | None = None

class IndexRequest(_PathMixin):
    project_path: str = _PROJECT_PATH
    extra_extensions: list[str] = []

class GraphQueryRequest(_PathMixin):
    project_path: str = _PROJECT_PATH
    file_path: str = ""

class ImpactRequest(_PathMixin):
    target: str
    project_path: str = _PROJECT_PATH
    depth: int = 3

class FlowRequest(_PathMixin):
    entrypoint: str
    project_path: str = _PROJECT_PATH
    file: str | None = None
    depth: int = 5

class SymbolRequest(_PathMixin):
    name: str
    project_path: str = _PROJECT_PATH
    file: str | None = None

class ContextSearchRequest(_PathMixin):
    query: str
    project_path: str = _PROJECT_PATH
    limit: int = 5

class WatchRequest(_PathMixin):
    project_path: str = _PROJECT_PATH
    action: str = "start"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/search")
async def code_search(body: SearchRequest):
    """Hybrid semantic + BM25 search across the codebase. Natural language queries supported."""
    try:
        return _run_intel("vc_search", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index")
async def code_index(body: IndexRequest):
    """Start full codebase indexing (background). Poll /code-intel/status for progress."""
    try:
        return _run_intel("vc_index", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] index failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update")
async def code_update(body: IndexRequest):
    """Incrementally update index — only re-indexes changed files."""
    try:
        return _run_intel("vc_update", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def code_status(project_path: str = _PROJECT_PATH):
    """Get indexing progress and collection stats."""
    try:
        return _run_intel("vc_status", {"project_path": project_path})
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/graph/build")
async def graph_build(body: IndexRequest):
    """Build the file-level dependency graph (AST-based, 18 languages)."""
    try:
        return _run_intel("vc_graph_build", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] graph build failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/graph/query")
async def graph_query(body: GraphQueryRequest):
    """Query the dependency graph for a specific file: imports + dependents."""
    try:
        return _run_intel("vc_graph_query", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] graph query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/circular")
async def graph_circular(project_path: str = _PROJECT_PATH):
    """Detect circular dependencies in the codebase."""
    try:
        return _run_intel("vc_graph_circular", {"project_path": project_path})
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] circular deps failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/graph/visualize")
async def graph_visualize(project_path: str = _PROJECT_PATH, mode: str = "html"):
    """Generate interactive HTML or Mermaid diagram of the dependency graph."""
    try:
        return _run_intel("vc_visualize", {"project_path": project_path, "mode": mode, "open": False})
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] visualize failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/impact")
async def code_impact(body: ImpactRequest):
    """Blast radius analysis — what breaks if you change a function or class?"""
    try:
        return _run_intel("vc_impact", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] impact failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flow")
async def code_flow(body: FlowRequest):
    """Trace execution call flow from an entry point."""
    try:
        return _run_intel("vc_flow", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] flow failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/symbol")
async def code_symbol(body: SymbolRequest):
    """360-degree view of a symbol: definition, callers, callees."""
    try:
        return _run_intel("vc_symbol", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] symbol failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols")
async def list_symbols(project_path: str = _PROJECT_PATH, file: str | None = None, query: str | None = None, limit: int = 20):
    """List or search symbols in the codebase."""
    try:
        return _run_intel("vc_symbols", {"project_path": project_path, "file": file, "query": query, "limit": limit})
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] symbols failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context/search")
async def context_search(body: ContextSearchRequest):
    """Search context artifacts (schemas, API specs, architecture docs) alongside code."""
    try:
        return _run_intel("vc_context_search", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] context search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/context")
async def list_context(project_path: str = _PROJECT_PATH):
    """List all indexed context artifacts."""
    try:
        return _run_intel("vc_context", {"project_path": project_path})
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] context list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/watch")
async def code_watch(body: WatchRequest):
    """Start or stop the file watcher for automatic index updates."""
    try:
        return _run_intel("vc_watch", body.model_dump())
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] watch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def code_intel_health():
    """Check VectorCode Intelligence infrastructure: Qdrant, Ollama, Docker."""
    try:
        return _run_intel("vc_health", {})
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] health failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects")
async def list_indexed_projects():
    """List all projects indexed by VectorCode Intelligence."""
    try:
        return _run_intel("vc_projects", {})
    except Exception as e:
        logger.error(f"[VECTOR][api][code_intel] projects failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("OK: code_intel.py router")
