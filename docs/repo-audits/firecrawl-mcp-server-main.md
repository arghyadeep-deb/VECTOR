# firecrawl-mcp-server-main Audit

**Repo:** Firecrawl MCP Server — TypeScript MCP server exposing Firecrawl tools (MIT)
**Audited:** 2026-06-02
**Verified:** `firecrawl 4.26.0` pip-installed; `FirecrawlApp` not used in any VECTOR file

---

## 1. Repo Reality

TypeScript MCP server (`@mendableai/firecrawl-mcp-server`) wrapping the Firecrawl API. Exposes **15 MCP tools**:
- `firecrawl_scrape` — structured scrape of a single URL
- `firecrawl_crawl` — recursive crawl of an entire site
- `firecrawl_map` — discover all URLs in a domain
- `firecrawl_search` — web search with full-content extraction
- `firecrawl_extract` — LLM-guided structured data extraction
- `firecrawl_deep_research` — autonomous multi-step research agent
- `firecrawl_generate_llmstxt` — generate LLMs.txt for any domain
- Plus batch, cancel, status, and monitor operations

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|------------------|-----------------|--------|
| Structured web scraping | `WebScout` uses DDG HTML parser only | FirecrawlApp: NONE | ❌ Gap |
| Recursive site crawl | ❌ No crawl capability | N/A | ❌ |
| Web search + full content | `WebScout._parse_ddg_html()` (limited) | DDG-only | ⚠️ Partial |
| LLM extraction | ❌ No LLM-guided extraction | N/A | ❌ |
| Autonomous research agent | ❌ No deep research mode | N/A | ❌ |
| firecrawl pip package | `firecrawl 4.26.0` installed | ✅ installed | ✅ |
| Used in VECTOR code | ❌ FirecrawlApp unused everywhere | grep: NONE | ❌ |

---

## 3. Frontend: N/A

---

## 4. Verdict

**INTEGRATE DIRECTLY** — Two integration paths:
1. Run MCP server: `npx @mendableai/firecrawl-mcp-server` with `FIRECRAWL_API_KEY`
2. Wire `FirecrawlApp` directly into `districts/research/web_scout.py` — firecrawl is already pip-installed, just never called

The second option (direct Python use) is better for the autonomous loop. Add `FIRECRAWL_API_KEY` to `.env`, then use `FirecrawlApp(api_key=...).scrape_url()` as a primary backend in `WebScout`, falling back to DDG when not configured.

**Delete-readiness:** DELETE-NOW clone — use pip package (`firecrawl 4.26.0` already installed).

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | `FirecrawlApp` pip-installed but never called — `WebScout` still uses DDG-only HTML parsing | `districts/research/web_scout.py` | HIGH |
| G2 | No recursive site crawl capability in VECTOR | `districts/research/web_scout.py` | MED |
| G3 | No LLM-guided data extraction from arbitrary URLs | `districts/research/` | MED |
