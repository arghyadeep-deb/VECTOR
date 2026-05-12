"""Agents router — /agents, /agent/award."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from core.api.schemas import AgentAwardRequest, AgentAwardResponse, AgentListResponse
from core.api.dependencies import get_agent_registry
from core.api.crud import get_agents, get_agent, award_agent

router = APIRouter(prefix="/agents", tags=["agents"])
# Spec requires POST /agent/award (singular) — alias router
router_singular = APIRouter(prefix="/agent", tags=["agents"])


@router.get("", response_model=AgentListResponse)
async def list_agents():
    """List all registered agents with their HP and status."""
    try:
        agents = get_agents()
        return AgentListResponse(agents=agents, count=len(agents))
    except Exception as e:
        logger.error(f"[VECTOR][api][agents] list failed: {e}")
        return AgentListResponse(agents=[], count=0, error=str(e))


@router.get("/{agent_id}")
async def get_agent_endpoint(agent_id: str):
    """Get a specific agent by ID."""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return agent


async def _do_award(body: AgentAwardRequest) -> AgentAwardResponse:
    result = award_agent(body.agent_id, body.points, body.reason)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Agent not found: {body.agent_id}")
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))
    award_data = result.get("award", {})
    new_hp = award_data.get("new_hp", result.get("agent", {}).get("health_points", 0))
    model_upgraded = award_data.get("model_changed", False)
    hp_status = "alive" if new_hp > 200 else ("weakened" if new_hp > 50 else "critical")
    return AgentAwardResponse(
        new_hp=new_hp,
        status=hp_status,
        model_upgraded=model_upgraded,
        agent=result.get("agent", {}),
        award=award_data,
    )


@router.post("/award", response_model=AgentAwardResponse)
async def award_agent_endpoint(body: AgentAwardRequest):
    """Award points to an agent (for HP system)."""
    try:
        return await _do_award(body)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][agents] award failed: {e}")
        raise HTTPException(status_code=500, detail=f"Award failed: {e}")


@router_singular.post("/award", response_model=AgentAwardResponse, include_in_schema=False)
async def award_agent_singular(body: AgentAwardRequest):
    """Spec-path alias: POST /agent/award → /agents/award."""
    try:
        return await _do_award(body)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][agents] award (singular) failed: {e}")
        raise HTTPException(status_code=500, detail=f"Award failed: {e}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
