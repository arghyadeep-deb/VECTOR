"""VECTOR finance router - /finance/* endpoints."""

__all__ = [
    "budget_analyze",
    "BudgetAnalyzeReq",
    "list_expenses",
    "llm_cost_summary",
    "log_expense",
    "LogExpenseReq",
    "router",
    "tax_plan",
    "TaxPlanReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/finance", tags=["finance"])


class BudgetAnalyzeReq(BaseModel):
    month: str = ""
    data: str = ""

@router.post("/budget-analyze")
async def budget_analyze(body: BudgetAnalyzeReq):
    """Monthly budget variance and forecasts."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "budget_analyze", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][finance] budget_analyze failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expenses")
async def list_expenses():
    """List recent expenses with categories."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "list_expenses", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][finance] list_expenses failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class LogExpenseReq(BaseModel):
    amount: float = 0.0
    description: str = ""
    category: str = ""

@router.post("/expenses/log")
async def log_expense(body: LogExpenseReq):
    """Log expense with auto-categorization."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "log_expense", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][finance] log_expense failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class TaxPlanReq(BaseModel):
    income: float = 0.0
    year: int = 2026

@router.post("/tax-plan")
async def tax_plan(body: TaxPlanReq):
    """Tax planning recommendations and deductions."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "tax_plan", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][finance] tax_plan failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cost-tracker")
async def llm_cost_summary():
    """LLM API cost usage and budget remaining."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "llm_cost_summary", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][finance] llm_cost_summary failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
