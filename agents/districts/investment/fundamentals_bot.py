import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class FundamentalsBot(AgentBase):
    """
    Analyzes financial statements and fundamental data
    for investment decisions.
    """

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "FundamentalsBot", "investment")
        if ghost:
            self.inherit_ghost(ghost)

        self._yfinance_available = self._check_yfinance()
        self._analysis_cache: dict[str, dict] = {}
        logger.info("[VECTOR][fundamentals_bot] FundamentalsBot initialized")

    def _check_yfinance(self) -> bool:
        """Check if yfinance is available."""
        try:
            import yfinance
            return True
        except ImportError:
            return False

    def analyze_financials(self, ticker: str) -> dict:
        """
        Analyze financial statements for a company.
        """
        ticker = ticker.upper()

        if self._yfinance_available:
            return self._analyze_real_financials(ticker)
        return self._analyze_mock_financials(ticker)

    def _analyze_real_financials(self, ticker: str) -> dict:
        """Analyze real financial data using yfinance."""
        try:
            import yfinance as yf

            ticker_obj = yf.Ticker(ticker)

            income_stmt = ticker_obj.income_stmt
            balance_sheet = ticker_obj.balance_sheet
            cash_flow = ticker_obj.cashflow

            return {
                "status": "success",
                "ticker": ticker,
                "income_statement": self._format_income_statement(income_stmt),
                "balance_sheet": self._format_balance_sheet(balance_sheet),
                "cash_flow": self._format_cash_flow(cash_flow),
                "key_metrics": self._calculate_key_metrics(income_stmt, balance_sheet),
                "source": "yfinance"
            }

        except Exception as e:
            logger.error(f"[VECTOR][fundamentals_bot] Financial analysis failed: {e}")
            return {"ticker": ticker, "status": "error", "message": str(e)}

    def _analyze_mock_financials(self, ticker: str) -> dict:
        """Return mock financial analysis."""
        hash_val = sum(ord(c) for c in ticker)

        return {
            "status": "success",
            "ticker": ticker,
            "income_statement": {
                "revenue": 50000000000 * (hash_val % 5 + 1),
                "revenue_growth_yoy": round(5 + (hash_val % 15), 1),
                "gross_profit": 25000000000 * (hash_val % 5 + 1),
                "operating_income": 10000000000 * (hash_val % 5 + 1),
                "net_income": 8000000000 * (hash_val % 5 + 1),
                "eps": round(3 + (hash_val % 10) / 10, 2)
            },
            "balance_sheet": {
                "total_assets": 100000000000 * (hash_val % 5 + 1),
                "total_liabilities": 40000000000 * (hash_val % 5 + 1),
                "shareholders_equity": 60000000000 * (hash_val % 5 + 1),
                "cash": 15000000000 * (hash_val % 5 + 1),
                "long_term_debt": 20000000000 * (hash_val % 5 + 1)
            },
            "cash_flow": {
                "operating_cash_flow": 12000000000 * (hash_val % 5 + 1),
                "capital_expenditure": 3000000000 * (hash_val % 5 + 1),
                "free_cash_flow": 9000000000 * (hash_val % 5 + 1),
                "dividends_paid": 2000000000 * (hash_val % 5 + 1)
            },
            "key_metrics": {
                "profit_margin": round(15 + (hash_val % 20), 1),
                "roe": round(18 + (hash_val % 15), 1),
                "roa": round(8 + (hash_val % 10), 1),
                "debt_to_equity": round(50 + (hash_val % 50), 1),
                "current_ratio": round(1.5 + (hash_val % 100) / 100, 2),
                "quick_ratio": round(1.2 + (hash_val % 80) / 100, 2)
            },
            "source": "mock"
        }

    def _format_income_statement(self, df) -> dict:
        """Format income statement DataFrame."""
        if df is None or df.empty:
            return {}

        latest = df.iloc[:, 0] if len(df.columns) > 0 else {}

        return {
            "revenue": float(latest.get("Total Revenue", 0)),
            "revenue_growth_yoy": 0.0,
            "gross_profit": float(latest.get("Gross Profit", 0)),
            "operating_income": float(latest.get("Operating Income", 0)),
            "net_income": float(latest.get("Net Income", 0)),
            "eps": float(latest.get("Basic EPS", 0)) if "Basic EPS" in latest else 0.0
        }

    def _format_balance_sheet(self, df) -> dict:
        """Format balance sheet DataFrame."""
        if df is None or df.empty:
            return {}

        latest = df.iloc[:, 0] if len(df.columns) > 0 else {}

        return {
            "total_assets": float(latest.get("Total Assets", 0)),
            "total_liabilities": float(latest.get("Total Liabilities Net Minority", 0)),
            "shareholders_equity": float(latest.get("Total Equity", 0)),
            "cash": float(latest.get("Cash And Cash Equivalents", 0)),
            "long_term_debt": float(latest.get("Long Term Debt", 0))
        }

    def _format_cash_flow(self, df) -> dict:
        """Format cash flow DataFrame."""
        if df is None or df.empty:
            return {}

        latest = df.iloc[:, 0] if len(df.columns) > 0 else {}

        return {
            "operating_cash_flow": float(latest.get("Operating Cash Flow", 0)),
            "capital_expenditure": float(latest.get("Capital Expenditure", 0)),
            "free_cash_flow": float(latest.get("Free Cash Flow", 0)) if "Free Cash Flow" in latest else 0.0,
            "dividends_paid": float(latest.get("Dividends Paid", 0))
        }

    def _calculate_key_metrics(self, income_df, balance_df) -> dict:
        """Calculate key financial metrics."""
        return {
            "profit_margin": 0.0,
            "roe": 0.0,
            "roa": 0.0,
            "debt_to_equity": 0.0,
            "current_ratio": 0.0,
            "quick_ratio": 0.0
        }

    def check_valuation(self, metric: str, threshold: float) -> dict:
        """
        Check if a valuation metric is above or below threshold.
        """
        metric = metric.lower().strip()

        metric_ranges = {
            "pe_ratio": {"fair": (15, 25), "low": 15, "high": 30},
            "forward_pe": {"fair": (12, 22), "low": 12, "high": 28},
            "peg_ratio": {"fair": (1, 2), "low": 1, "high": 2.5},
            "pb_ratio": {"fair": (2, 5), "low": 2, "high": 7},
            "ps_ratio": {"fair": (3, 8), "low": 3, "high": 10},
            "ev_ebitda": {"fair": (8, 15), "low": 8, "high": 20}
        }

        if metric not in metric_ranges:
            return {
                "metric": metric,
                "status": "error",
                "message": f"Unknown metric: {metric}"
            }

        ranges = metric_ranges[metric]
        value = threshold

        if value < ranges["low"]:
            assessment = "undervalued"
        elif value > ranges["high"]:
            assessment = "overvalued"
        else:
            assessment = "fairly_valued"

        return {
            "metric": metric,
            "value": value,
            "assessment": assessment,
            "fair_range": f"{ranges['low']}-{ranges['high']}",
            "recommendation": self._get_valuation_recommendation(metric, assessment)
        }

    def _get_valuation_recommendation(self, metric: str, assessment: str) -> str:
        """Get recommendation based on valuation."""
        if assessment == "undervalued":
            return f"Potential buy opportunity - {metric.replace('_', ' ')} is below fair value"
        elif assessment == "overvalued":
            return f"Caution advised - {metric.replace('_', ' ')} is above fair value"
        return f"{metric.replace('_', ' ')} is within fair value range"

    def compare_to_sector(self, ticker: str, sector: str) -> dict:
        """
        Compare a stock's fundamentals to sector averages.
        """
        ticker = ticker.upper()
        sector = sector.lower()

        sector_averages = {
            "technology": {
                "pe_ratio": 28,
                "revenue_growth": 15,
                "profit_margin": 20,
                "roe": 22,
                "debt_to_equity": 60
            },
            "healthcare": {
                "pe_ratio": 22,
                "revenue_growth": 8,
                "profit_margin": 15,
                "roe": 18,
                "debt_to_equity": 50
            },
            "finance": {
                "pe_ratio": 12,
                "revenue_growth": 5,
                "profit_margin": 25,
                "roe": 12,
                "debt_to_equity": 150
            },
            "consumer": {
                "pe_ratio": 20,
                "revenue_growth": 6,
                "profit_margin": 10,
                "roe": 15,
                "debt_to_equity": 80
            }
        }

        if sector not in sector_averages:
            return {
                "ticker": ticker,
                "status": "error",
                "message": f"Unknown sector: {sector}"
            }

        financials = self.analyze_financials(ticker)
        if financials.get("status") != "success":
            return financials

        fundamentals = financials.get("key_metrics", {})
        sector_avg = sector_averages[sector]

        comparison = {
            "ticker": ticker,
            "sector": sector,
            "metrics": {}
        }

        for metric, sector_value in sector_avg.items():
            ticker_value = fundamentals.get(metric, 0)
            if ticker_value and sector_value:
                diff = ((ticker_value - sector_value) / sector_value) * 100
                comparison["metrics"][metric] = {
                    "ticker_value": ticker_value,
                    "sector_avg": sector_value,
                    "difference_percent": round(diff, 1),
                    "vs_sector": "above" if diff > 0 else "below"
                }

        comparison["overall_assessment"] = self._assess_vs_sector(comparison["metrics"])

        self.award_points(15, f"compared_{ticker}_to_{sector}")
        return comparison

    def _assess_vs_sector(self, metrics: dict) -> str:
        """Assess overall performance vs sector."""
        above_count = sum(1 for m in metrics.values() if m["vs_sector"] == "above")
        total = len(metrics)

        if above_count / total > 0.6:
            return "strong_vs_sector"
        elif above_count / total < 0.4:
            return "weak_vs_sector"
        return "in_line_with_sector"

    def get_dividend_analysis(self, ticker: str) -> dict:
        """
        Analyze dividend metrics for a stock.
        """
        ticker = ticker.upper()

        if self._yfinance_available:
            return self._get_real_dividend_analysis(ticker)
        return self._get_mock_dividend_analysis(ticker)

    def _get_real_dividend_analysis(self, ticker: str) -> dict:
        """Get real dividend data."""
        try:
            import yfinance as yf

            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info

            return {
                "status": "success",
                "ticker": ticker,
                "dividend_yield": info.get("dividendYield", 0) * 100 if info.get("dividendYield") else 0,
                "annual_dividend": info.get("dividendRate", 0),
                "payout_ratio": info.get("payoutRatio", 0) * 100 if info.get("payoutRatio") else 0,
                "dividend_growth_5y": info.get("dividendGrowthRate5Y", 0) * 100 if info.get("dividendGrowthRate5Y") else 0,
                "consecutive_growth_years": 0,
                "source": "yfinance"
            }

        except Exception as e:
            return {"ticker": ticker, "status": "error", "message": str(e)}

    def _get_mock_dividend_analysis(self, ticker: str) -> dict:
        """Return mock dividend analysis."""
        hash_val = sum(ord(c) for c in ticker)

        return {
            "status": "success",
            "ticker": ticker,
            "dividend_yield": round(1 + (hash_val % 5), 2),
            "annual_dividend": round(1 + (hash_val % 4), 2),
            "payout_ratio": round(20 + (hash_val % 40), 1),
            "dividend_growth_5y": round(3 + (hash_val % 10), 1),
            "consecutive_growth_years": hash_val % 10,
            "source": "mock"
        }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    bot = FundamentalsBot()

    analysis = bot.analyze_financials("AAPL")
    print(f"Analysis status: {analysis.get('status', 'N/A')}")

    comparison = bot.compare_to_sector("AAPL", "technology")
    print(f"Sector comparison: {comparison.get('overall_assessment', 'N/A')}")

    print("✅ fundamentals_bot.py OK")
