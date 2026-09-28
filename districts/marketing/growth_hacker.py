"""
Growth Hacker — viral loops, North Star metric, funnel analysis, growth experiments.

Helps Arghyadeep grow VECTOR's presence, personal brand, and any startup/agency
projects using AARRR/ICE/North Star frameworks.
"""

import asyncio
import datetime
import json
import re

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat
from districts.marketing._skill_loader import load_skill, SkillMixin

_GROWTH_FRAMEWORKS = ["AARRR", "ICE_SCORING", "NORTH_STAR", "PIRATE_METRICS", "VIRAL_LOOPS"]

class GrowthHacker(AgentBase, SkillMixin):
    """
    Data-driven growth specialist. Viral loops, North Star metric, funnel optimization,
    ICE scoring for growth ideas, 30/60/90-day growth plans.
    Augmented with: marketing-ideas, analytics, cro skill prompts.
    """

    def __init__(self):
        super().__init__(agent_id="growth_hacker_001", name="GrowthHacker", district="marketing")
        self.capabilities = ["funnel_analysis", "growth", "marketing", "north_star", "plan", "score_idea", "viral_loop", "research"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        self._skill_prompt = load_skill("marketing-ideas", "analytics", "cro")
        logger.info("[VECTOR][growth] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def score_growth_idea(self, idea: str, impact: int, confidence: int, effort: int) -> dict:
        """ICE scoring: Impact × Confidence / Effort. Each 1-10."""
        impact = max(1, min(10, impact))
        confidence = max(1, min(10, confidence))
        effort = max(1, min(10, effort))
        ice_score = round((impact * confidence) / effort, 2)
        if ice_score >= 8:
            priority = "P0 — ship this week"
        elif ice_score >= 5:
            priority = "P1 — next sprint"
        elif ice_score >= 3:
            priority = "P2 — backlog"
        else:
            priority = "P3 — deprioritize"
        return {
            "idea": idea,
            "impact": impact,
            "confidence": confidence,
            "effort": effort,
            "ice_score": ice_score,
            "priority": priority,
        }

    def analyze_funnel(self, stages: list[dict]) -> dict:
        """Given [{stage, users}], find conversion rates and biggest drop-off."""
        if len(stages) < 2:
            return {"error": "Need at least 2 funnel stages"}
        results = []
        biggest_drop = {"stage": "", "drop_pct": 0.0}
        for i in range(len(stages) - 1):
            top = stages[i]["users"]
            bottom = stages[i + 1]["users"]
            conv = round(bottom / max(top, 1) * 100, 1)
            drop = round(100 - conv, 1)
            results.append({
                "from": stages[i]["stage"],
                "to": stages[i + 1]["stage"],
                "conversion_pct": conv,
                "drop_pct": drop,
                "lost_users": top - bottom,
            })
            if drop > biggest_drop["drop_pct"]:
                biggest_drop = {"stage": f"{stages[i]['stage']} → {stages[i+1]['stage']}", "drop_pct": drop}

        overall_conv = round(stages[-1]["users"] / max(stages[0]["users"], 1) * 100, 1)
        return {
            "stages": results,
            "overall_conversion_pct": overall_conv,
            "biggest_drop": biggest_drop,
            "suggestion": f"Focus on '{biggest_drop['stage']}' — {biggest_drop['drop_pct']}% of users drop here",
        }

    def design_viral_loop(self, product: str, user_action: str) -> dict:
        """Map trigger→action→reward→referral mechanism, estimate K-factor potential."""
        return {
            "product": product,
            "trigger": f"User achieves value from {user_action}",
            "action": "User shares result or invites a friend",
            "reward": "Both users get enhanced feature access",
            "referral": "New user joins with friend's referral context",
            "k_factor_estimate": "0.3-0.8 (typical for dev tools; >1.0 = exponential growth)",
            "loop_type": "product-led",
            "channels": ["word-of-mouth", "social share", "in-product invite", "GitHub stars"],
            "quick_wins": [
                f"Add 'Built with {product}' badge that links back",
                "One-click share of achievements/outputs",
                "Public showcase page for top users",
            ],
        }

    async def define_north_star_metric(self, product_description: str) -> dict:
        """LLM identifies the one metric that captures core value delivery."""
        prompt = (
            f"Define the North Star Metric for this product:\n{product_description}\n\n"
            f"Return JSON:\n"
            f'{{"north_star_metric": "name", "definition": "how to measure it", '
            f'"why": "why this captures real value", '
            f'"leading_indicators": ["3 metrics that predict the NSM"], '
            f'"lagging_indicators": ["2 metrics that confirm NSM health"], '
            f'"target_30d": "realistic 30-day target"}} '
        )
        try:
            response = self._chat(prompt, timeout=20.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][growth] NSM LLM failed: {}", e)

        return {
            "north_star_metric": "Weekly Active Users who complete core action",
            "definition": "Users who trigger the primary value action at least once per week",
            "why": "Captures both acquisition and activation/retention simultaneously",
            "leading_indicators": ["New signups", "Onboarding completion rate", "Day-1 retention"],
            "lagging_indicators": ["Monthly revenue", "Net Promoter Score"],
            "target_30d": "Define baseline first, then target 20% improvement",
        }

    async def generate_growth_plan(self, product: str, current_users: int,
                                   target_users: int, timeline_days: int) -> dict:
        """30/60/90-day structured growth plan."""
        growth_needed = target_users - current_users
        prompt = (
            f"Create a {timeline_days}-day growth plan for '{product}'.\n"
            f"Current users: {current_users} → Target: {target_users} (+{growth_needed})\n\n"
            f"Return JSON:\n"
            f'{{"channels": [{{"name": "channel", "effort": "low/medium/high", '
            f'"expected_users": 0, "actions": ["specific steps"]}}], '
            f'"week_1_sprint": ["3 immediate actions"], '
            f'"month_1_goal": "specific milestone", '
            f'"month_2_goal": "specific milestone", '
            f'"key_metric": "what to track daily", '
            f'"risks": ["top 2 risks"]}}'
        )
        try:
            response = self._chat(prompt, timeout=25.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                result = json.loads(match.group())
                result["product"] = product
                result["growth_target"] = growth_needed
                return result
        except Exception as e:
            logger.warning("[VECTOR][growth] plan LLM failed: {}", e)

        return {
            "product": product,
            "growth_target": growth_needed,
            "channels": [
                {"name": "organic-content", "effort": "medium", "expected_users": growth_needed // 3,
                 "actions": ["Publish weekly technical blog", "Share on LinkedIn/Twitter", "Answer relevant questions"]},
                {"name": "community", "effort": "medium", "expected_users": growth_needed // 3,
                 "actions": ["Post in relevant subreddits", "Engage in Discord servers", "GitHub trending"]},
                {"name": "referral", "effort": "low", "expected_users": growth_needed // 3,
                 "actions": ["Implement 'Built with' badge", "Launch referral program", "Share user success stories"]},
            ],
            "week_1_sprint": ["Set up analytics", "Define ICP clearly", "Ship shareable output feature"],
            "month_1_goal": f"Reach {current_users + growth_needed // 3} users",
            "month_2_goal": f"Reach {current_users + (growth_needed * 2) // 3} users",
            "key_metric": "Daily active users + weekly signups",
            "risks": ["Content-market fit mismatch", "Insufficient retention before scaling"],
        }

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "plan")
        try:
            if task_type == "research":
                artifact = task.get("params") if isinstance(task.get("params"), dict) else {}
                sources = artifact.get("sources") if isinstance(artifact, dict) else None
                if artifact.get("artifact_type") != "trend_research_handoff" or not isinstance(sources, list):
                    return {"status": "error", "agent": self.name, "reason": "valid trend research artifact is required"}
                self.know("latest_trend_research_handoff", artifact)
                return {
                    "status": "ok", "agent": self.name, "accepted": True,
                    "source_count": len(sources),
                    "next_step": "turn the cited audience signal into a reviewable campaign hypothesis before publication",
                }
            if task_type == "north_star":
                result = await self.define_north_star_metric(task.get("product_description", ""))
                self.award_points(25, "north_star_defined")
                return {"status": "ok", "north_star": result}

            elif task_type == "score_idea":
                result = self.score_growth_idea(
                    task.get("idea", ""), task.get("impact", 5),
                    task.get("confidence", 5), task.get("effort", 5),
                )
                self.award_points(10, "idea_scored")
                return {"status": "ok", "score": result}

            elif task_type == "viral_loop":
                result = self.design_viral_loop(
                    task.get("product", "VECTOR"), task.get("user_action", "generates an AI output")
                )
                self.award_points(20, "viral_loop_designed")
                return {"status": "ok", "viral_loop": result}

            elif task_type == "funnel_analysis":
                result = self.analyze_funnel(task.get("stages", []))
                self.award_points(20, "funnel_analyzed")
                return {"status": "ok", "funnel": result}

            elif task_type not in ("plan",) and (task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")):
                # 2026-07-28: unmatched/free-text task_type always fell
                # through to "plan" with hardcoded defaults (VECTOR AI /
                # 0 users / 1000 target), ignoring what was actually asked
                # — same bug class as design district's #33. Only routes
                # here when there's a real query and the type isn't
                # already the legitimate "plan" default.
                query = task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")
                return {"status": "ok", "response": await self.answer_marketing_question(query)}

            else:  # plan
                result = await self.generate_growth_plan(
                    task.get("product", "VECTOR AI"),
                    task.get("current_users", 0),
                    task.get("target_users", 1000),
                    task.get("timeline_days", 90),
                )
                self._get_memory().store(
                    event_type="growth_plan",
                    content=f"Growth plan for {result['product']}: +{result['growth_target']} users",
                    tags=["marketing", "growth"],
                    source="growth_hacker",
                )
                self.award_points(35, "growth_plan_generated")
                return {"status": "ok", "plan": result}

        except Exception as e:
            logger.error("[VECTOR][growth] {}", e)
            self.deduct_points(30, "growth_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = GrowthHacker()
        score = agent.score_growth_idea("Add GitHub badge", impact=7, confidence=8, effort=2)
        print(f"[OK] score_idea: ice={score['ice_score']} priority={score['priority']}")
        funnel = agent.analyze_funnel([
            {"stage": "Visit", "users": 1000}, {"stage": "Signup", "users": 120},
            {"stage": "Activate", "users": 45}, {"stage": "Retain", "users": 20},
        ])
        print(f"[OK] funnel: overall={funnel['overall_conversion_pct']}% drop={funnel['biggest_drop']['stage']}")
        loop = agent.design_viral_loop("VECTOR AI", "generates an insight")
        print(f"[OK] viral_loop: type={loop['loop_type']} channels={len(loop['channels'])}")
        result = await agent.run({"type": "plan", "product": "VECTOR", "current_users": 0, "target_users": 500})
        print(f"[OK] run: status={result['status']}")
        print("growth_hacker.py OK")

    asyncio.run(_smoke())
