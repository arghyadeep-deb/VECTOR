"""
VECTOR Research API — single interface for all districts that need research.

Wraps core/research_engine with VECTOR's model routing, loguru logging,
and Obsidian output. Districts never import from core.research_engine directly.

Model routing (VECTOR Rule 11 — local Ollama only):
    quick    → vector-focus  (gemma4:e2b, 40+ tok/s, permanent VRAM)
    reason   → vector-reasoning (qwen3:14b, step-by-step)
    deep     → vector-reasoning  (qwen3:14b, 65K context, overnight)
    papers   → vector-reasoning (academic papers need structured reasoning)

Search engines (free, no API key required by default):
    auto     → DuckDuckGo + Wikipedia + ArXiv (VECTOR default)
    academic → ArXiv + PubMed + Semantic Scholar + OpenAlex
    news     → DuckDuckGo + Wikinews + The Guardian
    web      → DuckDuckGo + SearXNG (if running locally)
"""

from pathlib import Path
from datetime import datetime
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG

# ── VECTOR model routing ──────────────────────────────────────────────────────

_MODEL_ROUTES = {
    "quick":   CONFIG.get("models", {}).get("focus", "vector-focus"),
    "reason":  CONFIG.get("models", {}).get("reasoning", "vector-reasoning"),
    "deep":    CONFIG.get("models", {}).get("deep", "qwen3:14b"),
    "papers":  CONFIG.get("models", {}).get("reasoning", "vector-reasoning"),
}

_OLLAMA_URL = CONFIG.get("OLLAMA_HOST", "http://127.0.0.1:11434")

_BRAIN_RESEARCH_DIR = Path(
    CONFIG.get("paths", {}).get(
        "brain_research",
        str(Path.home() / "V.E.C.T.O.R Brain" / "Research")
    )
)

def _make_settings(mode: str = "quick", search_tool: str = "auto",
                   max_results: int = 10, iterations: int = 2,
                   extra_overrides: dict | None = None) -> dict:
    """Build a research engine settings snapshot using VECTOR's Ollama models."""
    try:
        from core.research_engine.api.settings_utils import create_settings_snapshot
    except ImportError as e:
        logger.error("[VECTOR][research_api] core.research_engine not available: {}", e)
        raise

    model = _MODEL_ROUTES.get(mode, _MODEL_ROUTES["quick"])
    overrides: dict[str, Any] = {
        "llm.provider": "ollama",
        "llm.model": model,
        "llm.ollama_base_url": _OLLAMA_URL,
        "llm.temperature": 0.3,
        "llm.max_tokens": 4096,
        "search.tool": search_tool,
        "search.max_results": max_results,
        "search.iterations": iterations,
        "programmatic_mode": True,
    }
    if extra_overrides:
        overrides.update(extra_overrides)

    return create_settings_snapshot(overrides=overrides)

def _save_to_brain(content: str, title: str, subfolder: str = "") -> Path | None:
    """Save research output to VECTOR Brain/Research/ for Obsidian."""
    try:
        target_dir = _BRAIN_RESEARCH_DIR / subfolder if subfolder else _BRAIN_RESEARCH_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:60]
        fpath = target_dir / f"{timestamp}_{safe_title}.md"
        fpath.write_text(content, encoding="utf-8")
        logger.info("[VECTOR][research_api] Saved to Brain: {}", fpath.name)
        return fpath
    except Exception as e:
        logger.warning("[VECTOR][research_api] Could not save to Brain: {}", e)
        return None

# ── Public API ────────────────────────────────────────────────────────────────

def quick_research(query: str, save_to_brain: bool = True) -> dict:
    """
    Fast research summary using vector-focus (1-3 min).
    Uses DuckDuckGo + Wikipedia + ArXiv. No API key needed.

    Returns:
        dict with keys: summary, findings, sources, research_id, brain_path
    """
    logger.info("[VECTOR][research_api] Quick research: {}", query[:80])
    try:
        from core.research_engine.api.research_functions import quick_summary
        settings = _make_settings(mode="quick", search_tool="auto",
                                   max_results=8, iterations=2)
        result = quick_summary(query, settings_snapshot=settings)

        if save_to_brain and result.get("summary"):
            content = f"# Research: {query}\n\n{result['summary']}\n\n"
            if result.get("sources"):
                content += "## Sources\n\n"
                for src in result["sources"][:10]:
                    content += f"- {src}\n"
            result["brain_path"] = str(_save_to_brain(content, query, "quick"))

        logger.info("[VECTOR][research_api] Quick research complete — {} chars",
                    len(result.get("summary", "")))
        return result
    except Exception as e:
        logger.error("[VECTOR][research_api] quick_research failed: {}", e)
        return {"summary": f"Research failed: {e}", "findings": [], "sources": [], "error": str(e)}

