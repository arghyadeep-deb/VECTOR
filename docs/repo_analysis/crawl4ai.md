# crawl4ai-main - VECTOR Absorption Review

**Verdict:** IMPLEMENT narrow crawler/extraction upgrade. Do not vendor the full server or bypass VECTOR's scraper boundaries.

**Priority:** HIGH for research/content quality

**Effort:** 1-2 sessions for a provider adapter and extraction contract

**License:** Apache-2.0 plus an explicit attribution requirement in the local license text.

**Repo size inspected:** About 875 files, excluding git/build/cache directories.

## What It Is

Crawl4AI is a Python LLM-friendly web crawler and scraper. It turns dynamic web pages into clean Markdown/structured data for RAG, agents, and data pipelines.

It includes:

- async Playwright/Patchright crawling
- LLM-ready Markdown generation
- BM25/fit-Markdown filtering
- CSS/XPath/schema-based extraction
- LLM extraction
- deep crawling and crash recovery
- sessions, cookies, profiles, proxies, browser hooks
- screenshots/media/link/iframe extraction
- Docker/FastAPI server mode

## VECTOR Overlap

VECTOR already has:

- `core/scraper` and research-engine fetch paths
- Playwright usage in time/calendar scraping
- research library and citation handling
- YouTube/content intelligence
- browser/MCP surfaces

Crawl4AI is a strong upgrade candidate for extraction quality, not a replacement for VECTOR's research engine.

## Real Value For VECTOR

Useful narrow additions:

- HTML-to-clean-Markdown extraction provider
- source-aware link/reference extraction
- schema-based extraction for repetitive pages
- query-focused/BM25 content pruning before LLM calls
- deep crawl resume state for long research jobs
- screenshot/debug artifacts for failed crawls
- crawler result schema: markdown, links, metadata, screenshots, fetch time, content hash

## Risks

- attribution requirement means vendoring/redistribution needs notices
- Docker API history includes serious security issues, so self-hosted server mode must be treated carefully
- stealth/proxy features can drift into unwanted scraping behavior
- browser sessions/cookies are sensitive and must not leak into general agents
- large dependency surface

## Recommendation For Sonnet

Build a VECTOR-native crawler provider wrapper first.

1. Add a `WebExtractionProvider` interface if none exists.
2. Implement a disabled-by-default Crawl4AI provider path or clean-room equivalent.
3. Normalize outputs into VECTOR research artifacts with citations and hashes.
4. Keep credentials/cookies isolated per approved task.
5. Route deep crawls through scheduler/PermissionGateway limits.
6. Add attribution notes if Crawl4AI code/dependency is distributed with VECTOR.

## Acceptance Criteria

- VECTOR works without Crawl4AI installed.
- A crawl result always includes URL, fetch timestamp, content hash, and extraction mode.
- No crawler can read local files or internal URLs unless explicitly allowed.
- External crawling respects rate limits and robots/terms policy decisions.
- Research prompts receive clean Markdown, not raw noisy HTML.

