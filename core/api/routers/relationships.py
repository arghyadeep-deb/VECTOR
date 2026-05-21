"""VECTOR relationships router - /relationships/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/relationships", tags=["relationships"])


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


@router.get("/contacts")
async def list_contacts():
    """List managed contacts with relationship metadata."""
    try:
        return _run("list_contacts", {})
    except Exception as e:
        logger.error("[VECTOR][relationships] list_contacts failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class AddContactReq(BaseModel):
    name: str = ""
    tier: str = "acquaintance"
    interests: str = ""

@router.post("/contacts/add")
async def add_contact(body: AddContactReq):
    """Add or update a contact."""
    try:
        return _run("add_contact", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][relationships] add_contact failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class CommunicationStyleReq(BaseModel):
    contact_name: str = ""
    message_history: str = ""

@router.post("/communication-style")
async def communication_style(body: CommunicationStyleReq):
    """Analyze communication style."""
    try:
        return _run("communication_style", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][relationships] communication_style failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class OutreachPlanReq(BaseModel):
    goal: str = "maintain"
    count: int = 3

@router.post("/outreach-plan")
async def outreach_plan(body: OutreachPlanReq):
    """Suggest who to reach out to and how."""
    try:
        return _run("outreach_plan", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][relationships] outreach_plan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
