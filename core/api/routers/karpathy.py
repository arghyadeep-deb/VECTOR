"""VECTOR karpathy router - /karpathy/* endpoints."""

__all__ = [
    "apply_patch_and_test",
    "ApplyPatchAndTestReq",
    "experiment_history",
    "propose_improvement",
    "ProposeImprovementReq",
    "router",
    "run_training",
    "RunTrainingReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/karpathy", tags=["karpathy"])


class RunTrainingReq(BaseModel):
    script: str = "train.py"
    config: str = ""
    budget_minutes: int = 30

@router.post("/run-training")
async def run_training(body: RunTrainingReq):
    """Execute training run with fixed time budget."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "run_training", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][karpathy] run_training failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class ProposeImprovementReq(BaseModel):
    current_results: str = ""
    model_arch: str = ""

@router.post("/propose-improvement")
async def propose_improvement(body: ProposeImprovementReq):
    """Suggest architectural improvements."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "propose_improvement", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][karpathy] propose_improvement failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class ApplyPatchAndTestReq(BaseModel):
    patch: str = ""
    metric: str = "val_loss"

@router.post("/apply-patch")
async def apply_patch_and_test(body: ApplyPatchAndTestReq):
    """Apply improvement patch and rerun."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "apply_patch_and_test", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][karpathy] apply_patch_and_test failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/experiment-history")
async def experiment_history():
    """Full history of training runs."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "experiment_history", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][karpathy] experiment_history failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
