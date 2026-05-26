"""VECTOR brain router - /brain/* endpoints."""
import sys

__all__ = [
    "active_hypotheses",
    "add_goal",
    "AddGoalReq",
    "epistemic_staleness",
    "epistemic_summary",
    "generate_hypothesis",
    "GenerateHypothesisReq",
    "get_goals",
    "get_person",
    "get_persons",
    "get_reasoning_chains",
    "immediate_actions",
    "red_team_attack",
    "red_team_audit",
    "RedTeamAttackReq",
    "RedTeamAuditReq",
    "router",
    "synthesize",
    "SynthesizeReq",
    "test_hypothesis",
    "TestHypothesisReq",
    "UpdateBeliefReq",
    "update_person_belief",
    "update_person_trust",
    "UpdateTrustReq",
]

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/brain", tags=["brain"])




@router.get("/goals")
async def get_goals():
    """List all VECTOR goals (LONG/MID/SHORT horizon)."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "get_goals", "params": {}})
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
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "add_goal", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][brain] add_goal failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/goals/immediate")
async def immediate_actions():
    """Get immediate action candidates."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "immediate_actions", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][brain] immediate_actions failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class SynthesizeReq(BaseModel):
    outputs: str = ""
    synthesis_type: str = "daily"

@router.post("/synthesis")
async def synthesize(body: SynthesizeReq):
    """Synthesize multiple district outputs into one narrative."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "synthesize", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][brain] synthesize failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateHypothesisReq(BaseModel):
    observation: str = ""

@router.post("/hypothesis/generate")
async def generate_hypothesis(body: GenerateHypothesisReq):
    """Generate hypothesis from observation."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "generate_hypothesis", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][brain] generate_hypothesis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hypothesis/active")
async def active_hypotheses():
    """List all active untested hypotheses."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "active_hypotheses", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][brain] active_hypotheses failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class TestHypothesisReq(BaseModel):
    hypothesis_id: str = ""
    evidence: str = ""

@router.post("/hypothesis/test")
async def test_hypothesis(body: TestHypothesisReq):
    """Test hypothesis against new evidence."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "test_hypothesis", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][brain] test_hypothesis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RedTeamAttackReq(BaseModel):
    plan: str = ""
    context: str = ""

@router.post("/red-team/attack")
async def red_team_attack(body: RedTeamAttackReq):
    """Adversarial attack on a plan."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "red_team_attack", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][brain] red_team_attack failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RedTeamAuditReq(BaseModel):
    policy: str = ""

@router.post("/red-team/audit")
async def red_team_audit(body: RedTeamAuditReq):
    """Audit a policy for vulnerabilities."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "red_team_audit", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][brain] red_team_audit failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/epistemic/summary")
async def epistemic_summary():
    """VECTOR self-knowledge map."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "epistemic_summary", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][brain] epistemic_summary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/epistemic/staleness")
async def epistemic_staleness():
    """List stale knowledge areas."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "epistemic_staleness", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][brain] epistemic_staleness failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reasoning/chains")
async def get_reasoning_chains(situation: str = "", limit: int = 20):
    """D2 — Return recent reasoning chains for the decision trace timeline.

    Query param `situation` filters by partial match; `limit` caps results (default 20).
    """
    try:
        from core.memory.reasoning_memory import ReasoningMemory
        rm = ReasoningMemory()
        chains = rm.get_recent(limit=limit, situation=situation)
        return {"chains": chains, "count": len(chains)}
    except Exception as e:
        logger.error("[VECTOR][brain] reasoning/chains failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
