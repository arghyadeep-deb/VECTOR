"""VECTOR brain router - /brain/* endpoints."""

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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger
from core.api.cache import goals_cache

router = APIRouter(prefix="/brain", tags=["brain"])


def _goal_system():
    from core.brain.goal_system import GoalSystem
    return GoalSystem()


@router.get("/goals")
async def get_goals():
    """List all VECTOR goals (LONG/MID/SHORT horizon)."""
    cached = goals_cache.get("brain_goals")
    if cached:
        return cached
    try:
        result = {"goals": _goal_system().get_active_goals()}
        goals_cache.set("brain_goals", result)
        return result
    except Exception as e:
        logger.error("[VECTOR][brain] get_goals failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class AddGoalReq(BaseModel):
    title: str = ""
    horizon: str = "short"
    priority: float = 0.5

@router.post("/goals/add")
async def add_goal(body: AddGoalReq):
    """Add or update a goal."""
    goals_cache.invalidate()  # new goal — bust all goals cache entries
    try:
        goal_id = _goal_system().add_goal(
            title=body.title,
            horizon=body.horizon,
            priority=int(body.priority),
        )
        return {"status": "ok", "goal_id": goal_id}
    except Exception as e:
        logger.error("[VECTOR][brain] add_goal failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/goals/immediate")
async def immediate_actions():
    """Get immediate action candidates."""
    try:
        return {"actions": _goal_system().generate_immediate_actions()}
    except Exception as e:
        logger.error("[VECTOR][brain] immediate_actions failed: {}", e)
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
        logger.error("[VECTOR][brain] synthesize failed: {}", e)
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
        logger.error("[VECTOR][brain] generate_hypothesis failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hypothesis/active")
async def active_hypotheses():
    """List all active untested hypotheses."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "active_hypotheses", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][brain] active_hypotheses failed: {}", e)
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
        logger.error("[VECTOR][brain] test_hypothesis failed: {}", e)
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
        logger.error("[VECTOR][brain] red_team_attack failed: {}", e)
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
        logger.error("[VECTOR][brain] red_team_audit failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/epistemic/summary")
async def epistemic_summary():
    """VECTOR self-knowledge map."""
    try:
        from core.brain.epistemic_tracker import EpistemicTracker

        tracker = EpistemicTracker()
        summary = tracker.get_knowledge_summary()
        return {"status": "ok", "summary": summary, **summary}
    except Exception as e:
        logger.error("[VECTOR][brain] epistemic_summary failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/epistemic/staleness")
async def epistemic_staleness():
    """List stale knowledge areas."""
    try:
        from core.brain.epistemic_tracker import EpistemicTracker

        tracker = EpistemicTracker()
        stale_claims = tracker.get_stale_claims()
        return {"status": "ok", "stale_claims": stale_claims, "count": len(stale_claims)}
    except Exception as e:
        logger.error("[VECTOR][brain] epistemic_staleness failed: {}", e)
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
        logger.error("[VECTOR][brain] reasoning/chains failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── D3 — Person knowledge graph endpoints ──────────────────────────────────


class UpdateBeliefReq(BaseModel):
    key: str
    value: str
    confidence: float = 0.8


class UpdateTrustReq(BaseModel):
    delta: float


@router.get("/persons")
async def get_persons():
    """D3 — Return all known persons for the knowledge graph nodes."""
    try:
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        persons = pm.get_all_persons()
        return {"persons": persons, "count": len(persons)}
    except Exception as e:
        logger.error("[VECTOR][brain] persons list failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/persons/{person_id}")
async def get_person(person_id: str):
    """D3 — Return full model for one person: beliefs, preferences, interaction_history."""
    try:
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        model = pm.get_model(person_id)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
        history = pm.get_interaction_history(person_id, limit=20)
        return {"person": model, "interaction_history": history}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[VECTOR][brain] person model failed for {}: {}", person_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/persons/{person_id}/belief")
async def update_person_belief(person_id: str, body: UpdateBeliefReq):
    """D3 — Inline-edit a person belief from the dashboard."""
    try:
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        if not pm.person_exists(person_id):
            raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
        ok = pm.update_belief(person_id, body.key, body.value, body.confidence)
        return {"updated": ok, "person_id": person_id, "key": body.key}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[VECTOR][brain] update_belief failed for {}: {}", person_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/persons/{person_id}/trust")
async def update_person_trust(person_id: str, body: UpdateTrustReq):
    """D3 — Inline-edit trust level for a person from the dashboard."""
    try:
        from core.brain.person_model import PersonModel
        pm = PersonModel()
        if not pm.person_exists(person_id):
            raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
        new_trust = pm.update_trust(person_id, body.delta)
        return {"updated": True, "person_id": person_id, "new_trust": new_trust}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[VECTOR][brain] update_trust failed for {}: {}", person_id, e)
        raise HTTPException(status_code=500, detail=str(e))
