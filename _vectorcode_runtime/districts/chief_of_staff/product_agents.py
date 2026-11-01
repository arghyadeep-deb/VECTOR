"""Source-grounded product agents owned by the chief-of-staff district."""
from __future__ import annotations

import asyncio
from collections import Counter
import math
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase
from core.config import CONFIG
from core.loop.context_engine import ContextEngine


class ProductAgentBase(AgentBase):
    """Shared citizen behaviour for bounded, evidence-led product analysis."""

    def __init__(self, agent_id: str, name: str, capabilities: list[str]) -> None:
        super().__init__(agent_id=agent_id, name=name, district="chief_of_staff")
        self.capabilities = capabilities
        self._context = ContextEngine()
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")

    @staticmethod
    def _params(task: dict[str, Any]) -> dict[str, Any]:
        params = task.get("params")
        return params if isinstance(params, dict) else task

    async def _grounded_narrative(self, instruction: str, evidence: str) -> str:
        """Summarise supplied evidence through routed inference, never as evidence itself."""
        if not evidence:
            return ""
        try:
            from core.inference.vectorcode_llm import chat

            hydration = self._context.session_hydration_prompt()
            messages = [
                {"role": "system", "content": hydration},
                {
                    "role": "user",
                    "content": (
                        f"{instruction}\n\nUse only the evidence between the delimiters. "
                        "Do not claim a fact without its source URL.\n"
                        f"--- EVIDENCE ---\n{evidence[:6000]}\n--- END EVIDENCE ---"
                    ),
                },
            ]
            result = await asyncio.to_thread(chat, model=self._model, messages=messages, timeout=20.0)
            return (result or "").strip()
        except Exception as exc:
            logger.warning("[VECTOR][chief_of_staff_product] {} synthesis unavailable: {}", self.name, exc)
            return ""

    @staticmethod
    def _rice(item: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("RICE candidate must be an object")

        def number(field: str, default: float) -> float:
            try:
                value = float(item.get(field, default))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} must be a finite number") from exc
            if not math.isfinite(value):
                raise ValueError(f"{field} must be a finite number")
            return value

        reach = max(0.0, number("reach", 0.0))
        impact = max(0.0, number("impact", 0.0))
        confidence = min(100.0, max(0.0, number("confidence", 0.0))) / 100.0
        effort = max(1.0, number("effort", 1.0))
        return {
            "name": str(item.get("name", "unnamed")),
            "rice_score": round(reach * impact * confidence / effort, 2),
            "reach": reach,
            "impact": impact,
            "confidence": round(confidence * 100, 1),
            "effort": effort,
        }


