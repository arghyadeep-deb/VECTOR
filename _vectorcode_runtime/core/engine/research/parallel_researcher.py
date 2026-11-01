"""
VECTOR Parallel Researcher — concurrent multi-source research.

Runs multiple search queries simultaneously and merges results.
Ported from vector's integrations/parallel.rs ParallelSearchTool.

Modes:
  fast      : DuckDuckGo + Wikipedia, no API keys needed
  deep      : DuckDuckGo + ArXiv + Wikipedia concurrently
  agentic   : full pipeline with LLM synthesis (requires Ollama)
"""
from __future__ import annotations

__all__ = [
    "parallel_extract",
    "parallel_search",
    "ParallelResearcher",
    "ParallelSearchResult",
    "ResearchReport",
]


import asyncio
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class ParallelSearchResult:
    query: str
    source: str
    title: str
    snippet: str
    url: str = ""
    score: float = 1.0


@dataclass
class ResearchReport:
    objective: str
    queries: list[str]
    results: list[ParallelSearchResult]
    synthesis: str = ""
    sources: list[str] = field(default_factory=list)

    @property
    def result_count(self) -> int:
        return len(self.results)

    def to_markdown(self) -> str:
        lines = [f"# Research: {self.objective}", ""]
        if self.synthesis:
            lines += ["## Summary", self.synthesis, ""]
        lines.append("## Results")
        for r in self.results[:20]:
            lines.append(f"### {r.title}")
            lines.append(f"*Source: {r.source}* {'| ' + r.url if r.url else ''}")
            lines.append(r.snippet)
            lines.append("")
        if self.sources:
            lines += ["## Sources"] + [f"- {s}" for s in self.sources]
        return "\n".join(lines)


# â”€â”€ Source implementations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def _search_duckduckgo(query: str, max_results: int = 5) -> list[ParallelSearchResult]:
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(ParallelSearchResult(
                    query=query,
                    source="duckduckgo",
                    title=r.get("title", ""),
                    snippet=r.get("body", "")[:500],
                    url=r.get("href", ""),
                ))
        return results
    except ImportError:
        logger.warning("[VECTOR][parallel_researcher] duckduckgo_search not installed")
        return []
    except Exception as e:
        logger.warning("[VECTOR][parallel_researcher] DuckDuckGo failed: {}", e)
        return []


async def _search_wikipedia(query: str, max_results: int = 3) -> list[ParallelSearchResult]:
    try:
        import wikipedia
        results = []
        loop = asyncio.get_event_loop()
        titles = await loop.run_in_executor(None, lambda: wikipedia.search(query, results=max_results))
        for title in titles[:max_results]:
            try:
                summary = await loop.run_in_executor(None, lambda t=title: wikipedia.summary(t, sentences=3))
                results.append(ParallelSearchResult(
                    query=query,
                    source="wikipedia",
                    title=title,
                    snippet=summary[:500],
                    url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                ))
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return results
    except Exception as e:
        logger.warning("[VECTOR][parallel_researcher] Wikipedia failed: {}", e)
        return []


async def _search_arxiv(query: str, max_results: int = 5) -> list[ParallelSearchResult]:
    try:
        import arxiv
        results = []
        client = arxiv.Client()
        search = arxiv.Search(query=query, max_results=max_results)
        loop = asyncio.get_event_loop()
        papers = await loop.run_in_executor(None, lambda: list(client.results(search)))
        for p in papers:
            results.append(ParallelSearchResult(
                query=query,
                source="arxiv",
                title=p.title,
                snippet=p.summary[:500],
                url=p.entry_id,
                score=0.9,
            ))
        return results
    except Exception as e:
        logger.warning("[VECTOR][parallel_researcher] ArXiv failed: {}", e)
        return []


