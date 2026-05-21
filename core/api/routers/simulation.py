"""Simulation router Ã¢â‚¬â€ /simulation/* endpoints for the MiroFish social simulation engine."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/simulation", tags=["simulation"])

_sim_agent = None


def _get_sim_agent():
    global _sim_agent
    if _sim_agent is None:
        from districts.intelligence.vector_social_sim_agent import SocialSimAgent
        _sim_agent = SocialSimAgent()
    return _sim_agent


# Ã¢â€â‚¬Ã¢â€â‚¬ Request models Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

class OntologyRequest(BaseModel):
    document: str

class SimulationRequest(BaseModel):
    csv_path: str = ""
    total_rounds: int = 5
    max_concurrent: int = 3
    platform: str = "twitter"

class InterviewRequest(BaseModel):
    user_id: str
    prompt: str

class ReportRequest(BaseModel):
    trace_db_path: str = ""


# Ã¢â€â‚¬Ã¢â€â‚¬ Endpoints Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

@router.post("/ontology")
async def build_ontology(body: OntologyRequest):
    """Build knowledge graph from a document using LLM-powered entity extraction."""
    try:
        return await _get_sim_agent().run({"type": "build_ontology", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][simulation] ontology failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_simulation(body: SimulationRequest):
    """Run a multi-agent social simulation with LLM-driven agent behaviors."""
    try:
        return await _get_sim_agent().run({"type": "run_simulation", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][simulation] run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/interview")
async def interview_agent(body: InterviewRequest):
    """Interview a simulated agent to get their perspective."""
    try:
        return await _get_sim_agent().run({"type": "interview_agent", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][simulation] interview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report")
async def generate_report(body: ReportRequest):
    """Generate a markdown analysis report from simulation trace data."""
    try:
        return await _get_sim_agent().run({"type": "generate_report", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][simulation] report failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def simulation_status():
    """Get current simulation engine status and capabilities."""
    try:
        from districts.intelligence.vector_social_sim.app.services.vector_simulation_engine import VectorSocialSimEngine
        return {
            "available": True,
            "engine": "VectorSocialSimEngine",
            "action_types": ["CREATE_POST", "LIKE_POST", "REPOST", "COMMENT", "FOLLOW",
                             "UNFOLLOW", "SHARE", "SEARCH", "BROWSE_FEED", "REPORT",
                             "BLOCK", "MUTE", "REPLY", "QUOTE"],
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


if __name__ == "__main__":
    print("OK: simulation.py router")
