"""VECTOR brain router - /brain/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/brain", tags=["brain"])


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


@router.get("/goals")
async def get_goals():
    """List all VECTOR goals (LONG/MID/SHORT horizon)."""
    try:
        return _run("get_goals", {})
    except Exception as e:
        logger.error("[VECTOR][brain] get_goals failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class AddGoalReq(BaseModel):
    title: str = ""
    horizon: str = "short"
    priority: float = 0.5

@router.post("/goals/add")
async def add_goal(body: AddGoalReq):
    """Add or update a goal."""
    try:
        return _run("add_goal", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][brain] add_goal failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/goals/immediate")
async def immediate_actions():
    """Get immediate action candidates."""
    try:
        return _run("immediate_actions", {})
    except Exception as e:
        logger.error("[VECTOR][brain] immediate_actions failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class SynthesizeReq(BaseModel):
    outputs: str = ""
    synthesis_type: str = "daily"

@router.post("/synthesis")
async def synthesize(body: SynthesizeReq):
    """Synthesize multiple district outputs into one narrative."""
    try:
        return _run("synthesize", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][brain] synthesize failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateHypothesisReq(BaseModel):
    observation: str = ""

@router.post("/hypothesis/generate")
async def generate_hypothesis(body: GenerateHypothesisReq):
    """Generate hypothesis from observation."""
    try:
        return _run("generate_hypothesis", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][brain] generate_hypothesis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hypothesis/active")
async def active_hypotheses():
    """List all active untested hypotheses."""
    try:
        return _run("active_hypotheses", {})
    except Exception as e:
        logger.error("[VECTOR][brain] active_hypotheses failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class TestHypothesisReq(BaseModel):
    hypothesis_id: str = ""
    evidence: str = ""

@router.post("/hypothesis/test")
async def test_hypothesis(body: TestHypothesisReq):
    """Test hypothesis against new evidence."""
    try:
        return _run("test_hypothesis", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][brain] test_hypothesis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RedTeamAttackReq(BaseModel):
    plan: str = ""
    context: str = ""

@router.post("/red-team/attack")
async def red_team_attack(body: RedTeamAttackReq):
    """Adversarial attack on a plan."""
    try:
        return _run("red_team_attack", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][brain] red_team_attack failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RedTeamAuditReq(BaseModel):
    policy: str = ""

@router.post("/red-team/audit")
async def red_team_audit(body: RedTeamAuditReq):
    """Audit a policy for vulnerabilities."""
    try:
        return _run("red_team_audit", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][brain] red_team_audit failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/epistemic/summary")
async def epistemic_summary():
    """VECTOR self-knowledge map."""
    try:
        return _run("epistemic_summary", {})
    except Exception as e:
        logger.error("[VECTOR][brain] epistemic_summary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/epistemic/staleness")
async def epistemic_staleness():
    """List stale knowledge areas."""
    try:
        return _run("epistemic_staleness", {})
    except Exception as e:
        logger.error("[VECTOR][brain] epistemic_staleness failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
