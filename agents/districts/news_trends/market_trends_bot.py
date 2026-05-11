"""
Module: agents/districts/news_trends/market_trends_bot.py
District: news_trends | Focus: Market trend tracking, analysis, anomaly alerts
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, re
from typing import Optional


class MarketTrendsBot(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="MarketTrendsBot",
            district="news_trends",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.tracked_trends = {}
        self.anomalies = []
        logger.info("[VECTOR][news_trends] MarketTrendsBot ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.ollama_safe import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def track_trends(self, keywords: list[str]) -> dict:
        logger.info(f"[VECTOR][news_trends] Tracking trends: {keywords}")
        self.add_lesson({"action": "track_trends", "keywords": keywords})

        trend_data = []
        for keyword in keywords:
            prompt = f"Analyze the current market trend for '{keyword}'. Provide: 1) Current status (rising/stable/falling), 2) Key drivers, 3) 3-month outlook, 4) Risk factors. Keep it concise."
            analysis = self._call_ollama(prompt)

            trend_data.append({
                "keyword": keyword,
                "analysis": analysis,
                "tracked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

            if keyword not in self.tracked_trends:
                self.tracked_trends[keyword] = []
            self.tracked_trends[keyword].append({
                "analysis": analysis,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

        result = {
            "keywords": keywords,
            "trends": trend_data,
            "total_tracked": len(keywords),
        }

        self.memory.store(
            event_type="trends_tracked",
            content=f"Tracked {len(keywords)} market trends",
            tags=["market", "trends", "tracking"],
            context=result,
            source="MarketTrendsBot"
        )

        logger.info(f"[VECTOR][news_trends] Tracked {len(keywords)} trends")
        return result

    def generate_trend_report(self, trend: str) -> dict:
        logger.info(f"[VECTOR][news_trends] Generating trend report for: {trend}")
        self.add_lesson({"action": "generate_trend_report", "trend": trend})

        historical = self.tracked_trends.get(trend, [])
        history_text = "\n".join([f"- {h['analysis'][:200]}" for h in historical[-5:]]) if historical else "No historical data"

        prompt = f"""Generate a comprehensive market trend report for '{trend}'.
Historical tracking: {history_text}
Include: Executive summary, Current status, Key drivers, Competitive landscape, 6-month forecast, Investment implications, Risk rating (1-10)."""
        report = self._call_ollama(prompt)

        result = {
            "trend": trend,
            "report": report,
            "historical_data_points": len(historical),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="trend_report_generated",
            content=f"Generated trend report for '{trend}'",
            tags=["market", "report", "trends"],
            context=result,
            source="MarketTrendsBot"
        )

        return result

    def alert_anomaly(self, trend_name: str) -> dict:
        logger.info(f"[VECTOR][news_trends] Checking for anomalies in: {trend_name}")
        self.add_lesson({"action": "alert_anomaly", "trend": trend_name})

        historical = self.tracked_trends.get(trend_name, [])
        if len(historical) < 2:
            is_anomaly = False
            confidence = 0.3
            message = "Insufficient historical data for anomaly detection"
        else:
            latest = historical[-1]["analysis"]
            prompt = f"""Analyze if this is an anomaly in the trend '{trend_name}':
Latest: {latest[:500]}
History: {json.dumps([h['analysis'][:200] for h in historical[-3:]])}
Detect if: sudden spikes/drops, unusual patterns, breaking news impact, or contradictory data.
Return JSON: {{is_anomaly: bool, confidence: float, anomaly_type: string, message: string}}"""
            response = self._call_ollama(prompt)

            try:
                import re as _re
                json_match = _re.search(r'\{.*\}', response, _re.DOTALL)
                if json_match:
                    anomaly_data = json.loads(json_match.group(0))
                    is_anomaly = anomaly_data.get("is_anomaly", False)
                    confidence = anomaly_data.get("confidence", 0.5)
                    message = anomaly_data.get("message", response[:200])
                    anomaly_type = anomaly_data.get("anomaly_type", "unknown")
                else:
                    is_anomaly = False
                    confidence = 0.5
                    message = response[:200]
                    anomaly_type = "unknown"
            except json.JSONDecodeError:
                is_anomaly = False
                confidence = 0.5
                message = response[:200]
                anomaly_type = "parsing_error"

        alert = {
            "trend_name": trend_name,
            "is_anomaly": is_anomaly,
            "anomaly_type": anomaly_type if is_anomaly else None,
            "confidence": round(confidence, 2),
            "message": message,
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        if is_anomaly:
            self.anomalies.append(alert)

        self.memory.store(
            event_type="anomaly_alert",
            content=f"Anomaly check for '{trend_name}': is_anomaly={is_anomaly}",
            tags=["market", "anomaly", "alert"],
            context=alert,
            source="MarketTrendsBot"
        )

        return alert


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    bot = MarketTrendsBot()
    assert bot.district == "news_trends"

    result = bot.track_trends(["AI", "semiconductors", "cloud computing"])
    assert "trends" in result
    assert len(result["trends"]) == 3

    report = bot.generate_trend_report("AI")
    assert "report" in report

    alert = bot.alert_anomaly("AI")
    assert "is_anomaly" in alert
    assert "confidence" in alert

    print("✅ market_trends_bot.py OK")