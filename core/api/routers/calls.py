"""VECTOR calls router - /calls/* endpoints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
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
        logger.error("[VECTOR][calls] screen_call failed: %s", e)
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
        logger.error("[VECTOR][calls] transcribe_call failed: %s", e)
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
        logger.error("[VECTOR][calls] voice_respond failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/contacts")
async def list_call_contacts():
    """List call screening whitelist."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "list_call_contacts", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][calls] list_call_contacts failed: %s", e)
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
        logger.error("[VECTOR][calls] add_call_contact failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
