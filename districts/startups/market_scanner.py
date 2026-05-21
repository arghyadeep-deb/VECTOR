"""
Module: agents/startups/market_scanner.py
District: startups | Focus: Scan market, analyze trends, identify gaps
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime
from typing import Optional


class MarketScanner(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="MarketScanner",
            district="startups",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.scan_history = []
        logger.info("[VECTOR][startups] MarketScanner ready")

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

        try:
            import re
            json_match = re.search(r'\{.*\}', scan, re.DOTALL)
            if json_match:
                scan_data = json.loads(json_match.group(0))
            else:
                scan_data = {"segments": [], "pain_points": [scan[:300]], "successful_models": []}
        except json.JSONDecodeError:
            scan_data = {"segments": [], "pain_points": [scan[:300]], "successful_models": []}

        result = {
            "niche": niche,
            "segments": scan_data.get("segments", []),
            "pain_points": scan_data.get("pain_points", []),
            "emerging_niches": scan_data.get("emerging_niches", []),
            "successful_models": scan_data.get("successful_models", []),
            "opportunities_count": len(scan_data.get("segments", [])),
            "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.scan_history.append(result)
        self.memory.store(
            event_type="market_scanned",
            content=f"Scanned {niche} market: {len(scan_data.get('segments', []))} segments found",
            tags=["startups", "market_scan", niche],
            context=result,
            source="MarketScanner"
        )

        logger.info(f"[VECTOR][startups] Market scan for '{niche}': {len(scan_data.get('segments', []))} segments")
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

        try:
            import re
            json_match = re.search(r'\{.*\}', trends, re.DOTALL)
            if json_match:
                trend_data = json.loads(json_match.group(0))
            else:
                trend_data = {"momentum": "stable", "forecast": trends[:200], "confidence": 0.5}
        except json.JSONDecodeError:
            trend_data = {"momentum": "stable", "forecast": trends[:200], "confidence": 0.5}

        result = {
            "niche": niche,
            "trends": trend_data,
            "trend_score": 8 if trend_data.get("momentum") == "accelerating" else 5 if trend_data.get("momentum") == "stable" else 3,
            "analyzed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="trends_analyzed",
            content=f"Trend analysis for '{niche}': momentum={trend_data.get('momentum', 'unknown')}",
            tags=["startups", "trends", niche],
            context=result,
            source="MarketScanner"
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

        try:
            import re
            json_match = re.search(r'\{.*\}', gaps_text, re.DOTALL)
            if json_match:
                gaps_data = json.loads(json_match.group(0))
            else:
                gaps_data = {"gaps": [{"type": "general", "description": gaps_text[:200], "severity": "medium", "opportunity_score": 6}]}
        except json.JSONDecodeError:
            gaps_data = {"gaps": [{"type": "general", "description": gaps_text[:200], "severity": "medium", "opportunity_score": 6}]}

        result = {
            "niche": niche,
            "gaps": gaps_data.get("gaps", []),
            "high_priority_gaps": [g for g in gaps_data.get("gaps", []) if g.get("opportunity_score", 5) >= 8],
            "total_gaps": len(gaps_data.get("gaps", [])),
            "identified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="gaps_identified",
            content=f"Identified {len(gaps_data.get('gaps', []))} market gaps in '{niche}'",
            tags=["startups", "gaps", niche],
            context=result,
            source="MarketScanner"
        )

        logger.info(f"[VECTOR][startups] Identified {len(gaps_data.get('gaps', []))} gaps in '{niche}'")
        return result


    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        result = self.scan_market(p.get("niche", "AI SaaS"))
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = MarketScanner()
    assert agent.district == "startups"

    scan = agent.scan_market("AI SaaS")
    assert "segments" in scan
    assert "opportunities_count" in scan

    trends = agent.analyze_trends("AI SaaS")
    assert "trends" in trends
    assert "momentum" in trends["trends"]

    gaps = agent.identify_gaps("AI SaaS")
    assert "gaps" in gaps
    assert "total_gaps" in gaps
    assert gaps["total_gaps"] >= 1

    print("✅ market_scanner.py OK")