"""
Deep Researcher — VECTOR's primary research agent.

Uses VECTOR Research Engine (core/research_engine/) for multi-source,
iterative research. Replaces the basic web_scout for complex queries.

Model routing (all local Ollama — VECTOR Rule 11):
    quick     → vector-focus   (~1-3 min, real-time)
    report    → vector-reasoning    (~10-30 min, overnight tasks)
    papers    → vector-reasoning (academic, structured)
    news      → vector-focus   (fast, current events)

HP awards:
    quick_research:   +15 HP on success, -10 HP on failure
    generate_report:  +40 HP on success, -20 HP on failure
    research_papers:  +20 HP on success, -10 HP on failure
"""
import asyncio


from loguru import logger
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from districts.research.research_api import (
    quick_research,
    generate_report,
    research_papers,
    research_news,
    analyze_documents,
)


class DeepResearcher(AgentBase):
    """
    VECTOR's deep research agent. Performs iterative multi-source research
    using local Ollama models via VECTOR Research Engine.

    Capable of:
    - Quick summaries (1-3 min, DuckDuckGo + Wikipedia + ArXiv)
    - Full structured reports (10-30 min, multi-section with citations)
    - Academic paper research (ArXiv + PubMed + Semantic Scholar)
    - News research (DuckDuckGo + Wikinews)
    - Local document collection search
    """

    def __init__(self):
        super().__init__(
            agent_id="deep_researcher_001",
            name="DeepResearcher",
            district="research",
        )
        self.capabilities = ["deep_research", "documents", "news", "papers", "quick", "report", "research", "search"]
        self._memory: EpisodicMemory | None = None
        logger.info("[VECTOR][deep_researcher] initialized")

    # capability names advertised by this agent that are not themselves a research mode
    _TASK_ALIASES = {"deep_research": "quick", "research": "quick", "search": "quick"}

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    # ── Research methods ──────────────────────────────────────────────────────

    async def quick(self, query: str, save_to_brain: bool = True) -> dict:
        """Fast research summary (1-3 min). Best for quick lookups."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: quick_research(query, save_to_brain=save_to_brain)
            )
            if result.get("summary") and not result.get("error") and "failed" not in result["summary"]:
                # An answer with no sources is a claim nobody can check: full reward only when sources came back.
                self.award_points(15 if result.get("sources") else 4, "quick_research_success" if result.get("sources") else "quick_research_unsourced")
                self._get_memory().store(
                    event_type="research_quick",
                    content=f"Quick research: {query[:100]}",
                    tags=["research", "quick"],
                    source="deep_researcher",
                )
            else:
                self.deduct_points(10, "quick_research_failed")
            return result
        except Exception as e:
            logger.error("[VECTOR][deep_researcher] quick() failed: {}", e)
            self.deduct_points(10, "quick_research_error")
            return {"summary": str(e), "findings": [], "sources": [], "error": str(e)}

    async def report(self, query: str, searches_per_section: int = 2,
                     save_to_brain: bool = True) -> dict:
        """Full structured report (10-30 min). Use for interview prep, market research."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: generate_report(
                    query,
                    searches_per_section=searches_per_section,
                    save_to_brain=save_to_brain,
                )
            )
            if result.get("content") and not result.get("error") and "failed" not in result.get("content", ""):
                self.award_points(40, "report_generation_success")
                self._get_memory().store(
                    event_type="research_report",
                    content=f"Report generated: {query[:100]}",
                    tags=["research", "report", "deep"],
                    source="deep_researcher",
                )
            else:
                self.deduct_points(20, "report_generation_failed")
            return result
        except Exception as e:
            logger.error("[VECTOR][deep_researcher] report() failed: {}", e)
            self.deduct_points(20, "report_generation_error")
            return {"content": str(e), "metadata": {}, "error": str(e)}

    async def papers(self, query: str, max_results: int = 10) -> dict:
        """Academic paper research via ArXiv + PubMed + Semantic Scholar."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: research_papers(query, max_results=max_results)
            )
            if result.get("summary") and not result.get("error") and "failed" not in result["summary"]:
                self.award_points(20, "paper_research_success")
            else:
                self.deduct_points(10, "paper_research_failed")
            return result
        except Exception as e:
            logger.error("[VECTOR][deep_researcher] papers() failed: {}", e)
            self.deduct_points(10, "paper_research_error")
            return {"summary": str(e), "findings": [], "sources": [], "error": str(e)}

    async def news(self, query: str, max_results: int = 10) -> dict:
        """News research — fast, current events."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: research_news(query, max_results=max_results)
            )
            if result.get("error"):
                self.deduct_points(10, "news_research_failed")
            else:
                self.award_points(10, "news_research_success")
            return result
        except Exception as e:
            logger.error("[VECTOR][deep_researcher] news() failed: {}", e)
            return {"summary": str(e), "findings": [], "sources": [], "error": str(e)}

    async def documents(self, query: str, collection_name: str,
                        max_results: int = 10) -> dict:
        """Search a local document collection."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: analyze_documents(query, collection_name, max_results)
            )
            if result.get("error"):
                self.deduct_points(10, "document_search_failed")
            else:
                self.award_points(10, "document_search_success")
            return result
        except Exception as e:
            logger.error("[VECTOR][deep_researcher] documents() failed: {}", e)
            return {"summary": str(e), "documents": [], "error": str(e)}

    # ── Task dispatcher ───────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "quick")
        # 2026-07-28: real chat dispatch puts the user's text at
        # task["params"]["query"], not top-level task["query"] — this was
        # returning a clean "No query provided" error for every real
        # conversational research question (see core/city/prompt_agent.py's
        # matching fix for the full explanation).
        query = (task.get("params") or {}).get("query") or task.get("query", "")

        if not query:
            return {"status": "error", "error": "No query provided"}

        # The advertised capability names route here unchanged (ResearchSwarm forwards the task type as-is), so they
        # must be accepted: "deep_research"/"research"/"search" used to fall through to "Unknown task type".
        task_type = self._TASK_ALIASES.get(task_type, task_type)

        try:
            if task_type == "quick":
                result = await self.quick(query, task.get("save_to_brain", True))
            elif task_type == "report":
                result = await self.report(
                    query,
                    searches_per_section=task.get("searches_per_section", 2),
                    save_to_brain=task.get("save_to_brain", True),
                )
            elif task_type == "papers":
                result = await self.papers(query, task.get("max_results", 10))
            elif task_type == "news":
                result = await self.news(query, task.get("max_results", 10))
            elif task_type == "documents":
                result = await self.documents(
                    query,
                    task.get("collection", "default"),
                    task.get("max_results", 10),
                )
            else:
                return {"status": "error", "error": f"Unknown task type: {task_type}"}

            # A failed or empty research call is not "ok": the inner methods swallow their exceptions into summary
            # text (and dock HP), so without this check the caller, the executor and the learning loop all saw success.
            if result.get("error"):
                return {"status": "error", "type": task_type, **result}
            if not (result.get("summary") or result.get("content") or result.get("findings") or result.get("documents")):
                return {"status": "error", "type": task_type, "error": "research returned no content", **result}
            # Evidence level, so plans/learning can tell a sourced answer from a bare one (a plan can require
            # result_field "sources" min_items 1). Status stays "ok": the research ran; whether it is *verified* is a
            # separate, checkable fact.
            n_sources = len(result.get("sources") or []) + len(result.get("documents") or [])
            return {"status": "ok", "type": task_type, "evidence": {"sources": n_sources, "sourced": n_sources > 0}, **result}

        except Exception as e:
            logger.error("[VECTOR][deep_researcher] run() failed: {}", e)
            self.deduct_points(15, "research_task_error")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    async def _smoke():
        agent = DeepResearcher()
        # Lightweight test — just checks imports and init work
        print(f"[OK] DeepResearcher initialized | HP={agent.health_points}")
        print("deep_researcher.py OK")
    asyncio.run(_smoke())