# â”€â”€ ParallelResearcher â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ParallelResearcher:
    """
    Concurrent multi-source research tool.

    Usage:
        researcher = ParallelResearcher(mode="deep")
        report = await researcher.research(
            objective="latest advances in LLM compression",
            queries=["LLM quantization 2024", "token compression techniques"],
        )
        logger.info(report.to_markdown())

    """

    MODES = {
        "fast":    ["duckduckgo", "wikipedia"],
        "deep":    ["duckduckgo", "wikipedia", "arxiv"],
        "agentic": ["duckduckgo", "wikipedia", "arxiv"],
    }

    def __init__(self, mode: str = "fast", max_results_per_source: int = 5) -> None:
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of {list(self.MODES)}")
        self.mode = mode
        self.max_results = max_results_per_source
        self._sources = self.MODES[mode]

    async def research(
        self,
        objective: str,
        queries: list[str] | None = None,
        synthesize: bool = False,
    ) -> ResearchReport:
        """
        Run parallel research across all configured sources.

        Args:
            objective:  Research goal (used for synthesis)
            queries:    Search queries (if None, uses objective as single query)
            synthesize: If True, uses Ollama to synthesize a summary

        Returns:
            ResearchReport with merged results
        """
        if not queries:
            queries = [objective]

        logger.info(
            "[VECTOR][parallel_researcher] {} queries via {} sources (mode={})",
            len(queries), len(self._sources), self.mode,
        )

        tasks = []
        for query in queries[:10]:
            for source in self._sources:
                tasks.append(self._search_one(source, query))

        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: list[ParallelSearchResult] = []
        for r in all_results:
            if isinstance(r, list):
                merged.extend(r)

        # Deduplicate by title
        seen_titles: set[str] = set()
        deduped = []
        for r in merged:
            key = r.title.lower()[:60]
            if key not in seen_titles:
                seen_titles.add(key)
                deduped.append(r)

        sources = list({r.url for r in deduped if r.url})

        report = ResearchReport(
            objective=objective,
            queries=queries,
            results=deduped,
            sources=sources,
        )

        if synthesize and deduped:
            report.synthesis = await self._synthesize(objective, deduped[:10])

        logger.info(
            "[VECTOR][parallel_researcher] found {} results for '{}'",
            len(deduped), objective[:40],
        )
        return report

    async def _search_one(self, source: str, query: str) -> list[ParallelSearchResult]:
        fn = {
            "duckduckgo": _search_duckduckgo,
            "wikipedia": _search_wikipedia,
            "arxiv": _search_arxiv,
        }.get(source)
        if fn is None:
            return []
        return await fn(query, self.max_results)

    async def _synthesize(self, objective: str, results: list[ParallelSearchResult]) -> str:
        try:
            import httpx
            snippets = "\n".join(f"- {r.title}: {r.snippet[:200]}" for r in results)
            payload = {
                "model": "qwen3:14b",
                "prompt": f"Synthesize these research findings for: {objective}\n\n{snippets}\n\nWrite a 3-sentence summary:",
                "stream": False,
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post("http://localhost:11434/api/generate", json=payload)
                return resp.json().get("response", "")
        except Exception as e:
            logger.warning("[VECTOR][parallel_researcher] synthesis failed: {}", e)
            return ""


async def parallel_search(
    queries: list[str],
    mode: str = "fast",
    max_results: int = 5,
) -> list[ParallelSearchResult]:
    """Convenience: search multiple queries concurrently, return flat result list."""
    researcher = ParallelResearcher(mode=mode, max_results_per_source=max_results)
    report = await researcher.research(objective=queries[0], queries=queries)
    return report.results


async def parallel_extract(urls: list[str], max_chars: int = 5000) -> list[dict]:
    """Extract content from multiple URLs concurrently."""
    import httpx
    results = []

    async def _fetch(url: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "VECTOR/1.0"})
                text = resp.text[:max_chars]
                return {"url": url, "content": text, "status": resp.status_code}
        except Exception as e:
            return {"url": url, "content": "", "error": str(e)}

    tasks = [_fetch(url) for url in urls[:20]]
    results = await asyncio.gather(*tasks)
    return list(results)


if __name__ == "__main__":
    async def _test():
        r = ParallelResearcher(mode="fast")
        report = await r.research("Python asyncio", queries=["Python asyncio tutorial"])
        print(f"OK parallel_researcher.py — {report.result_count} results")

    asyncio.run(_test())
