"""VECTOR interview router - /interview/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/interview", tags=["interview"])


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


class StartInterviewReq(BaseModel):
    role: str = ""
    company: str = ""
    interview_type: str = "behavioral"

@router.post("/start")
async def start_interview(body: StartInterviewReq):
    """Start a mock interview session."""
    try:
        return _run("start_interview", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][interview] start_interview failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateQuestionReq(BaseModel):
    role: str = ""
    difficulty: str = "medium"
    question_type: str = "behavioral"

@router.post("/generate-question")
async def generate_question(body: GenerateQuestionReq):
    """Generate interview question."""
    try:
        return _run("generate_question", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][interview] generate_question failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class EvaluateAnswerReq(BaseModel):
    question: str = ""
    answer: str = ""
    role: str = ""

@router.post("/evaluate")
async def evaluate_answer(body: EvaluateAnswerReq):
    """Score and give feedback on an interview answer."""
    try:
        return _run("evaluate_answer", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][interview] evaluate_answer failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class CompanyResearchReq(BaseModel):
    company: str = ""
    role: str = ""

@router.post("/company-research")
async def company_research(body: CompanyResearchReq):
    """Research company: culture, hiring patterns."""
    try:
        return _run("company_research", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][interview] company_research failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class InterviewReportReq(BaseModel):
    session_id: str = ""

@router.post("/report")
async def interview_report(body: InterviewReportReq):
    """Generate interview performance analysis report."""
    try:
        return _run("interview_report", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][interview] interview_report failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
