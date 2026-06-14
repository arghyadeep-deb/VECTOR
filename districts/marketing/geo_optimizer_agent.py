"""
GEO Optimizer — measures AI search engine citation score (0-100).
Tracks how often your brand/content is cited by ChatGPT, Claude, Perplexity, Gemini, AI Overviews.
"""

import asyncio

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG

class GEOOptimizerAgent(AgentBase):
    """GEO score agent — AI search citation auditor (0-100)."""

    ENGINES = ["perplexity", "chatgpt", "claude", "gemini", "google_ai_overview"]

    def __init__(self):
        super().__init__(agent_id="geo_optimizer_001", name="GEOOptimizerAgent", district="marketing")

    async def check_citation(self, brand: str, query: str, engine: str = "perplexity") -> dict:
        """Check if brand is cited in an AI engine's response to a query."""
        try:
            from core.inference.provider_client import get_client
            client = get_client()

            prompt = f"Answer this question: {query}\n\nProvide a comprehensive answer."

            # Use appropriate model per engine
            model_map = {
                "perplexity": "perplexity/llama-3.1-sonar-large-128k-online",
                "chatgpt": "gpt-4o",
                "claude": "claude-sonnet-4-6",
                "gemini": "gemini-2.5-pro",
            }
            model = model_map.get(engine, CONFIG.get("models", {}).get("focus", "vector-focus"))

            response = await client.complete(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )

            content = (response.content or "").lower()
            cited = brand.lower() in content

            return {
                "engine": engine,
                "query": query,
                "brand": brand,
                "cited": cited,
                "score": 100 if cited else 0,
                "excerpt": content[:200] if cited else "",
            }
        except Exception as e:
            logger.warning("[VECTOR][geo] {} check failed: {}", engine, e)
            return {"engine": engine, "query": query, "brand": brand, "cited": False, "score": 0, "error": str(e)}

    async def geo_score(self, brand: str, queries: list[str]) -> dict:
        """
        Compute GEO score 0-100 across multiple queries and engines.
        Higher score = more AI citations.
        """
        tasks = []
        for query in queries:
            for engine in ["perplexity", "chatgpt", "claude", "gemini"]:
                tasks.append(self.check_citation(brand, query, engine))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if isinstance(r, dict)]
        cited = [r for r in valid if r.get("cited")]

        score = (len(cited) / len(valid) * 100) if valid else 0

        self.award_points(10, "geo_score_computed")
        return {
            "brand": brand,
            "geo_score": round(score, 1),
            "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D",
            "citations": len(cited),
            "total_checks": len(valid),
            "by_engine": {e: sum(1 for r in cited if r["engine"] == e) for e in self.ENGINES},
            "top_queries": [r["query"] for r in cited[:3]],
        }

    async def run(self, params: dict = None) -> dict:
        p = params or {}
        brand = p.get("brand", CONFIG.get("owner_name", "VECTOR"))
        queries = p.get("queries", ["best AI assistant", "top AI tools 2026"])
        return await self.geo_score(brand, queries)

if __name__ == "__main__":
    a = GEOOptimizerAgent()
    print("✅ geo_optimizer_agent OK:", type(a))
