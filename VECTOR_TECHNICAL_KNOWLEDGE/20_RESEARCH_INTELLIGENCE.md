# Research and Intelligence

**Purpose:** Web research, information gathering, analysis
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR's research district provides web search, content scraping, data extraction, and analysis capabilities.

**Key Properties:**
- **Web search** — multi-engine search
- **Content scraping** — browser-based extraction
- **Data analysis** — LLM-powered synthesis
- **Summarization** — concise summaries

**Files:** `districts/research/`
**Status:** ✅ IMPLEMENTED, production-reachable

---

## Research Agents

### WebResearcher

**File:** `districts/research/web_researcher.py`
**Status:** ✅ IMPLEMENTED

```python
class WebResearcher(AgentBase):
    """Web research agent."""
    
    async def _execute_task(self, query: str, task_type: str) -> dict:
        if task_type == "search":
            return await self._search(query)
        elif task_type == "scrape":
            return await self._scrape(query)
        elif task_type == "analyze":
            return await self._analyze(query)
        else:
            return {"success": False, "error": "Unknown task type"}
    
    async def _search(self, query: str) -> dict:
        """Search web."""
        from tools.web_tools import web_search
        
        results = await web_search(query)
        
        # Summarize with LLM
        from core.inference.provider_client import chat
        
        prompt = f"""Summarize these search results for: {query}

Results:
{json.dumps(results, indent=2)}

Provide a concise summary with key findings."""
        
        response = await chat([{"role": "user", "content": prompt}])
        
        return {
            "success": True,
            "summary": response.content,
            "sources": results
        }
    
    async def _scrape(self, url: str) -> dict:
        """Scrape webpage."""
        from tools.browser_tools import browser_scrape
        
        content = await browser_scrape(url)
        
        return {
            "success": True,
            "content": content
        }
    
    async def _analyze(self, query: str) -> dict:
        """Analyze data."""
        # Search first
        search_results = await self._search(query)
        
        if not search_results["success"]:
            return search_results
        
        # Deep analysis with LLM
        from core.inference.provider_client import chat
        
        prompt = f"""Deep analysis of: {query}

Data:
{search_results['summary']}

Provide:
1. Key findings
2. Patterns/trends
3. Implications
4. Recommendations"""
        
        response = await chat([{"role": "user", "content": prompt}])
        
        return {
            "success": True,
            "analysis": response.content,
            "sources": search_results["sources"]
        }
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Web search | 1-5s | API latency |
| Content scraping | 2-10s | Network |
| Analysis | 3-15s | LLM call |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `16_TOOL_SYSTEM.md` — Tool system
- `17_COMMUNICATIONS.md` — Communications

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
