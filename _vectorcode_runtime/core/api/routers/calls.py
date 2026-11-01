"""VECTOR calls router - /calls/* endpoints."""

import json

__all__ = [
    "add_call_contact",
    "AddCallContactReq",
    "list_call_contacts",
    "router",
    "screen_call",
    "ScreenCallReq",
    "transcribe_call",
    "TranscribeCallReq",
    "voice_respond",
    "VoiceRespondReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/calls", tags=["calls"])


class ScreenCallReq(BaseModel):
    caller_number: str = ""
    caller_name: str = ""

@router.post("/screen")
async def screen_call(body: ScreenCallReq):
    """Screen incoming call for spam."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "screen_call", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][calls] screen_call failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class TranscribeCallReq(BaseModel):
    audio_path: str = ""
    language: str = "auto"

@router.post("/transcribe")
async def transcribe_call(body: TranscribeCallReq):
    """Transcribe a call recording to text."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "transcribe_call", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][calls] transcribe_call failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class VoiceRespondReq(BaseModel):
    transcript: str = ""
    context: str = ""

@router.post("/respond")
async def voice_respond(body: VoiceRespondReq):
    """Generate AI-driven call response."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "voice_respond", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][calls] voice_respond failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/contacts")
async def list_call_contacts():
    """List call screening whitelist."""
    try:
        from core.runtime_paths import data_path

        contacts_path = data_path("call_contacts.json")
        if not contacts_path.exists():
            return {"status": "ok", "contacts": [], "count": 0, "source": "call_contacts.json"}

        raw = json.loads(contacts_path.read_text(encoding="utf-8") or "{}")
        contacts_blob = raw.get("contacts", raw)
        if isinstance(contacts_blob, dict):
            contacts = [
                {"number": number, **details}
                if isinstance(details, dict)
                else {"number": number, "name": str(details)}
                for number, details in contacts_blob.items()
            ]
        elif isinstance(contacts_blob, list):
            contacts = contacts_blob
        else:
            contacts = []

        return {"status": "ok", "contacts": contacts, "count": len(contacts), "source": "call_contacts.json"}
    except Exception as e:
        logger.error("[VECTOR][calls] list_call_contacts failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class AddCallContactReq(BaseModel):
    name: str = ""
    number: str = ""
    tier: str = "known"

@router.post("/contacts/add")
async def add_call_contact(body: AddCallContactReq):
    """Add contact to whitelist."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "add_call_contact", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][calls] add_call_contact failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
