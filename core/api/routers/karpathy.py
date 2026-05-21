"""VECTOR karpathy router - /karpathy/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/karpathy", tags=["karpathy"])


def _run(task_type: str, params: dict) -> dict:
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            gov.dispatch({"type": task_type, "params": params})
        )
    finally:
        loop.close()
    return result


class RunTrainingReq(BaseModel):
    script: str = "train.py"
    config: str = ""
    budget_minutes: int = 30

@router.post("/run-training")
async def run_training(body: RunTrainingReq):
    """Execute training run with fixed time budget."""
    try:
        return _run("run_training", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][karpathy] run_training failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class ProposeImprovementReq(BaseModel):
    current_results: str = ""
    model_arch: str = ""

@router.post("/propose-improvement")
async def propose_improvement(body: ProposeImprovementReq):
    """Suggest architectural improvements."""
    try:
        return _run("propose_improvement", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][karpathy] propose_improvement failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class ApplyPatchAndTestReq(BaseModel):
    patch: str = ""
    metric: str = "val_loss"

@router.post("/apply-patch")
async def apply_patch_and_test(body: ApplyPatchAndTestReq):
    """Apply improvement patch and rerun."""
    try:
        return _run("apply_patch_and_test", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][karpathy] apply_patch_and_test failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/experiment-history")
async def experiment_history():
    """Full history of training runs."""
    try:
        return _run("experiment_history", {})
    except Exception as e:
        logger.error("[VECTOR][karpathy] experiment_history failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