class ProductTrendResearcher(ProductAgentBase):
    """Collect source-backed trend evidence and hand a bounded brief to peers."""

    def __init__(self) -> None:
        super().__init__(
            "product_trend_researcher_001",
            "ProductTrendResearcher",
            ["product_trend_research"],
        )

    @staticmethod
    def _normalise_sources(raw_sources: Any) -> list[dict[str, str]]:
        if not isinstance(raw_sources, list):
            return []
        sources: list[dict[str, str]] = []
        for raw in raw_sources[:5]:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url", "")).strip()
            if not url.startswith(("https://", "http://")):
                continue
            title = str(raw.get("title", "Untitled source")).strip()[:200]
            excerpt = str(raw.get("snippet") or raw.get("content") or "").strip()[:700]
            if excerpt and ProductTrendResearcher._safe_excerpt(excerpt):
                sources.append({"title": title, "url": url, "excerpt": excerpt})
        return sources

    @staticmethod
    def _safe_excerpt(excerpt: str) -> bool:
        """Reject prompt-injection-shaped web content before a model sees it."""
        try:
            from core.security.prompt_injection import scan_text

            return not scan_text(excerpt, context="product_trend_research").has_high
        except Exception as exc:
            logger.warning("[VECTOR][chief_of_staff_product] source screening unavailable: {}", exc)
            return False

    async def _collect_sources(self, query: str, provided: Any) -> list[dict[str, str]]:
        sources = self._normalise_sources(provided)
        if sources or not query:
            return sources
        try:
            reply = await self.a2a_ask(
                "search_web", {"query": query}, to="WebScout", capability="search_web"
            )
            if reply.ok and isinstance(reply.result, dict):
                return self._normalise_sources(reply.result.get("results"))
        except Exception as exc:
            logger.warning("[VECTOR][chief_of_staff_product] trend collection failed: {}", exc)
        return []

    @staticmethod
    def _evidence_text(sources: list[dict[str, str]]) -> str:
        return "\n\n".join(
            f"Source: {source['title']}\nURL: {source['url']}\nExcerpt: {source['excerpt']}"
            for source in sources
        )

    @staticmethod
    def _fallback_summary(query: str, sources: list[dict[str, str]]) -> str:
        titles = "; ".join(source["title"] for source in sources)
        return f"Evidence collected for '{query}' from {len(sources)} sources: {titles}. Review the cited excerpts before committing work."

    async def _handoff(self, artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
        handoffs: dict[str, dict[str, Any]] = {}
        targets = {"coding": "CodingSwarm", "marketing": "GrowthHacker"}
        for district, target in targets.items():
            reply = await self.a2a_ask("research", artifact, to=target, capability="research")
            handoff = reply.to_dict()
            handoff["target"] = target
            handoffs[district] = handoff
        return handoffs

    async def run(self, task: dict) -> dict:
        params = self._params(task)
        query = str(params.get("query") or params.get("topic") or "").strip()
        if not query:
            return {"status": "error", "reason": "query is required", "agent": self.name}
        sources = await self._collect_sources(query, params.get("sources"))
        if not sources:
            return {
                "status": "no_evidence",
                "agent": self.name,
                "query": query,
                "reason": "No URL-bearing source evidence was available; no trend claim or handoff was produced.",
            }
        evidence = self._evidence_text(sources)
        narrative = ""
        if params.get("synthesize", True):
            narrative = await self._grounded_narrative(
                "Produce a concise product-trend brief with opportunity, risk, and one reversible next step.", evidence
            )
        artifact = {
            "artifact_type": "trend_research_handoff",
            "query": query,
            "sources": sources,
            "summary": narrative or self._fallback_summary(query, sources),
            "summary_provenance": "model_synthesis" if narrative else "deterministic_source_index",
            "constraints": [
                "Evidence is informational; validate before implementation or campaign publication.",
                "This handoff proposes no code edit, publication, or external action.",
            ],
        }
        handoffs = await self._handoff(artifact)
        self.know("latest_trend_research", artifact)
        delivered = [district for district, handoff in handoffs.items() if handoff.get("ok")]
        if len(delivered) == len(handoffs):
            self.award_points(20, "source_backed_trend_research_delivered")
            status = "ok"
        elif delivered:
            self.award_points(10, "source_backed_trend_research_partially_delivered")
            status = "partial"
        else:
            status = "error"
        return {
            "status": status,
            "agent": self.name,
            "artifact": artifact,
            "handoffs": handoffs,
            "delivered_handoffs": delivered,
        }


class ProductFeedbackSynthesizer(ProductAgentBase):
    """Turn supplied product feedback into traceable recurring themes."""

    def __init__(self) -> None:
        super().__init__("product_feedback_synthesizer_001", "ProductFeedbackSynthesizer", ["product_feedback_analysis"])

    async def run(self, task: dict) -> dict:
        params = self._params(task)
        raw_signals = params.get("signals", [])
        if not isinstance(raw_signals, list):
            return {"status": "error", "reason": "signals must be a list of strings", "agent": self.name}
        signals = [str(signal).strip() for signal in raw_signals if str(signal).strip()]
        if not signals:
            return {"status": "error", "reason": "signals are required", "agent": self.name}
        stopwords = frozenset({"this", "that", "with", "from", "have", "been", "were", "they", "them", "your", "about", "there", "would", "could", "should", "really", "very", "more"})
        terms = Counter(
            word.lower().strip(".,!?:;")
            for signal in signals
            for word in signal.split()
            if len(word) > 3 and word.lower().strip(".,!?:;") not in stopwords
        )
        result = {
            "status": "ok", "agent": self.name, "themes": [word for word, _ in terms.most_common(5)],
            "signal_count": len(signals),
        }
        if params.get("synthesize", True):
            result["summary"] = await self._grounded_narrative(
                "Summarise recurring feedback themes and uncertainties.", "\n".join(f"- {signal}" for signal in signals[:20])
            )
        self.know("latest_product_feedback", result)
        self.award_points(15, "product_feedback_synthesized")
        return result


class ProductManager(ProductAgentBase):
    """Create a bounded PRD or transparent RICE score from owner inputs."""

    def __init__(self) -> None:
        super().__init__("chief_product_manager_001", "ChiefOfStaffProductManager", ["product_requirements"])

    async def run(self, task: dict) -> dict:
        params = self._params(task)
        task_type = str(task.get("type") or params.get("type") or "prd")
        if task_type == "rice_score" or params.get("action") == "rice_score":
            try:
                result = self._rice(params)
            except ValueError as exc:
                return {"status": "error", "reason": str(exc), "agent": self.name}
            self.award_points(10, "product_rice_scored")
            return {"status": "ok", "agent": self.name, "rice": result}
        feature = str(params.get("feature") or params.get("feature_name") or "").strip()
        problem = str(params.get("problem") or "").strip()
        if not feature or not problem:
            return {"status": "error", "reason": "feature and problem are required for a PRD", "agent": self.name}
        prd = {
            "feature": feature, "problem": problem,
            "success_metrics": list(params.get("success_metrics") or []),
            "user_stories": list(params.get("user_stories") or []),
            "out_of_scope": list(params.get("out_of_scope") or []),
        }
        if params.get("synthesize", True):
            prd["summary"] = await self._grounded_narrative(
                "Write a concise product requirement summary without inventing requirements.",
                f"Feature: {feature}\nProblem: {problem}\nMetrics: {prd['success_metrics']}\nStories: {prd['user_stories']}",
            )
        self.know("latest_prd", prd)
        self.award_points(15, "product_prd_created")
        return {"status": "ok", "agent": self.name, "prd": prd}


class ProductSprintPrioritizer(ProductAgentBase):
    """Rank an explicit sprint candidate list with reproducible RICE arithmetic."""

    def __init__(self) -> None:
        super().__init__("product_sprint_prioritizer_001", "ProductSprintPrioritizer", ["product_sprint_ranking"])

    async def run(self, task: dict) -> dict:
        params = self._params(task)
        candidates = params.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return {"status": "error", "reason": "non-empty candidates are required", "agent": self.name}
        try:
            ranked = sorted(
                (self._rice(candidate) for candidate in candidates if isinstance(candidate, dict)),
                key=lambda item: item["rice_score"], reverse=True,
            )
        except ValueError as exc:
            return {"status": "error", "reason": str(exc), "agent": self.name}
        if not ranked:
            return {"status": "error", "reason": "candidates must be objects", "agent": self.name}
        result = {"status": "ok", "agent": self.name, "priorities": ranked}
        skipped = sum(1 for candidate in candidates if not isinstance(candidate, dict))
        if skipped:
            # Non-object candidates are not ranked; say so instead of silently dropping them.
            result["skipped_candidates"] = skipped
        if params.get("synthesize", True):
            result["summary"] = await self._grounded_narrative(
                "Explain the RICE ranking and uncertainty without changing any scores.", str(ranked)
            )
        self.know("latest_sprint_priorities", result)
        self.award_points(15, "sprint_priorities_ranked")
        return result


class ProductBehavioralNudgeEngine(ProductAgentBase):
    """Recommend a product-work nudge; delivery remains the caller's choice."""

    def __init__(self) -> None:
        super().__init__("product_behavioral_nudge_001", "ProductBehavioralNudgeEngine", ["product_work_nudge"])

    async def run(self, task: dict) -> dict:
        params = self._params(task)
        blocker = str(params.get("blocker") or "").strip()
        next_step = str(params.get("next_step") or "").strip()
        if not blocker or not next_step:
            return {"status": "error", "reason": "blocker and next_step are required", "agent": self.name}
        result = {
            "status": "ok", "agent": self.name,
            "nudge": f"Product work is blocked by: {blocker}. Take this reversible next step now: {next_step}.",
            "delivery": "recommended_not_sent",
        }
        if params.get("synthesize", True):
            drafted = await self._grounded_narrative(
                "Draft one concise, non-manipulative product-work nudge. Do not imply it was sent.",
                f"Blocker: {blocker}\nReversible next step: {next_step}",
            )
            if drafted:
                result["nudge"] = drafted
        self.know("latest_product_nudge", result)
        self.award_points(5, "product_nudge_recommended")
        return result


if __name__ == "__main__":
    async def _smoke() -> None:
        sprint = ProductSprintPrioritizer()
        result = await sprint.run({"type": "prioritize_gaps", "candidates": [{"name": "evidence", "reach": 10, "impact": 3, "confidence": 80, "effort": 2}]})
        assert result["status"] == "ok" and result["priorities"][0]["name"] == "evidence"
        logger.info("[VECTOR][chief_of_staff_product] smoke test passed")

    asyncio.run(_smoke())
