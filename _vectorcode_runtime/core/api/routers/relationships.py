"""VECTOR relationships router - /relationships/* endpoints."""

__all__ = [
    "add_contact",
    "AddContactReq",
    "communication_style",
    "CommunicationStyleReq",
    "list_contacts",
    "outreach_plan",
    "OutreachPlanReq",
    "router",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/relationships", tags=["relationships"])


@router.get("/contacts")
async def list_contacts():
    """List managed contacts with relationship metadata."""
    try:
        from core.relationships.schema import get_connection
        from core.runtime_paths import data_path

        db_path = data_path("contacts.db")
        if not db_path.exists():
            return {"status": "ok", "contacts": [], "total_contacts": 0, "source": "contacts.db"}

        with get_connection(db_path) as conn:
            has_contacts = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'contacts'"
            ).fetchone()
            if not has_contacts:
                return {"status": "ok", "contacts": [], "total_contacts": 0, "source": "contacts.db"}
            cursor = conn.execute(
                """
                SELECT name, phone, email, notes, added_at, last_contacted, contact_count
                FROM contacts
                ORDER BY name COLLATE NOCASE ASC
                LIMIT 500
                """
            )
            contacts = [dict(row) for row in cursor.fetchall()]
        return {
            "status": "ok",
            "contacts": contacts,
            "total_contacts": len(contacts),
            "source": "contacts.db",
        }
    except Exception as e:
        logger.error("[VECTOR][relationships] list_contacts failed: {}", e)
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
        logger.error("[VECTOR][relationships] add_contact failed: {}", e)
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
        logger.error("[VECTOR][relationships] communication_style failed: {}", e)
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
        logger.error("[VECTOR][relationships] outreach_plan failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
