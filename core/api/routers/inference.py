"""Inference router — /inference/stats."""


__all__ = [
    "inference_run",
    "inference_stats",
    "list_models",
    "list_providers",
    "router",
]


from fastapi import APIRouter
from loguru import logger
import httpx

from core.api.schemas import InferenceStatsResponse
from core.config import CONFIG

router = APIRouter(prefix="/inference", tags=["inference"])

_OLLAMA_HOST = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
if not _OLLAMA_HOST.startswith("http"):
    _OLLAMA_HOST = "http://" + _OLLAMA_HOST

@router.get("/stats", response_model=InferenceStatsResponse)
async def inference_stats():
    try:
        configured = [
            "vector-focus", "vector-reasoning", "vector-coder",
            "vector-ambient", "vector-deep", "vector-chairman",
        ]
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                loaded = [m["name"] for m in r.json().get("models", [])]
                return InferenceStatsResponse(
                    total_models=len(configured),
                    loaded_models=len(loaded),
                    model_list=loaded,
                    status="ok",
                )
            else:
                return InferenceStatsResponse(
                    total_models=len(configured), loaded_models=0,
                    model_list=[], status=f"ollama_error_{r.status_code}",
                )
    except Exception as e:
        logger.warning(f"[VECTOR][api][inference] stats failed: {type(e).__name__}: {e}")
        return InferenceStatsResponse(
            total_models=0, loaded_models=0, model_list=[], status=str(e),
        )

@router.post("/run")
async def inference_run(model: str, prompt: str, system: str = ""):
    """Run a one-shot inference against a local Ollama model."""
    try:
        from core.inference.ollama_safe import chat
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = chat(model=model, messages=messages, timeout=60.0, caller_id="api_inference_run")
        if not response:
            return {"status": "error", "error": "Model returned empty response — check Ollama status"}
        return {"status": "ok", "model": model, "response": response}
    except Exception as e:
        logger.error(f"[VECTOR][api][inference] run failed: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/models")
async def list_models():
    """List all Ollama models with their sizes and status."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                models = r.json().get("models", [])
                return {"status": "ok", "models": models, "count": len(models)}
            return {"status": "error", "models": [], "count": 0}
    except Exception as e:
        return {"status": "error", "error": str(e), "models": [], "count": 0}


@router.get("/providers")
async def list_providers():
    """List all configured LLM providers (Ollama + cloud fallbacks)."""
    try:
        from core.inference.llm_providers import PROVIDER_REGISTRY
        return {
            "providers": list(PROVIDER_REGISTRY.keys()),
            "count": len(PROVIDER_REGISTRY),
        }
    except Exception as e:
        return {"providers": ["ollama"], "count": 1, "note": str(e)}


if __name__ == "__main__":
    print("OK: inference.py")
