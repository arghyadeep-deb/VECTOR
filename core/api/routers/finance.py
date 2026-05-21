"""VECTOR finance router - /finance/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/finance", tags=["finance"])


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


class BudgetAnalyzeReq(BaseModel):
    month: str = ""
    data: str = ""

@router.post("/budget-analyze")
async def budget_analyze(body: BudgetAnalyzeReq):
    """Monthly budget variance and forecasts."""
    try:
        return _run("budget_analyze", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][finance] budget_analyze failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expenses")
async def list_expenses():
    """List recent expenses with categories."""
    try:
        return _run("list_expenses", {})
    except Exception as e:
        logger.error("[VECTOR][finance] list_expenses failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class LogExpenseReq(BaseModel):
    amount: float = 0.0
    description: str = ""
    category: str = ""

@router.post("/expenses/log")
async def log_expense(body: LogExpenseReq):
    """Log expense with auto-categorization."""
    try:
        return _run("log_expense", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][finance] log_expense failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class TaxPlanReq(BaseModel):
    income: float = 0.0
    year: int = 2026

@router.post("/tax-plan")
async def tax_plan(body: TaxPlanReq):
    """Tax planning recommendations and deductions."""
    try:
        return _run("tax_plan", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][finance] tax_plan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cost-tracker")
async def llm_cost_summary():
    """LLM API cost usage and budget remaining."""
    try:
        return _run("llm_cost_summary", {})
    except Exception as e:
        logger.error("[VECTOR][finance] llm_cost_summary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
