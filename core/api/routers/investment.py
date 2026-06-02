"""Investment router  --  /investment/* endpoints for Fincept, AutoHedge, VibeTranding agents."""


from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/investment", tags=["investment"])


def _get_agent(agent_class_path: str):
    import importlib
    module_path, class_name = agent_class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()


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
        agent = _get_agent("districts.investment.vector_finagent_agent.FinAgentAgent")
        return await agent.run({"type": "investor_analysis", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] analyze failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dcf")
async def dcf_valuation(body: DCFRequest):
    """Run DCF/WACC valuation model for a company."""
    try:
        agent = _get_agent("districts.investment.vector_finagent_agent.FinAgentAgent")
        return await agent.run({"type": "corporate_finance/dcf", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] dcf failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alpha")
async def alpha_discovery(body: AlphaRequest):
    """Discover alpha signals using RSI, MACD, ROC technical indicators."""
    try:
        agent = _get_agent("districts.investment.vector_finagent_agent.FinAgentAgent")
        return await agent.run({"type": "alpha_discovery", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] alpha failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backtest")
async def backtest(body: BacktestRequest):
    """Run quantitative backtest via Fincept's BacktestingPy provider."""
    try:
        agent = _get_agent("districts.investment.vector_finagent_agent.FinAgentAgent")
        return await agent.run({"type": "quant_backtest", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/geopolitics")
async def geopolitics(body: GeopoliticsRequest):
    """Geopolitical risk analysis for investment decisions."""
    try:
        agent = _get_agent("districts.investment.vector_finagent_agent.FinAgentAgent")
        return await agent.run({"type": "geopolitics", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] geopolitics failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


#  --  AutoHedge endpoints  -- 

@router.post("/hedge")
async def hedge_analysis(body: HedgeRequest):
    """Run AutoHedge multi-agent hedge fund analysis (ANALYSIS ONLY, never executes trades)."""
    try:
        agent = _get_agent("districts.investment.vector_hedgebot_agent.HedgeBotAgent")
        return await agent.run({"type": "hedge_run", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] hedge failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hedge/status")
async def hedge_status():
    """Get current AutoHedge session status and portfolio snapshot."""
    try:
        agent = _get_agent("districts.investment.vector_hedgebot_agent.HedgeBotAgent")
        return await agent.run({"type": "hedge_status", "params": {}
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


#  --  VibeTranding endpoints  -- 

@router.post("/research")
async def vt_research(body: VTResearchRequest):
    """Run VibeTranding quantitative research with 74 skills and 9 backtest engines."""
    try:
        agent = _get_agent("districts.investment.vector_backtest_agent.BacktestAgent")
        return await agent.run({"type": "vt_research", "params": body.model_dump()})
    except Exception as e:
        logger.error(f"[VECTOR][api][investment] vt_research failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/research/skills")
async def vt_skills():
    """List all 74 quantitative research skills available in VibeTranding."""
    try:
        agent = _get_agent("districts.investment.vector_backtest_agent.BacktestAgent")
        return await agent.run({"type": "list_skills", "params": {}
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio")
async def get_portfolio():
    """Get current portfolio summary — positions, value, and day P&L.
    Returns safe stub values if the StockAnalyst is unavailable.
    """
    try:
        agent = _get_agent("districts.investment.stock_analyst.StockAnalyst")
        result = await agent.run({"type": "portfolio_summary", "params": {}})
        return result
    except Exception as e:
        logger.warning(f"[VECTOR][api][investment] portfolio fallback: {e}")
        return {
            "status": "ok",
            "positions": [],
            "portfolio_value": 0.0,
            "day_pnl": 0.0,
            "alerts": [],
            "note": "StockAnalyst not available — wire districts.investment.stock_analyst",
        }


@router.get("/market-status")
async def get_market_status():
    """Return open/closed status for US, India, and crypto markets."""
    import datetime

    def _market_open(open_h: int, open_m: int, close_h: int, close_m: int, tz_offset: float) -> bool:
        """Very lightweight check — no pytz required."""
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        local_h = (utc_now.hour + tz_offset) % 24
        local_m = utc_now.minute
        local_mins = local_h * 60 + local_m
        open_mins = open_h * 60 + open_m
        close_mins = close_h * 60 + close_m
        weekday = utc_now.weekday()  # 0=Mon … 6=Sun
        if weekday >= 5:  # Sat / Sun — all equity markets closed
            return False
        return open_mins <= local_mins < close_mins

    # UTC offsets: IST = +5.5, ET = -4 (EDT, summer), crypto always open
    india_open  = _market_open(9, 15, 15, 30, 5.5)
    us_open     = _market_open(9, 30, 16, 0, -4.0)

    return {
        "us":     {"open": us_open,    "label": "NYSE/NASDAQ",  "tz": "ET"},
        "india":  {"open": india_open, "label": "NSE/BSE",      "tz": "IST"},
        "crypto": {"open": True,       "label": "Crypto 24/7",  "tz": "UTC"},
    }


if __name__ == "__main__":
    print("OK: investment.py router")
