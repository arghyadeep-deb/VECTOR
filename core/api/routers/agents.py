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


@router.post("/award", response_model=AgentAwardResponse)
async def award_agent_endpoint(body: AgentAwardRequest):
    """Award points to an agent (for HP system)."""
    try:
        result = award_agent(body.agent_id, body.points, body.reason)
        if result.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Agent not found: {body.agent_id}")
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error"))
        return AgentAwardResponse(
            status=result.get("status"),
            agent=result.get("agent", {}),
            award=result.get("award", {}),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][agents] award failed: {e}")
        raise HTTPException(status_code=500, detail=f"Award failed: {e}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
