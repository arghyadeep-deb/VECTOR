"""VECTOR calls router - /calls/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/calls", tags=["calls"])


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


class ScreenCallReq(BaseModel):
    caller_number: str = ""
    caller_name: str = ""

@router.post("/screen")
async def screen_call(body: ScreenCallReq):
    """Screen incoming call for spam."""
    try:
        return _run("screen_call", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][calls] screen_call failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class TranscribeCallReq(BaseModel):
    audio_path: str = ""
    language: str = "auto"

@router.post("/transcribe")
async def transcribe_call(body: TranscribeCallReq):
    """Transcribe a call recording to text."""
    try:
        return _run("transcribe_call", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][calls] transcribe_call failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class VoiceRespondReq(BaseModel):
    transcript: str = ""
    context: str = ""

@router.post("/respond")
async def voice_respond(body: VoiceRespondReq):
    """Generate AI-driven call response."""
    try:
        return _run("voice_respond", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][calls] voice_respond failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/contacts")
async def list_call_contacts():
    """List call screening whitelist."""
    try:
        return _run("list_call_contacts", {})
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
    try:
        return _run("add_call_contact", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][calls] add_call_contact failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