def generate_report(query: str, searches_per_section: int = 2,
                    save_to_brain: bool = True) -> dict:
    """
    Full structured research report using vector-reasoning (10-30 min).
    Multi-section markdown report with citations.

    Returns:
        dict with keys: content, metadata, brain_path
    """
    logger.info("[VECTOR][research_api] Generating report: {}", query[:80])
    try:
        from core.research_engine.api.research_functions import generate_report as _gen
        settings = _make_settings(mode="deep", search_tool="auto",
                                   max_results=15, iterations=3)
        result = _gen(query, searches_per_section=searches_per_section,
                      settings_snapshot=settings)

        if save_to_brain and result.get("content"):
            result["brain_path"] = str(
                _save_to_brain(result["content"], f"Report_{query}", "reports")
            )

        logger.info("[VECTOR][research_api] Report generated — {} chars",
                    len(result.get("content", "")))
        return result
    except Exception as e:
        logger.error("[VECTOR][research_api] generate_report failed: {}", e)
        return {"content": f"Report generation failed: {e}", "metadata": {}, "error": str(e)}

def research_papers(query: str, max_results: int = 10) -> dict:
    """
    Academic paper research using ArXiv + PubMed + Semantic Scholar.
    Uses vector-reasoning for structured paper analysis.

    Returns:
        dict with keys: summary, findings, sources
    """
    logger.info("[VECTOR][research_api] Paper research: {}", query[:80])
    try:
        from core.research_engine.api.research_functions import quick_summary
        settings = _make_settings(
            mode="papers", search_tool="arxiv",
            max_results=max_results, iterations=2,
            extra_overrides={"search.strategy": "source_based"}
        )
        result = quick_summary(query, settings_snapshot=settings)
        logger.info("[VECTOR][research_api] Paper research complete — {} findings",
                    len(result.get("findings", [])))
        return result
    except Exception as e:
        logger.error("[VECTOR][research_api] research_papers failed: {}", e)
        return {"summary": f"Paper research failed: {e}", "findings": [], "sources": [], "error": str(e)}

def research_news(query: str, max_results: int = 10) -> dict:
    """
    News research using DuckDuckGo + Wikinews. Fast, no API key needed.

    Returns:
        dict with keys: summary, findings, sources
    """
    logger.info("[VECTOR][research_api] News research: {}", query[:80])
    try:
        from core.research_engine.api.research_functions import quick_summary
        settings = _make_settings(
            mode="quick", search_tool="auto",
            max_results=max_results, iterations=1,
            extra_overrides={"search.strategy": "news"}
        )
        result = quick_summary(query, settings_snapshot=settings,
                                search_original_query=False)
        return result
    except Exception as e:
        logger.error("[VECTOR][research_api] research_news failed: {}", e)
        return {"summary": f"News research failed: {e}", "findings": [], "sources": [], "error": str(e)}

def analyze_documents(query: str, collection_name: str,
                      max_results: int = 10) -> dict:
    """
    Search a local document collection (ChromaDB/LightRAG).

    Returns:
        dict with keys: summary, documents, collection
    """
    logger.info("[VECTOR][research_api] Document search: {} in '{}'",
                query[:60], collection_name)
    try:
        from core.research_engine.api.research_functions import analyze_documents as _ad
        settings = _make_settings(mode="reason")
        result = _ad(query, collection_name=collection_name,
                     max_results=max_results, settings_snapshot=settings)
        return result
    except Exception as e:
        logger.error("[VECTOR][research_api] analyze_documents failed: {}", e)
        return {"summary": f"Document analysis failed: {e}", "documents": [], "error": str(e)}

if __name__ == "__main__":
    # Smoke test — quick research with no API key
    result = quick_research("What is VECTOR autonomous AI system?", save_to_brain=False)
    summary = result.get("summary", "")
    print(f"[OK] quick_research: {len(summary)} chars returned")
    print("research_api.py OK")
