"""
Module: agents/districts/startups/competitor_spy.py
District: startups | Focus: Analyze competitors, track movements, generate reports
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime
from typing import Optional


class CompetitorSpy(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="CompetitorSpy",
            district="startups",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.competitor_profiles = {}
        self.movement_history = {}
        logger.info("[VECTOR][startups] CompetitorSpy ready")

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

    def analyze_competitor(self, name: str) -> dict:
        logger.info(f"[VECTOR][startups] Analyzing competitor: {name}")
        self.add_lesson({"action": "analyze_competitor", "competitor": name})

        prompt = f"""Perform a comprehensive competitive analysis of '{name}':
1. Business model and revenue streams
2. Target customers and market positioning
3. Key products/services and pricing
4. Strengths (what they do well)
5. Weaknesses (vulnerabilities)
6. Market share and growth trajectory
7. Technology stack and innovation
8. Team and leadership quality
9. Funding and financial health
10. Customer sentiment and reviews

Return JSON: {{name, business_model: string, target_market: string, products: string[], pricing: string, strengths: string[], weaknesses: string[], market_share: string, funding: string, overall_strength: strong/moderate/weak, key_insight: string}}"""
        analysis = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', analysis, re.DOTALL)
            if json_match:
                profile = json.loads(json_match.group(0))
            else:
                profile = {"name": name, "overall_strength": "moderate", "key_insight": analysis[:200]}
        except json.JSONDecodeError:
            profile = {"name": name, "overall_strength": "moderate", "key_insight": analysis[:200]}

        self.competitor_profiles[name] = profile

        result = {
            "competitor_name": name,
            "profile": profile,
            "analyzed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="competitor_analyzed",
            content=f"Analyzed competitor '{name}': {profile.get('overall_strength', 'unknown')} strength",
            tags=["startups", "competitor", name],
            context=result,
            source="CompetitorSpy"
        )

        return result

    def track_movements(self, competitor_name: str) -> dict:
        logger.info(f"[VECTOR][startups] Tracking movements for: {competitor_name}")
        self.add_lesson({"action": "track_movements", "competitor": competitor_name})

        profile = self.competitor_profiles.get(competitor_name, {})

        prompt = f"""Track recent strategic moves for '{competitor_name}':
Current profile: {json.dumps(profile)[:500]}
Look for: 1) Product launches and updates, 2) Marketing campaign changes, 3) Pricing adjustments, 4) Partnership announcements, 5) Hiring trends, 6) Funding rounds, 7) Expansion moves, 8) Customer feedback changes.
Return JSON: {{recent_moves: [{{date: string, move_type: string, description: string, impact: high/medium/low}}], strategic_direction: string, threat_level: high/medium/low, recommended_response: string}}"""
        movements = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', movements, re.DOTALL)
            if json_match:
                move_data = json.loads(json_match.group(0))
            else:
                move_data = {"recent_moves": [], "threat_level": "medium"}
        except json.JSONDecodeError:
            move_data = {"recent_moves": [], "threat_level": "medium"}

        if competitor_name not in self.movement_history:
            self.movement_history[competitor_name] = []

        for move in move_data.get("recent_moves", []):
            self.movement_history[competitor_name].append({
                "move": move,
                "tracked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

        result = {
            "competitor_name": competitor_name,
            "recent_moves": move_data.get("recent_moves", []),
            "strategic_direction": move_data.get("strategic_direction", ""),
            "threat_level": move_data.get("threat_level", "medium"),
            "total_moves_tracked": len(self.movement_history.get(competitor_name, [])),
            "tracked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="movements_tracked",
            content=f"Tracked {len(move_data.get('recent_moves', []))} moves for '{competitor_name}'",
            tags=["startups", "tracking", competitor_name],
            context=result,
            source="CompetitorSpy"
        )

        return result

    def generate_competitive_report(self) -> dict:
        logger.info("[VECTOR][startups] Generating competitive analysis report")
        self.add_lesson({"action": "generate_competitive_report"})

        competitors = list(self.competitor_profiles.keys())
        movements_summary = {}
        for name, history in self.movement_history.items():
            movements_summary[name] = {
                "total_moves": len(history),
                "latest_move": history[-1]["move"] if history else None,
                "threat_level": "high" if len(history) > 5 else "medium" if len(history) > 2 else "low",
            }

        prompt = f"""Generate a comprehensive competitive analysis report:
Competitors analyzed: {len(competitors)}
Competitor profiles: {json.dumps(list(self.competitor_profiles.values())[:5], indent=2)}
Movement history: {json.dumps(movements_summary, indent=2)}
Include: 1) Competitive landscape overview, 2) Each competitor summary with threat level, 3) Market positioning map, 4) Strategic recommendations, 5) Top 3 threats and how to address them, 6) Opportunities to exploit."""
        report = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        result = {
            "competitors_analyzed": len(competitors),
            "competitor_names": competitors,
            "movement_summary": movements_summary,
            "full_report": report,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="competitive_report_generated",
            content=f"Generated competitive report: {len(competitors)} competitors",
            tags=["startups", "report", "competitive"],
            context=result,
            source="CompetitorSpy"
        )

        return result


    async def run(self, task: dict) -> dict:
        result = self.generate_competitive_report()
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = CompetitorSpy()
    assert agent.district == "startups"

    profile = agent.analyze_competitor("GitHub Copilot")
    assert "profile" in profile
    assert profile["competitor_name"] == "GitHub Copilot"

    moves = agent.track_movements("GitHub Copilot")
    assert "recent_moves" in moves
    assert "threat_level" in moves

    report = agent.generate_competitive_report()
    assert "full_report" in report
    assert report["competitors_analyzed"] >= 1

    print("✅ competitor_spy.py OK")