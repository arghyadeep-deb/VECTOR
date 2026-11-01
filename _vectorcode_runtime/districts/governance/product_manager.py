"""
Product Manager — PRD creation, roadmap ownership, feature prioritization.

Manages VECTOR's own product development process and any client products
built via the agency district. PRDs, stakeholder alignment, outcome tracking.
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

_RICE_FIELDS = ["reach", "impact", "confidence", "effort"]

class ProductManager(AgentBase):
    """
    Product lifecycle management: PRDs, RICE scoring, roadmaps, outcome tracking.
    Bridges user needs, business goals, and technical reality for VECTOR itself
    and any products in the agency district.
    """

    def __init__(self):
        super().__init__(agent_id="product_manager_001", name="ProductManager", district="governance")
        self.capabilities = ["brief", "council", "decision", "product", "rice", "roadmap"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info("[VECTOR][pm] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def rice_score(self, feature: str, reach: int, impact: int,
                   confidence: int, effort: int) -> dict:
        """RICE prioritization: (Reach × Impact × Confidence%) / Effort."""
        conf_pct = max(0, min(100, confidence)) / 100.0
        score = round((reach * impact * conf_pct) / max(effort, 1), 1)
        return {
            "feature": feature,
            "reach": reach,
            "impact": impact,
            "confidence_pct": confidence,
            "effort": effort,
            "rice_score": score,
            "priority": "P0" if score > 100 else "P1" if score > 50 else "P2" if score > 20 else "P3",
        }

    def build_prd(self, feature_name: str, problem: str, success_metrics: list[str],
                   user_stories: list[str], constraints: list[str] = None) -> dict:
        """Generate a structured PRD (Product Requirements Document)."""
        ts = datetime.datetime.now().strftime("%Y-%m-%d")
        return {
            "metadata": {
                "feature": feature_name,
                "created": ts,
                "status": "draft",
                "owner": "Arghyadeep Deb",
            },
            "problem_statement": problem,
            "goals": [
                f"Solve: {problem[:60]}",
                "Measurable improvement in user experience",
                "Ship within agreed timeline without scope creep",
            ],
            "success_metrics": success_metrics,
            "user_stories": [
                {"story": story, "acceptance_criteria": f"Given {story.split('want')[0].strip().replace('As a','').strip()}, "
                                                         f"when the feature is used, then the user achieves the stated goal."}
                for story in user_stories
            ],
            "out_of_scope": constraints or ["Existing features remain unchanged", "No new infrastructure required"],
            "technical_notes": "Implementation details TBD with engineering team",
            "open_questions": ["Who is the primary user persona?", "What's the fallback if primary approach fails?"],
        }

    def build_roadmap(self, features: list[dict], quarters: int = 4) -> dict:
        """Assign features to quarters based on RICE score and dependencies."""
        scored = []
        for f in features:
            score = self.rice_score(
                f.get("name", ""), f.get("reach", 10), f.get("impact", 3),
                f.get("confidence", 70), f.get("effort", 5),
            )
            scored.append({**f, **score})

        sorted_features = sorted(scored, key=lambda x: -x["rice_score"])
        per_quarter = max(1, len(sorted_features) // quarters)
        roadmap = {}
        quarter_names = [f"Q{i+1}" for i in range(quarters)]
        for i, q in enumerate(quarter_names):
            start = i * per_quarter
            end = start + per_quarter if i < quarters - 1 else len(sorted_features)
            roadmap[q] = [
                {"feature": f["name"], "rice_score": f["rice_score"], "priority": f["priority"]}
                for f in sorted_features[start:end]
            ]
        return {
            "roadmap": roadmap,
            "total_features": len(features),
            "quarters_planned": quarters,
            "top_priority": sorted_features[0]["name"] if sorted_features else "N/A",
        }

    async def write_feature_brief(self, feature_name: str, context: str) -> str:
        """LLM generates a 1-page feature brief for stakeholder alignment."""
        prompt = (
            f"Write a 200-word product feature brief for '{feature_name}'.\n"
            f"Context: {context}\n\n"
            f"Structure:\n"
            f"**Why we're building this:** [problem and user pain]\n"
            f"**What we're building:** [specific feature description]\n"
            f"**How we'll measure success:** [2-3 metrics]\n"
            f"**What we're NOT building:** [explicit scope exclusions]\n"
            f"**Launch criteria:** [definition of done]\n\n"
            f"Be specific, avoid vague statements, keep it under 200 words."
        )
        try:
            from core.prompt_library import get_library as _gl
            _sys = _gl().get_for_agent("product_manager") or ""
            _msgs = ([{"role": "system", "content": _sys}] if _sys else []) + [{"role": "user", "content": prompt}]
            return chat(model=self._model, messages=_msgs, timeout=20.0)
        except Exception as e:
            logger.warning("[VECTOR][pm] brief LLM failed: {}", e)
            return (
                f"**Why we're building {feature_name}:** {context[:100]}.\n\n"
                f"**What we're building:** A focused implementation of {feature_name} "
                f"that directly addresses the stated problem.\n\n"
                f"**Success metrics:** User task completion rate, time-to-value, satisfaction score.\n\n"
                f"**Not building:** Anything outside the core use case. Scope additions require new PRD.\n\n"
                f"**Launch criteria:** All acceptance criteria pass, documentation complete, demo recorded."
            )

    async def answer_product_question(self, query: str) -> str:
        """Answer a free-text/unmatched-task_type question about VECTOR's
        product/roadmap process, instead of always generating a fully
        hardcoded fake PRD ('Users can't accomplish their goal efficiently',
        etc.) regardless of what was actually asked — the exact
        KNOWN_ISSUES bug pattern found here: any conversational question
        routed to ProductManager used to get a fabricated PRD for a
        nonexistent 'New Feature' back instead of an answer."""
        prompt = (
            "You are VECTOR's ProductManager in the governance district — "
            "you own PRDs, roadmap prioritization (RICE scoring), and "
            "feature briefs for VECTOR itself. Answer the owner's question "
            "directly and concretely. Do not invent a fake feature, PRD, "
            f"or roadmap unless the question actually asks for one.\n\n"
            f"Question: {query}"
        )
        try:
            from core.prompt_library import get_library as _gl
            _sys = _gl().get_for_agent("product_manager") or ""
            _msgs = ([{"role": "system", "content": _sys}] if _sys else []) + [{"role": "user", "content": prompt}]
            result = chat(model=self._model, messages=_msgs, timeout=20.0)
            return (result or "").strip()
        except Exception as e:
            logger.warning("[VECTOR][pm] answer_product_question failed: {}", e)
            return ""

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "prd")
        try:
            if task_type == "rice":
                result = self.rice_score(
                    task.get("feature", ""), task.get("reach", 100),
                    task.get("impact", 3), task.get("confidence", 70),
                    task.get("effort", 5),
                )
                self.award_points(10, "feature_scored")
                return {"status": "ok", "rice": result}

            elif task_type == "roadmap":
                result = self.build_roadmap(
                    task.get("features", []), task.get("quarters", 4)
                )
                self._get_memory().store(
                    event_type="roadmap_built",
                    content=f"Roadmap: {result['total_features']} features across {result['quarters_planned']} quarters",
                    tags=["governance", "product", "roadmap"],
                    source="product_manager",
                )
                self.award_points(30, "roadmap_built")
                return {"status": "ok", "roadmap": result}

            elif task_type == "brief":
                brief = await self.write_feature_brief(
                    task.get("feature_name", "Feature"), task.get("context", "")
                )
                self.award_points(20, "feature_brief_written")
                return {"status": "ok", "brief": brief}

            else:  # prd, or an unmatched task_type carrying a free-text question
                # Only treat this as a real PRD request when a real feature_name
                # was actually supplied — a bare conversational message has no
                # "feature_name" and used to still get a fabricated PRD for a
                # made-up "New Feature". Real free text gets answered instead.
                query = (
                    (task.get("params") or {}).get("query")
                    or task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query and not task.get("feature_name"):
                    answer = await self.answer_product_question(query)
                    if answer:
                        self._get_memory().store(
                            event_type="product_question_answered",
                            content=f"ProductManager answered: {query[:80]}",
                            tags=["governance", "product"],
                            source="product_manager",
                        )
                        self.award_points(15, "product_question_answered")
                        return {"status": "ok", "response": answer}

                prd = self.build_prd(
                    task.get("feature_name", "New Feature"),
                    task.get("problem", "Users can't accomplish their goal efficiently"),
                    task.get("success_metrics", ["Task completion rate > 85%", "Time-on-task reduced by 30%"]),
                    task.get("user_stories", ["As a user, I want to complete my task faster"]),
                    task.get("constraints", None),
                )
                self._get_memory().store(
                    event_type="prd_created",
                    content=f"PRD: {prd['metadata']['feature']}",
                    tags=["governance", "product", "prd"],
                    source="product_manager",
                )
                self.award_points(35, "prd_created")
                return {"status": "ok", "prd": prd}

        except Exception as e:
            logger.error("[VECTOR][pm] {}", e)
            self.deduct_points(30, "pm_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ProductManager()
        rice = agent.rice_score("VECTOR Dashboard", reach=500, impact=4, confidence=80, effort=8)
        print(f"[OK] rice: score={rice['rice_score']} priority={rice['priority']}")
        prd = agent.build_prd("VECTOR Web Dashboard",
                               "Users can't monitor VECTOR without running CLI commands",
                               ["Dashboard load time < 2s", "All district status visible at a glance"],
                               ["As an owner, I want to see all district health at a glance"])
        print(f"[OK] prd: feature={prd['metadata']['feature']} metrics={len(prd['success_metrics'])}")
        roadmap = agent.build_roadmap([
            {"name": "Dashboard", "reach": 100, "impact": 5, "confidence": 80, "effort": 8},
            {"name": "Voice pipeline", "reach": 50, "impact": 4, "confidence": 60, "effort": 6},
            {"name": "Mobile app", "reach": 30, "impact": 3, "confidence": 40, "effort": 10},
        ], quarters=2)
        print(f"[OK] roadmap: top={roadmap['top_priority']} features={roadmap['total_features']}")
        result = await agent.run({"type": "rice", "feature": "API rate limiting", "reach": 1000})
        print(f"[OK] run: status={result['status']}")
        print("product_manager.py OK")

    asyncio.run(_smoke())
