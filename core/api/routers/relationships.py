"""VECTOR relationships router - /relationships/* endpoints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/relationships", tags=["relationships"])




@router.get("/contacts")
async def list_contacts():
    """List managed contacts with relationship metadata."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "list_contacts", "params": {}})
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
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "add_contact", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][relationships] add_contact failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class CommunicationStyleReq(BaseModel):
    contact_name: str = ""
    message_history: str = ""

@router.post("/communication-style")
async def communication_style(body: CommunicationStyleReq):
    """Analyze communication style."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "communication_style", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][relationships] communication_style failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class OutreachPlanReq(BaseModel):
    goal: str = "maintain"
    count: int = 3

@router.post("/outreach-plan")
async def outreach_plan(body: OutreachPlanReq):
    """Suggest who to reach out to and how."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "outreach_plan", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][relationships] outreach_plan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
