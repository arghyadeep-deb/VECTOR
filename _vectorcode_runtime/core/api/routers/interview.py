"""VECTOR interview router - /interview/* endpoints."""

__all__ = [
    "company_research",
    "CompanyResearchReq",
    "evaluate_answer",
    "EvaluateAnswerReq",
    "generate_question",
    "GenerateQuestionReq",
    "interview_report",
    "InterviewReportReq",
    "router",
    "start_interview",
    "StartInterviewReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/interview", tags=["interview"])


class StartInterviewReq(BaseModel):
    role: str = ""
    company: str = ""
    interview_type: str = "behavioral"

@router.post("/start")
async def start_interview(body: StartInterviewReq):
    """Start a mock interview session."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "start_interview", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][interview] start_interview failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateQuestionReq(BaseModel):
    role: str = ""
    difficulty: str = "medium"
    question_type: str = "behavioral"

@router.post("/generate-question")
async def generate_question(body: GenerateQuestionReq):
    """Generate interview question."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "generate_question", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][interview] generate_question failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class EvaluateAnswerReq(BaseModel):
    question: str = ""
    answer: str = ""
    role: str = ""

@router.post("/evaluate")
async def evaluate_answer(body: EvaluateAnswerReq):
    """Score and give feedback on an interview answer."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "evaluate_answer", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][interview] evaluate_answer failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class CompanyResearchReq(BaseModel):
    company: str = ""
    role: str = ""

@router.post("/company-research")
async def company_research(body: CompanyResearchReq):
    """Research company: culture, hiring patterns."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "company_research", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][interview] company_research failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class InterviewReportReq(BaseModel):
    session_id: str = ""

@router.post("/report")
async def interview_report(body: InterviewReportReq):
    """Generate interview performance analysis report."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "interview_report", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][interview] interview_report failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
