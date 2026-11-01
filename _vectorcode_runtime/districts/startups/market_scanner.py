"""
Module: agents/startups/market_scanner.py
District: startups | Focus: Scan market, analyze trends, identify gaps
"""
import sys
import asyncio
import datetime

from loguru import logger

from core.config import CONFIG
from districts.startups._base import StartupAgentBase

_MAX_SCAN_HISTORY = 500


class MarketScanner(StartupAgentBase):
    def __init__(self):
        super().__init__("MarketScanner")
        self.capabilities = ["market", "mine_social", "startups", "venture_pipeline"]
        self.scan_history = []
        logger.info("[VECTOR][startups] MarketScanner ready")

    def scan_market(self, niche: str) -> dict:
        logger.info(f"[VECTOR][startups] Scanning market: {niche}")
        self.add_lesson({"action": "scan_market", "niche": niche})

        prompt = f"""Scan the {niche} market and identify:
1. Top 5 market segments with their size and growth
2. Underserved customer needs and pain points
3. Emerging sub-niches within {niche}
4. Successful business models in this space
5. Revenue patterns and pricing models that work

Return JSON: {{segments: [{{name, size, growth_rate, opportunity_level, key_players}}], pain_points: string[], emerging_niches: string[], successful_models: string[]}}"""
        scan = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        scan_data = self._extract_json(scan)
        if scan_data is None:
            # A failed LLM scan must not read as "0 opportunities" and be
            # persisted/recorded as a real scan of this niche.
            return self._llm_error("scan_market", niche=niche)

        result = {
            "niche": niche,
            "segments": scan_data.get("segments", []),
            "pain_points": scan_data.get("pain_points", []),
            "emerging_niches": scan_data.get("emerging_niches", []),
            "successful_models": scan_data.get("successful_models", []),
            "opportunities_count": len(scan_data.get("segments", [])),
            "scanned_at": self._now_iso(),
        }
        self.scan_history.append(result)
        if len(self.scan_history) > _MAX_SCAN_HISTORY:
            del self.scan_history[:-_MAX_SCAN_HISTORY]
        self._store_result(
            "market_scanned",
            f"Scanned {niche} market: {len(scan_data.get('segments', []))} segments found",
            ["startups", "market_scan", niche],
            result,
        )
        logger.info(f"[VECTOR][startups] Market scan for '{niche}': {len(result['segments'])} segments")
        return result

    def analyze_trends(self, niche: str) -> dict:
        logger.info(f"[VECTOR][startups] Analyzing trends in: {niche}")
        self.add_lesson({"action": "analyze_trends", "niche": niche})

        prompt = f"""Analyze market trends for {niche}:
1. Current trend momentum (accelerating/stable/declining)
2. Key drivers of change
3. Technology enablers and disruptors
4. Regulatory impacts
5. Consumer behavior shifts
6. Investment and funding trends
7. 12-month trend forecast

Return JSON: {{momentum: string, key_drivers: string[], technologies: string[], regulatory: string[], consumer_shifts: string[], investment_trend: string, forecast: string, confidence: float}}"""
        trends = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        trend_data = self._extract_json(trends)
        if trend_data is None:
            return self._llm_error("analyze_trends", niche=niche)

        result = {
            "niche": niche,
            "trends": trend_data,
            "trend_score": 8 if trend_data.get("momentum") == "accelerating" else 5 if trend_data.get("momentum") == "stable" else 3,
            "analyzed_at": self._now_iso(),
        }
        self._store_result(
            "trends_analyzed",
            f"Trend analysis for '{niche}': momentum={trend_data.get('momentum', 'unknown')}",
            ["startups", "trends", niche],
            result,
        )
        return result

    def identify_gaps(self, niche: str) -> dict:
        logger.info(f"[VECTOR][startups] Identifying market gaps in: {niche}")
        self.add_lesson({"action": "identify_gaps", "niche": niche})

        prompt = f"""Identify market gaps and untapped opportunities in {niche}:
1. Underserved customer segments
2. Product/service gaps (no good solutions exist)
3. Pricing gaps (too expensive, too cheap, no flexible options)
4. Distribution gaps (no easy access, underserved channels)
5. Technology gaps (outdated solutions, unmet needs)
6. Geography gaps (underserved regions)
7. Timing gaps (solutions that need to exist but don't yet)

Return JSON: {{gaps: [{{type, description, severity: high/medium/low, opportunity_score: 1-10, target_customer: string}}]}}"""
        gaps_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        gaps_data = self._extract_json(gaps_text)
        if gaps_data is None:
            return self._llm_error("identify_gaps", niche=niche)

        result = {
            "niche": niche,
            "gaps": gaps_data.get("gaps", []),
            "high_priority_gaps": [g for g in gaps_data.get("gaps", []) if isinstance(g, dict) and self._num(g.get("opportunity_score"), 5) >= 8],
            "total_gaps": len(gaps_data.get("gaps", [])),
            "identified_at": self._now_iso(),
        }
        self._store_result(
            "gaps_identified",
            f"Identified {len(result['gaps'])} market gaps in '{niche}'",
            ["startups", "gaps", niche],
            result,
        )
        logger.info(f"[VECTOR][startups] Identified {result['total_gaps']} gaps in '{niche}'")
        return result

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        # 2026-07-28: run() never checked task["type"] at all — always
        # scanned "AI SaaS" (or whatever p.get("niche") happened to be)
        # regardless of what was actually asked, since free-text chat
        # dispatch never populates "niche" — same bug class as design
        # district's #33.
        query = p.get("query") or p.get("content") or task.get("query")
        if query and not p.get("niche"):
            history_ctx = f"Recent scans: {len(self.scan_history)} niches scanned so far." if self.scan_history else "No scans run yet."
            return await self.answer_startup_task(query, history_ctx)
        result = self.scan_market(p.get("niche", "AI SaaS"))
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = MarketScanner()
    assert agent.district == "startups"
    scan = agent.scan_market("AI SaaS")
    assert "segments" in scan and "opportunities_count" in scan
    trends = agent.analyze_trends("AI SaaS")
    assert "trends" in trends and "momentum" in trends["trends"]
    gaps = agent.identify_gaps("AI SaaS")
    assert "gaps" in gaps and gaps["total_gaps"] >= 1
    print("OK market_scanner.py")
