"""
Module: agents/startups/competitor_spy.py
District: startups | Focus: Analyze competitors, track movements, generate reports
"""
import sys
import asyncio
import json

from loguru import logger

from core.config import CONFIG
from districts.startups._base import StartupAgentBase

_MAX_COMPETITOR_MOVES = 500


class CompetitorSpy(StartupAgentBase):
    def __init__(self):
        super().__init__("CompetitorSpy")
        self.capabilities = ["competitor", "startups", "venture_pipeline"]
        self.competitor_profiles: dict = {}
        self.movement_history: dict = {}
        logger.info("[VECTOR][startups] CompetitorSpy ready")

    def analyze_competitor(self, name: str) -> dict:
        logger.info(f"[VECTOR][startups] Analyzing competitor: {name}")
        self.add_lesson({"action": "analyze_competitor", "competitor": name})

        prompt = f"""Perform a comprehensive competitive analysis of '{name}':
Business model, target customers, products/pricing, strengths, weaknesses, market share, funding, technology, team quality, customer sentiment.
Return JSON: {{name, business_model: string, target_market: string, products: string[], pricing: string, strengths: string[], weaknesses: string[], market_share: string, funding: string, overall_strength: strong/moderate/weak, key_insight: string}}"""
        analysis = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        profile = self._extract_json(analysis)
        if profile is None:
            # No canned "moderate strength" profile for a failed analysis.
            return self._llm_error("analyze_competitor", competitor_name=name)
        self.competitor_profiles[name] = profile

        result = {"competitor_name": name, "profile": profile, "analyzed_at": self._now_iso()}
        self._store_result("competitor_analyzed",
                           f"Analyzed competitor '{name}': {profile.get('overall_strength', 'unknown')} strength",
                           ["startups", "competitor", name], result)
        return result

    def track_movements(self, competitor_name: str) -> dict:
        logger.info(f"[VECTOR][startups] Tracking movements for: {competitor_name}")
        self.add_lesson({"action": "track_movements", "competitor": competitor_name})

        profile = self.competitor_profiles.get(competitor_name, {})
        prompt = f"""Track recent strategic moves for '{competitor_name}':
Current profile: {json.dumps(profile)[:500]}
Look for: product launches, marketing changes, pricing adjustments, partnerships, hiring, funding, expansion.
Return JSON: {{recent_moves: [{{date: string, move_type: string, description: string, impact: high/medium/low}}], strategic_direction: string, threat_level: high/medium/low, recommended_response: string}}"""
        movements = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        move_data = self._extract_json(movements)
        if move_data is None:
            # Failed tracking must not read as "no moves, medium threat".
            return self._llm_error("track_movements", competitor_name=competitor_name)
        if not isinstance(move_data.get("recent_moves"), list):
            move_data["recent_moves"] = []

        if competitor_name not in self.movement_history:
            self.movement_history[competitor_name] = []
        for move in move_data.get("recent_moves", []):
            self.movement_history[competitor_name].append({"move": move, "tracked_at": self._now_iso()})
        if len(self.movement_history[competitor_name]) > _MAX_COMPETITOR_MOVES:
            del self.movement_history[competitor_name][:-_MAX_COMPETITOR_MOVES]

        result = {
            "competitor_name": competitor_name,
            "recent_moves": move_data.get("recent_moves", []),
            "strategic_direction": move_data.get("strategic_direction", ""),
            "threat_level": move_data.get("threat_level", "medium"),
            "total_moves_tracked": len(self.movement_history.get(competitor_name, [])),
            "tracked_at": self._now_iso(),
        }
        self._store_result("movements_tracked",
                           f"Tracked {len(result['recent_moves'])} moves for '{competitor_name}'",
                           ["startups", "tracking", competitor_name], result)
        return result

    def generate_competitive_report(self) -> dict:
        logger.info("[VECTOR][startups] Generating competitive analysis report")
        self.add_lesson({"action": "generate_competitive_report"})

        competitors = list(self.competitor_profiles.keys())
        movements_summary = {
            name: {
                "total_moves": len(history),
                "latest_move": history[-1]["move"] if history else None,
                "threat_level": "high" if len(history) > 5 else "medium" if len(history) > 2 else "low",
            }
            for name, history in self.movement_history.items()
        }

        prompt = f"""Generate a comprehensive competitive analysis report:
Competitors analyzed: {len(competitors)}
Profiles: {json.dumps(list(self.competitor_profiles.values())[:5], indent=2)}
Movement summary: {json.dumps(movements_summary, indent=2)}
Include: landscape overview, each competitor summary, market positioning, strategic recommendations, top 3 threats, opportunities."""
        report = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        if not report or not report.strip():
            return self._llm_error("generate_competitive_report")

        result = {
            "competitors_analyzed": len(competitors),
            "competitor_names": competitors,
            "movement_summary": movements_summary,
            "full_report": report,
            "generated_at": self._now_iso(),
        }
        self._store_result("competitive_report_generated",
                           f"Generated competitive report: {len(competitors)} competitors",
                           ["startups", "report", "competitive"], result)
        return result

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        # 2026-07-28: run() never checked task["type"] at all — always
        # generated a report over whatever competitors happened to be
        # tracked so far (often none) — a total non-sequitur for a
        # free-text ask. Same bug class as design district's #33.
        query = p.get("query") or p.get("content") or task.get("query")
        if query:
            tracked = list(self.movement_history.keys())
            ctx = f"Currently tracking {len(tracked)} competitor(s): {', '.join(tracked) or 'none yet'}."
            return await self.answer_startup_task(query, ctx)
        result = self.generate_competitive_report()
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = CompetitorSpy()
    assert agent.district == "startups"
    p = agent.analyze_competitor("GitHub Copilot")
    assert "profile" in p and p["competitor_name"] == "GitHub Copilot"
    m = agent.track_movements("GitHub Copilot")
    assert "recent_moves" in m and "threat_level" in m
    r = agent.generate_competitive_report()
    assert "full_report" in r and r["competitors_analyzed"] >= 1
    print("OK competitor_spy.py")
