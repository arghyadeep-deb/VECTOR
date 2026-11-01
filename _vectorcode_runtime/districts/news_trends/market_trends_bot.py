"""
Module: agents/news_trends/market_trends_bot.py
District: news_trends | Focus: Market trend tracking, analysis, anomaly alerts
"""

import sys
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
        self.capabilities = ["market", "news_trends", "trends", "venture_pipeline"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.tracked_trends = {}
        self.anomalies = []
        logger.info("[VECTOR][news_trends] MarketTrendsBot ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
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
        failed: list[str] = []
        for keyword in keywords:
            prompt = f"Analyze the current market trend for '{keyword}'. Provide: 1) Current status (rising/stable/falling), 2) Key drivers, 3) 3-month outlook, 4) Risk factors. Keep it concise."
            analysis = self._call_ollama(prompt)
            if not (analysis or "").strip():
                # empty LLM output was being stored as a tracked "trend"
                logger.warning("[VECTOR][news_trends] No analysis returned for '{}'", keyword)
                failed.append(keyword)
                continue

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
            "total_tracked": len(trend_data),
            "failed_keywords": failed,
        }
        if failed:
            result["status"] = "error" if not trend_data else "partial"
            result["error"] = f"no analysis returned for: {', '.join(map(str, failed))}"
        if not trend_data:
            return result

        self.memory.store(
            event_type="trends_tracked",
            content=f"Tracked {len(trend_data)} market trends",
            tags=["market", "trends", "tracking"],
            context=result,
            source="MarketTrendsBot"
        )

        logger.info("[VECTOR][news_trends] Tracked {} trends", len(trend_data))
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
        if not (report or "").strip():
            return {"status": "error", "error": "LLM returned no report", "trend": trend,
                    "report": "", "historical_data_points": len(historical)}

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
            anomaly_type = "unknown"
        else:
            latest = historical[-1]["analysis"]
            prompt = f"""Analyze if this is an anomaly in the trend '{trend_name}':
Latest: {latest[:500]}
History: {json.dumps([h['analysis'][:200] for h in historical[-3:]])}
Detect if: sudden spikes/drops, unusual patterns, breaking news impact, or contradictory data.
Return JSON: {{is_anomaly: bool, confidence: float, anomaly_type: string, message: string}}"""
            response = self._call_ollama(prompt)
            anomaly_type = "unknown"
            if not (response or "").strip():
                # previously reported as a clean "no anomaly" at 0.5 confidence
                return {"status": "error", "error": "LLM returned no anomaly analysis",
                        "trend_name": trend_name, "is_anomaly": False, "anomaly_type": None,
                        "confidence": 0.0, "message": "",
                        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}

            try:
                import re as _re
                json_match = _re.search(r'\{.*\}', response, _re.DOTALL)
                if json_match:
                    anomaly_data = json.loads(json_match.group(0))
                    raw_flag = anomaly_data.get("is_anomaly", False)
                    is_anomaly = (raw_flag.strip().lower() in ("true", "yes", "1")
                                  if isinstance(raw_flag, str) else bool(raw_flag))
                    try:
                        confidence = float(anomaly_data.get("confidence", 0.5))
                    except (TypeError, ValueError):
                        confidence = 0.5
                    message = anomaly_data.get("message", response[:200])
                    anomaly_type = anomaly_data.get("anomaly_type", "unknown")
                else:
                    is_anomaly = False
                    confidence = 0.5
                    message = response[:200]
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


    async def run(self, task: dict) -> dict:
        p = task.get("params") or {}
        keywords = p.get("keywords", ["AI", "startup", "India"])
        if isinstance(keywords, str):
            keywords = [keywords]
        result = self.track_trends(keywords)
        return {"status": "ok", **result}


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