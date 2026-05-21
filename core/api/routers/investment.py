"""Investment router — /investment/* endpoints for Fincept, AutoHedge, VibeTranding agents."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/investment", tags=["investment"])


def _run_agent(agent_class_path: str, task_type: str, params: dict) -> dict:
    import asyncio, importlib
    module_path, class_name = agent_class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    AgentClass = getattr(module, class_name)
    agent = AgentClass()
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(agent.run({"type": task_type, "params": params}))
    loop.close()
    return result


# ── Request models ────────────────────────────────────────────────────────────

class StockAnalysisRequest(BaseModel):
    symbol: str
    analysis_type: str = "full"

class DCFRequest(BaseModel):
    company_name: str
    revenue: float = 0.0
    growth_rate: float = 0.1
    discount_rate: float = 0.1

class AlphaRequest(BaseModel):
    symbols: list[str]
    lookback_days: int = 30

class BacktestRequest(BaseModel):
    strategy: str
    symbols: list[str]
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 10000.0

class GeopoliticsRequest(BaseModel):
    query: str

class HedgeRequest(BaseModel):
    task: str
    portfolio_value: float = 0.0
    risk_tolerance: str = "moderate"

class VTResearchRequest(BaseModel):
    task: str
    symbols: list[str] = []

class MiroFishRequest(BaseModel):
    action: str
    document: str = ""
    csv_path: str = ""
    total_rounds: int = 5
    max_concurrent: int = 3


# ── Fincept endpoints ─────────────────────────────────────────────────────────

@router.post("/analyze")
async def stock_analysis(body: StockAnalysisRequest):
    """Run comprehensive stock analysis via Fincept terminal intelligence."""
    try:
        return _run_agent(
            "districts.investment.vector_finagent_agent.FinAgentAgent",
            "investor_analysis",
            body.model_dump()
        )
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] analyze failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dcf")
async def dcf_valuation(body: DCFRequest):
    """Run DCF/WACC valuation model for a company."""
    try:
        return _run_agent(
            "districts.investment.vector_finagent_agent.FinAgentAgent",
            "corporate_finance/dcf",
            body.model_dump()
        )
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] dcf failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alpha")
async def alpha_discovery(body: AlphaRequest):
    """Discover alpha signals using RSI, MACD, ROC technical indicators."""
    try:
        return _run_agent(
            "districts.investment.vector_finagent_agent.FinAgentAgent",
            "alpha_discovery",
            body.model_dump()
        )
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] alpha failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backtest")
async def backtest(body: BacktestRequest):
    """Run quantitative backtest via Fincept's BacktestingPy provider."""
    try:
        return _run_agent(
            "districts.investment.vector_finagent_agent.FinAgentAgent",
            "quant_backtest",
            body.model_dump()
        )
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/geopolitics")
async def geopolitics(body: GeopoliticsRequest):
    """Geopolitical risk analysis for investment decisions."""
    try:
        return _run_agent(
            "districts.investment.vector_finagent_agent.FinAgentAgent",
            "geopolitics",
            body.model_dump()
        )
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] geopolitics failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── AutoHedge endpoints ───────────────────────────────────────────────────────

@router.post("/hedge")
async def hedge_analysis(body: HedgeRequest):
    """Run AutoHedge multi-agent hedge fund analysis (ANALYSIS ONLY, never executes trades)."""
    try:
        return _run_agent(
            "districts.investment.vector_hedgebot_agent.HedgeBotAgent",
            "hedge_run",
            body.model_dump()
        )
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] hedge failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hedge/status")
async def hedge_status():
    """Get current AutoHedge session status and portfolio snapshot."""
    try:
        return _run_agent(
            "districts.investment.vector_hedgebot_agent.HedgeBotAgent",
            "hedge_status",
            {}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── VibeTranding endpoints ────────────────────────────────────────────────────

@router.post("/research")
async def vt_research(body: VTResearchRequest):
    """Run VibeTranding quantitative research with 74 skills and 9 backtest engines."""
    try:
        return _run_agent(
            "districts.investment.vector_backtest_agent.BacktestAgent",
            "vt_research",
            body.model_dump()
        )
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] vt_research failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/research/skills")
async def vt_skills():
    """List all 74 quantitative research skills available in VibeTranding."""
    try:
        return _run_agent(
            "districts.investment.vector_backtest_agent.BacktestAgent",
            "list_skills",
            {}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("OK: investment.py router")
