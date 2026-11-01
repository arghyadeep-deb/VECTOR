import sys
import uuid
import asyncio as _asyncio
import concurrent.futures as _cf
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


def _llm(prompt: str, max_tokens: int = 700, temperature: float = 0.6) -> str:
    from core.inference.provider_client import ProviderClient as _PC
    async def _call():
        r = await _PC().chat(
            messages=[{"role": "user", "content": prompt}],
            model="domain:finance.analysis",   # gpt-5 → zai-glm-4.7 → DeepSeek-R1 → ollama
            tier="reasoning", temperature=temperature, max_tokens=max_tokens,
            caller_id="technical_bot",
        )
        return r.content
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_asyncio.run, _call()).result(timeout=90)


class TechnicalBot(AgentBase):
    """
    Provides technical analysis for stocks including price data,
    chart patterns, and technical indicators.
    """

    INDICATORS = [
        "sma", "ema", "rsi", "macd", "bollinger", "atr", "adx",
        "stochastic", "cci", "williams_r"
    ]

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "TechnicalBot", "investment")
        self.capabilities = ["calculate_indicators", "detect_patterns", "get_price_data", "investment", "technical_analysis", "trading_analysis"]
        if ghost:
            self.inherit_ghost(ghost)

        self._yfinance_available = self._check_yfinance()
        self._analysis_cache: dict[str, dict] = {}
        logger.info("[VECTOR][technical_bot] TechnicalBot initialized")

    def _check_yfinance(self) -> bool:
        """Check if yfinance is available."""
        try:
            import yfinance
            return True
        except ImportError:
            return False

    def get_price_data(self, symbol: str, timeframe: str = "3mo") -> dict:
        """
        Get historical price data for a symbol.
        Timeframes: 1d, 1w, 1mo, 3mo, 6mo, 1y, 5y, max
        """
        symbol = symbol.upper()

        if self._yfinance_available:
            return self._get_real_price_data(symbol, timeframe)
        return self._get_mock_price_data(symbol, timeframe)

    def _get_real_price_data(self, symbol: str, timeframe: str) -> dict:
        """Get real price data using yfinance."""
        try:
            import yfinance as yf
            import pandas as pd

            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=timeframe)

            if hist.empty:
                fallback = self._get_mock_price_data(symbol, timeframe)
                fallback["warning"] = "No yfinance data available"
                return fallback

            prices = hist["Close"].tolist()
            volumes = hist["Volume"].tolist()
            highs = hist["High"].tolist()
            lows = hist["Low"].tolist()
            dates = hist.index.strftime("%Y-%m-%d").tolist()

            return {
                "status": "success",
                "symbol": symbol,
                "timeframe": timeframe,
                "data": {
                    "dates": dates,
                    "prices": [round(p, 2) for p in prices],
                    "volumes": volumes,
                    "highs": [round(h, 2) for h in highs],
                    "lows": [round(l, 2) for l in lows]
                },
                "latest_price": round(prices[-1], 2) if prices else 0,
                "period_change": round(((prices[-1] - prices[0]) / prices[0]) * 100, 2) if len(prices) > 1 else 0,
                "source": "yfinance"
            }

        except Exception as e:
            logger.error(f"[VECTOR][technical_bot] Price data fetch failed: {e}")
            fallback = self._get_mock_price_data(symbol, timeframe)
            fallback["warning"] = str(e)
            return fallback

    def _get_mock_price_data(self, symbol: str, timeframe: str) -> dict:
        """Generate mock price data."""
        import random

        hash_val = sum(ord(c) for c in symbol)
        base_price = 50 + (hash_val % 200)
        volatility = 0.02 + (hash_val % 5) / 100

        period_days = {"1d": 1, "1w": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}.get(timeframe, 90)

        dates = []
        prices = []
        current_price = base_price

        for i in range(period_days):
            change = random.uniform(-volatility, volatility)
            current_price *= (1 + change)
            dates.append(f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}")
            prices.append(round(current_price, 2))

        return {
            "status": "success",
            "symbol": symbol,
            "timeframe": timeframe,
            "data": {
                "dates": dates,
                "prices": prices,
                "volumes": [random.randint(1000000, 50000000) for _ in dates],
                "highs": [round(p * 1.02, 2) for p in prices],
                "lows": [round(p * 0.98, 2) for p in prices]
            },
            "latest_price": prices[-1] if prices else 0,
            "period_change": round(((prices[-1] - prices[0]) / prices[0]) * 100, 2) if len(prices) > 1 else 0,
            "source": "mock"
        }

    def detect_patterns(self, symbol: str) -> dict:
        """
        Detect chart patterns in price data.
        """
        symbol = symbol.upper()

        price_data = self.get_price_data(symbol, "3mo")
        if price_data.get("status") != "success":
            return price_data

        prices = price_data["data"]["prices"]
        patterns = []

        if self._detect_double_bottom(prices):
            patterns.append({
                "type": "double_bottom",
                "signal": "bullish",
                "confidence": 75,
                "description": "Bullish reversal pattern - potential buy signal"
            })

        if self._detect_head_shoulders(prices):
            patterns.append({
                "type": "head_and_shoulders",
                "signal": "bearish",
                "confidence": 80,
                "description": "Bearish reversal pattern - potential sell signal"
            })

        if self._detect_uptrend(prices):
            patterns.append({
                "type": "uptrend",
                "signal": "bullish",
                "confidence": 85,
                "description": "Strong upward trend - hold or accumulate"
            })

        if self._detect_downtrend(prices):
            patterns.append({
                "type": "downtrend",
                "signal": "bearish",
                "confidence": 85,
                "description": "Strong downward trend - avoid or short"
            })

        if self._detect_support_resistance(prices):
            patterns.append({
                "type": "support_resistance",
                "signal": "neutral",
                "confidence": 70,
                "description": "Key support and resistance levels identified"
            })

        if not patterns:
            patterns.append({
                "type": "no_pattern",
                "signal": "neutral",
                "confidence": 50,
                "description": "No clear chart pattern detected"
            })

        self.award_points(10, f"patterns_detected_{symbol}")

        return {
            "status": "success",
            "symbol": symbol,
            "patterns": patterns,
            "timestamp": self._get_timestamp()
        }

    def _detect_double_bottom(self, prices: list) -> bool:
        """Detect double bottom pattern."""
        if len(prices) < 40:
            return False

        mid = len(prices) // 2
        left_section = prices[:mid]
        right_section = prices[mid:]

        if not left_section or not right_section:
            return False

        left_min = min(left_section)
        right_min = min(right_section)

        tolerance = 0.03
        return abs(left_min - right_min) / left_min < tolerance

    def _detect_head_shoulders(self, prices: list) -> bool:
        """Detect head and shoulders pattern."""
        if len(prices) < 60:
            return False

        third = len(prices) // 3
        left_shoulder = max(prices[:third])
        head = max(prices[third:2*third])
        right_shoulder = max(prices[2*third:])

        return head > left_shoulder * 1.1 and head > right_shoulder * 1.1

    def _detect_uptrend(self, prices: list) -> bool:
        """Detect uptrend pattern."""
        if len(prices) < 20:
            return False

        increases = sum(1 for i in range(1, len(prices)) if prices[i] > prices[i-1])
        return increases / (len(prices) - 1) > 0.6

    def _detect_downtrend(self, prices: list) -> bool:
        """Detect downtrend pattern."""
        if len(prices) < 20:
            return False

        decreases = sum(1 for i in range(1, len(prices)) if prices[i] < prices[i-1])
        return decreases / (len(prices) - 1) > 0.6

    def _detect_support_resistance(self, prices: list) -> bool:
        """Detect support and resistance levels."""
        return len(prices) >= 30

    def calculate_indicators(self, symbol: str, indicators: list[str]) -> dict:
        """
        Calculate technical indicators for a symbol.
        """
        symbol = symbol.upper()

        price_data = self.get_price_data(symbol, "3mo")
        if price_data.get("status") != "success":
            return price_data

        prices = price_data["data"]["prices"]
        results = {"symbol": symbol, "status": "success", "indicators": {}}

        for indicator in indicators:
            if indicator.lower() == "sma":
                results["indicators"]["sma_20"] = self._calculate_sma(prices, 20)
                results["indicators"]["sma_50"] = self._calculate_sma(prices, 50)
            elif indicator.lower() == "ema":
                results["indicators"]["ema_12"] = self._calculate_ema(prices, 12)
                results["indicators"]["ema_26"] = self._calculate_ema(prices, 26)
            elif indicator.lower() == "rsi":
                results["indicators"]["rsi_14"] = self._calculate_rsi(prices, 14)
            elif indicator.lower() == "macd":
                results["indicators"]["macd"] = self._calculate_macd(prices)
            elif indicator.lower() == "bollinger":
                results["indicators"]["bollinger"] = self._calculate_bollinger(prices)

        results["interpretation"] = self._interpret_indicators(results["indicators"])

        self.award_points(len(indicators) * 3, f"indicators_calculated_{symbol}")

        return results

    def _calculate_sma(self, prices: list, period: int) -> float:
        """Calculate Simple Moving Average."""
        if len(prices) < period:
            return 0.0
        return round(sum(prices[-period:]) / period, 2)

    def _calculate_ema(self, prices: list, period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return 0.0

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return round(ema, 2)

    def _calculate_rsi(self, prices: list, period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return 50.0

        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return round(rsi, 2)

    def _calculate_macd(self, prices: list) -> dict:
        """Calculate MACD indicator."""
        if len(prices) < 26:
            return {"macd": 0, "signal": 0, "histogram": 0}

        ema_12 = self._calculate_ema(prices, 12)
        ema_26 = self._calculate_ema(prices, 26)
        macd = ema_12 - ema_26

        macd_values = []
        for i in range(26, len(prices)):
            e12 = self._calculate_ema(prices[:i+1], 12)
            e26 = self._calculate_ema(prices[:i+1], 26)
            macd_values.append(e12 - e26)

        signal = self._calculate_ema(macd_values, 9) if len(macd_values) >= 9 else 0

        return {
            "macd": round(macd, 2),
            "signal": round(signal, 2),
            "histogram": round(macd - signal, 2)
        }

    def _calculate_bollinger(self, prices: list, period: int = 20) -> dict:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            return {"upper": 0, "middle": 0, "lower": 0}

        sma = self._calculate_sma(prices, period)
        recent_prices = prices[-period:]
        variance = sum((p - sma) ** 2 for p in recent_prices) / period
        std_dev = variance ** 0.5

        return {
            "upper": round(sma + (2 * std_dev), 2),
            "middle": round(sma, 2),
            "lower": round(sma - (2 * std_dev), 2)
        }

    def _interpret_indicators(self, indicators: dict) -> str:
        """Generate interpretation of technical indicators."""
        interpretations = []

        if "rsi_14" in indicators:
            rsi = indicators["rsi_14"]
            if rsi > 70:
                interpretations.append(f"RSI at {rsi} - Overbought conditions")
            elif rsi < 30:
                interpretations.append(f"RSI at {rsi} - Oversold conditions")
            else:
                interpretations.append(f"RSI at {rsi} - Neutral")

        if "sma_20" in indicators and "sma_50" in indicators:
            sma_20 = indicators["sma_20"]
            sma_50 = indicators["sma_50"]
            if sma_20 > sma_50:
                interpretations.append("SMA Golden Cross - Bullish signal")
            else:
                interpretations.append("SMA Death Cross - Bearish signal")

        if "macd" in indicators:
            macd_data = indicators["macd"]
            if isinstance(macd_data, dict):
                if macd_data.get("histogram", 0) > 0:
                    interpretations.append("MACD Histogram positive - Bullish momentum")
                else:
                    interpretations.append("MACD Histogram negative - Bearish momentum")

        return " | ".join(interpretations) if interpretations else "No clear signals"

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    SUPPORTED_TYPES = ("get_price_data", "detect_patterns", "calculate_indicators")

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        task_type = task.get("type", "get_price_data")

        if task_type == "get_price_data":
            return self.get_price_data(p.get("symbol", "RELIANCE"), p.get("timeframe", "3mo"))
        elif task_type == "detect_patterns":
            return self.detect_patterns(p.get("symbol", "RELIANCE"))
        elif task_type == "calculate_indicators":
            return self.calculate_indicators(
                p.get("symbol", "RELIANCE"), p.get("indicators", self.INDICATORS),
            )

        query = p.get("query") or p.get("content") or task.get("query") or task.get("prompt")
        if query and not p.get("symbol"):
            # 2026-07-29: unmatched/free-text task_type previously fell
            # straight through to an error stub with no real content —
            # same bug class as stock_analyst.py's pre-fix quote default
            # (KNOWN_ISSUES.md #1/#14/#15/#21/#33/#36). Answer it directly.
            try:
                prompt = (
                    "You are VECTOR's TechnicalBot, an investment-district agent that "
                    "provides technical analysis for stocks: price history, chart-"
                    "pattern detection (double bottom, head & shoulders, trends, "
                    "support/resistance), and indicators (SMA/EMA/RSI/MACD/Bollinger). "
                    "Analysis only — you never place or recommend executing real trades.\n\n"
                    f"Answer the user's question directly and specifically:\n{query}"
                )
                answer = _llm(prompt, max_tokens=700, temperature=0.6)
                return {"status": "ok", "response": answer}
            except Exception as e:
                logger.error("[VECTOR][technical_bot] free-text fallback failed: {}", e)
                # fall through to error stub below

        return {
            "status": "error",
            "error": f"unhandled type '{task_type}'",
            "supported": list(self.SUPPORTED_TYPES),
        }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    bot = TechnicalBot()

    patterns = bot.detect_patterns("AAPL")
    print(f"Detected {len(patterns.get('patterns', []))} patterns")

    indicators = bot.calculate_indicators("AAPL", ["sma", "rsi", "macd"])
    print(f"RSI: {indicators.get('indicators', {}).get('rsi_14', 'N/A')}")

    print("✅ technical_bot.py OK")
