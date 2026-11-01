"""Investment router  --  /investment/* endpoints for Fincept, AutoHedge, VibeTranding agents."""


import importlib
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/investment", tags=["investment"])

# Module-level agent cache — prevents a new DB connection on every request.
_agent_cache: dict[str, Any] = {}


def _get_agent(agent_class_path: str):
    """Return a cached agent instance for the given dotted class path.

    On first call the module is imported, the class is instantiated, and the
    result is stored in ``_agent_cache``.  Subsequent calls return the cached
    instance immediately, avoiding repeated DB connections and heavy __init__
    work on every HTTP request.
    """
    if agent_class_path not in _agent_cache:
        try:
            module_path, class_name = agent_class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            _agent_cache[agent_class_path] = cls()
        except Exception as e:
            logger.warning(
                "[VECTOR][api][investment] {} unavailable: {}", agent_class_path, e
            )
            return None
    return _agent_cache[agent_class_path]


#  --  Request models  -- 

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


#  --  Fincept endpoints  -- 

@router.post("/analyze")
async def stock_analysis(body: StockAnalysisRequest):
    """Run comprehensive stock analysis via Fincept terminal intelligence."""
    try:
        agent = _get_agent("districts.investment.finagent_agent.FinAgentAgent")
        if agent is None:
            raise HTTPException(status_code=503, detail="FinAgentAgent unavailable")
        return await agent.run({"type": "investor_analysis", "params": body.model_dump()})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] analyze failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dcf")
async def dcf_valuation(body: DCFRequest):
    """Run DCF/WACC valuation model for a company."""
    try:
        agent = _get_agent("districts.investment.finagent_agent.FinAgentAgent")
        if agent is None:
            raise HTTPException(status_code=503, detail="FinAgentAgent unavailable")
        return await agent.run({"type": "corporate_finance/dcf", "params": body.model_dump()})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] dcf failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alpha")
async def alpha_discovery(body: AlphaRequest):
    """Discover alpha signals using RSI, MACD, ROC technical indicators."""
    try:
        agent = _get_agent("districts.investment.finagent_agent.FinAgentAgent")
        if agent is None:
            raise HTTPException(status_code=503, detail="FinAgentAgent unavailable")
        return await agent.run({"type": "alpha_discovery", "params": body.model_dump()})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] alpha failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backtest")
async def backtest(body: BacktestRequest):
    """Run quantitative backtest via Fincept's BacktestingPy provider."""
    try:
        agent = _get_agent("districts.investment.finagent_agent.FinAgentAgent")
        if agent is None:
            raise HTTPException(status_code=503, detail="FinAgentAgent unavailable")
        return await agent.run({"type": "quant_backtest", "params": body.model_dump()})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/geopolitics")
async def geopolitics(body: GeopoliticsRequest):
    """Geopolitical risk analysis for investment decisions."""
    try:
        agent = _get_agent("districts.investment.finagent_agent.FinAgentAgent")
        if agent is None:
            raise HTTPException(status_code=503, detail="FinAgentAgent unavailable")
        return await agent.run({"type": "geopolitics", "params": body.model_dump()})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] geopolitics failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


#  --  AutoHedge endpoints  --

@router.post("/hedge")
async def hedge_analysis(body: HedgeRequest):
    """Run AutoHedge multi-agent hedge fund analysis (ANALYSIS ONLY, never executes trades)."""
    try:
        agent = _get_agent("districts.investment.hedgebot_agent.HedgeBotAgent")
        if agent is None:
            raise HTTPException(status_code=503, detail="HedgeBotAgent unavailable")
        return await agent.run({"type": "hedge_run", "params": body.model_dump()})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] hedge failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hedge/status")
async def hedge_status():
    """Get current AutoHedge session status and portfolio snapshot."""
    try:
        agent = _get_agent("districts.investment.hedgebot_agent.HedgeBotAgent")
        if agent is None:
            raise HTTPException(status_code=503, detail="HedgeBotAgent unavailable")
        return await agent.run({"type": "hedge_status", "params": {}})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


#  --  VibeTranding endpoints  --

@router.post("/research")
async def vt_research(body: VTResearchRequest):
    """Run VibeTranding quantitative research with 74 skills and 9 backtest engines."""
    try:
        agent = _get_agent("districts.investment.backtest_agent.BacktestAgent")
        if agent is None:
            raise HTTPException(status_code=503, detail="BacktestAgent unavailable")
        return await agent.run({"type": "vt_research", "params": body.model_dump()})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] vt_research failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/research/skills")
async def vt_skills():
    """List all 74 quantitative research skills available in VibeTranding."""
    try:
        agent = _get_agent("districts.investment.backtest_agent.BacktestAgent")
        if agent is None:
            raise HTTPException(status_code=503, detail="BacktestAgent unavailable")
        return await agent.run({"type": "list_skills", "params": {}})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio")
async def get_portfolio():
    """Get current portfolio summary: positions, value, and day P&L."""
    try:
        agent = _get_agent("districts.investment.stock_analyst.StockAnalyst")
        if agent is None:
            raise HTTPException(status_code=503, detail="StockAnalyst unavailable")
        result = await agent.run({"type": "portfolio_summary", "params": {}})
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] portfolio failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market-status")
async def get_market_status():
    """Return open/closed status for US, India, and crypto markets."""
    # Phase 3 audit (2026-10-02): this endpoint used to re-implement market-hours
    # math itself with a hardcoded US ET offset of -4.0 ("EDT, summer") applied
    # YEAR-ROUND -- wrong for the ~5 months/year the US is actually on EST
    # (UTC-5), which would report the market as open/closed an hour off during
    # that window. core/utils/market_hours.py already does this correctly via
    # ZoneInfo("America/New_York"), which resolves real DST transitions from the
    # IANA database. Delegate to it instead of keeping two implementations.
    from core.utils.market_hours import is_market_open

    return {
        "us":     {"open": is_market_open("us-stock"),    "label": "NYSE/NASDAQ",  "tz": "ET"},
        "india":  {"open": is_market_open("india-stock"), "label": "NSE/BSE",      "tz": "IST"},
        "crypto": {"open": True,                          "label": "Crypto 24/7",  "tz": "UTC"},
    }


if __name__ == "__main__":
    print("OK: investment.py router")
