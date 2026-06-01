# MCP/Infra Batch Audit
> Audited: 2026-06-01 | Auditor: VECTOR Agent
> VECTOR MCP context: `core/mcp_server.py` uses FastMCP 3.2.4 (installed) with 300+ tools across 16 categories.

---

## fastmcp-main

**What it is:**
FastMCP is a Python MCP framework (Apache-2.0, by Prefect). This is the **source repo** for the `fastmcp` package that VECTOR already depends on. Current installed version: **3.2.4**. The repo contains `fastmcp_slim` (core server+client) and `fastmcp_remote` (OAuth/remote transport extras).

Key features in the repo:
- `FastMCP` server with `@mcp.tool`, `@mcp.resource`, `@mcp.prompt` decorators
- `Client` for consuming any MCP server programmatically
- `as_proxy` — wrap any external MCP server and re-expose it as tools on your own server
- `import_server` — merge another FastMCP server's tools into your instance
- `from_openapi` — generate MCP tools from any OpenAPI spec
- `middleware` — add pre/post-processing to all tool calls
- Auth layer, OpenTelemetry tracing, `docket` task queue, App UI (interactive UIs in conversation)
- Transports: stdio, SSE, Streamable HTTP

**VECTOR parity:**
VECTOR already has `fastmcp` 3.2.4 installed and `core/mcp_server.py` is built entirely on it. The `_make_server()` function (`create_mcp_app` alias) uses `FastMCP("VECTOR")` with `@mcp.tool` throughout. The `core/mcp/client.py` exists as a hand-rolled JSON-RPC client that predates FastMCP's own `Client` class.

**Gaps vs installed version:**
The repo version matches what is installed (3.2.4). No upgrade delta. However two FastMCP features are **not yet used by VECTOR**:
1. `fastmcp.Client` — VECTOR's `core/mcp/client.py` re-implements MCP client from scratch over raw JSON-RPC subprocess I/O. FastMCP's `Client` handles stdio, SSE, and HTTP transports with full protocol support and is the correct replacement.
2. `mcp.as_proxy` / `mcp.import_server` — VECTOR could use these to proxy external MCP servers (Playwright MCP, Firecrawl MCP) directly into its tool namespace without writing Python wrappers.

**Integration plan:**
- Replace `core/mcp/client.py` raw JSON-RPC impl with `from fastmcp import Client` — smaller, battle-tested, supports all transports.
- When integrating external MCP servers (see Playwright/Firecrawl below), use `mcp.import_server(external_mcp)` to merge their tools into VECTOR's namespace at startup rather than spawning separate processes.
- No code changes required to `core/mcp_server.py` — it already uses FastMCP correctly.

**Verdict: SAFE TO DELETE THE REPO (already installed)**
The package is on PyPI at the correct version. The repo copy is redundant. The two unused FastMCP features (`Client`, `as_proxy`) are available in the already-installed package — no upgrade needed.

---

## modelcontextprotocol-main

**What it is:**
This is the **official Perplexity AI MCP server** (`@perplexity-ai/mcp-server`) — NOT the MCP specification repo (despite the folder name). TypeScript/Node.js, MIT license. It exposes 4 tools via `npx @perplexity-ai/mcp-server`:

| Tool | What it does |
|------|-------------|
| `perplexity_search` | Direct web search via Perplexity Search API, returns ranked results with metadata |
| `perplexity_ask` | Conversational AI + real-time web (sonar-pro model) |
| `perplexity_research` | Deep research mode (sonar-deep-research model) |
| `perplexity_reason` | Advanced reasoning (sonar-reasoning-pro model) |

Requires `PERPLEXITY_API_KEY`. Optional `strip_thinking` param on reason/research.

**VECTOR parity:**
VECTOR has `search_web` (DuckDuckGo via WebScout), `read_paper` (ArXiv), `mine_reddit` (Reddit), and `find_public_api`. It does NOT have a Perplexity-specific integration. The key differentiator is `perplexity_research` (sonar-deep-research) and `perplexity_reason` (sonar-reasoning-pro) — these are citation-grounded, multi-source synthesis tools that VECTOR's DuckDuckGo WebScout cannot replicate.

However: Perplexity is also listed in VECTOR's `core/inference/llm_providers.py` as a chat provider. VECTOR could call Perplexity's API directly via `provider_client.py` — it does not need a separate MCP server process to do so.

**Integration plan if desired:**
The simplest integration is NOT to run this as a separate MCP server process, but to add a `perplexity_research(query, mode)` tool directly to `core/mcp_server.py` that calls `core/inference/provider_client.py` with `provider="perplexity"`. This is cleaner than an external Node process.

If VECTOR needs the exact sonar models without going through provider_client, add `PERPLEXITY_API_KEY` to `.env` and run this server as a sidecar, then proxy it via `fastmcp.Client` + `mcp.import_server`.

**Verdict: SAFE TO DELETE THE REPO / PATCH VECTOR**
No Python to absorb — TypeScript/Node only. The 4 tools can be added as a thin `perplexity_research` MCP tool in `core/mcp_server.py` using the Perplexity provider already in `llm_providers.py`. The repo itself is not needed.

---

## playwright-mcp-main

**What it is:**
Official Microsoft Playwright MCP server (`@playwright/mcp`, TypeScript/Node.js, Apache-2.0). Provides browser automation as MCP tools — uses Playwright's accessibility tree (not screenshots). Run via `npx @playwright/mcp@latest`.

**Full tool inventory (25+ tools across capability groups):**

*Core automation (always on):*
`browser_navigate`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_snapshot`, `browser_take_screenshot`, `browser_close`, `browser_hover`, `browser_drag`, `browser_drop`, `browser_evaluate`, `browser_file_upload`, `browser_handle_dialog`, `browser_press_key`, `browser_resize`, `browser_select_option`, `browser_wait_for`, `browser_console_messages`, `browser_network_requests`, `browser_network_request`, `browser_run_code_unsafe`, `browser_navigate_back`, `browser_tabs`

*Opt-in via caps flags:*
`browser_get_config` (`--caps=config`), `browser_network_state_set` (`--caps=network`), PDF tools (`--caps=pdf`), vision/coordinate tools (`--caps=vision`), devtools (`--caps=devtools`)

**VECTOR parity:**
VECTOR has:
- `core/browser/dom_pruner.py` — prunes accessibility element lists (absorbed from auto-browser)
- `core/browser/auth_profiles.py` — named browser auth profiles (Playwright storage state)
- `core/browser/pii_scrub.py` — scrubs PII from browser observations
- `core/control/pc_controller.py` — pyautogui screen control
- `districts/time_calendar/kiit_scraper.py` — Playwright scraper for KIIT portal
- MCP tools: `browser_prune_dom`, `browser_list_auth_profiles`, `browser_save_auth_profile`

**What VECTOR does NOT have:** A live, persistent, browser automation MCP server with full click/type/navigate/screenshot loop. VECTOR's Playwright usage is task-specific Python scripts. There is no general-purpose browser agent loop callable from VECTOR's autonomous loop.

**Integration plan (INTEGRATE DIRECTLY):**
Run as a sidecar MCP server process:
```json
{
  "playwright": {
    "command": "npx",
    "args": ["@playwright/mcp@latest", "--headless", "--port", "8931"]
  }
}
```
Then in VECTOR's autonomous loop / district code, use `core/mcp/client.py` (or FastMCP's `Client`) to call `browser_navigate`, `browser_snapshot`, `browser_click` etc. from Python. This gives VECTOR's agents a full browser loop without reimplementing Playwright in Python.

The `core/browser/` absorption (dom_pruner, auth_profiles, pii_scrub) complements this perfectly: VECTOR prunes and scrubs the raw observations before feeding them to the LLM.

**Verdict: INTEGRATE DIRECTLY**
Run alongside VECTOR as a sidecar process (`npx @playwright/mcp@latest --headless --port 8931`). VECTOR's autonomous loop calls it via `MCPClient`. No Python reimplementation needed. The sidecar adds ~25 browser tools that no VECTOR district currently provides in an agent-callable way.

---

## firecrawl-mcp-server-main

**What it is:**
Official Firecrawl MCP server (TypeScript/Node.js, MIT). Exposes Firecrawl cloud/self-hosted API as MCP tools. Requires `FIRECRAWL_API_KEY` (or self-hosted URL). Run via `npx firecrawl-mcp`.

**Full tool inventory (15 tools):**

*Core scraping/search:*
| Tool | What it does |
|------|-------------|
| `firecrawl_scrape` | Scrape a URL to markdown, JSON, or structured data (with LLM extraction schema) |
| `firecrawl_map` | Discover all URLs on a site (sitemap-style) |
| `firecrawl_search` | Web search returning full-page content, not just snippets |
| `firecrawl_search_feedback` | Refund credits + improve search quality (optional) |
| `firecrawl_crawl` | Crawl a site recursively, follow links |
| `firecrawl_check_crawl_status` | Poll async crawl job status |
| `firecrawl_extract` | LLM-powered structured extraction across multiple URLs |
| `firecrawl_agent` | Autonomous web research agent (multi-step, deep research) |
| `firecrawl_agent_status` | Poll async agent job |
| `firecrawl_interact` | Start interactive browser session (click/navigate on a page) |
| `firecrawl_interact_stop` | End an interactive session |
| `firecrawl_parse` | Parse a local file (self-hosted only) |

*Monitor tools (via monitor.ts):*
`firecrawl_monitor_create`, `firecrawl_monitor_list`, `firecrawl_monitor_get`, `firecrawl_monitor_update`, `firecrawl_monitor_delete`, `firecrawl_monitor_run`, `firecrawl_monitor_checks`, `firecrawl_monitor_check`

**VECTOR parity:**
VECTOR has `search_web` (DuckDuckGo, no full-page content), `read_paper` (ArXiv PDF), `mine_reddit` (Reddit API). The key gaps:
- `firecrawl_scrape` with JSON schema extraction — VECTOR has no equivalent structured scraping tool
- `firecrawl_crawl` — recursive site crawl, no equivalent
- `firecrawl_map` — URL discovery across a domain, no equivalent
- `firecrawl_agent` — multi-step autonomous web research loop, no equivalent
- `firecrawl_monitor_*` — recurring scrape monitors with diff detection, no equivalent in VECTOR
- `firecrawl_extract` — cross-URL LLM extraction with a shared schema, no equivalent

**Integration plan (INTEGRATE DIRECTLY):**
Firecrawl is the most impactful addition for VECTOR's research district. Run as a sidecar:
```bash
env FIRECRAWL_API_KEY=fc-YOUR_KEY npx -y firecrawl-mcp
```
VECTOR's `districts/research/web_scout.py`, `paper_reader.py`, and `startups/market_scanner.py` would all benefit from calling `firecrawl_scrape` and `firecrawl_search` instead of raw DuckDuckGo + httpx. The monitor tools enable VECTOR to watch URLs for changes — directly useful for `startups/` (competitor pages) and `news_trends/` (news sources).

If no Firecrawl API key: Firecrawl supports self-hosted deployment (Docker). The `FIRECRAWL_API_URL` env var points to the local instance.

**Verdict: INTEGRATE DIRECTLY**
Run as a sidecar MCP process. Call from `districts/research/` via `MCPClient`. The 12 content tools fill a genuine gap in VECTOR's web research stack — structured extraction, recursive crawl, and autonomous web agents are not covered by existing districts.

---

## ClawRouter-main

**What it is:**
ClawRouter (TypeScript/Node.js, MIT) is an **agent-native LLM router and local proxy**. It runs on `localhost:8402` as an OpenAI-compatible API server. Key properties:
- 55+ models from OpenAI, Anthropic, Google, xAI, DeepSeek, Mistral, etc.
- **10 NVIDIA models free forever** (no API key, no signup) — including DeepSeek V4 (1M context) and a vision model
- Local routing in <1ms via 15-dimension weighted scoring (no external API calls for routing decisions)
- Authentication via local Ed25519 wallet signature (no API keys for payment; USDC via x402 protocol)
- 4 routing profiles: `free`, `eco`, `auto`, `premium`
- Smart tier classification: SIMPLE / MEDIUM / COMPLEX / REASONING
- Image generation (`/cr-imagegen`): 8 models (DALL-E-3, GPT-Image, Flux, Grok Imagine, CogView-4, etc.)
- Video generation (`/videogen`): Seedance 1.5/2.0, Grok Video
- Responds to any OpenAI-compatible client (`base_url="http://localhost:8402"`)

**Routing logic (15 dimensions):**
Token count, code keyword match, multilingual code keywords (EN/ZH/JA/RU/DE/ES/PT/KO/AR), multi-step patterns, question complexity, agentic task indicators, structured output signals, math/reasoning signals, vision input, tool calling requirements, context length, response format, task urgency, user tier preference.

**VECTOR parity:**
VECTOR has significant routing infrastructure:
- `vectorcode/src/router.py` — 4-layer GNNRouter: MoE(L0) → GNN(L1) → keyword(L2) → regex(L3)
- `core/inference/provider_client.py` — 27-provider routing with Ollama-first policy, tier-based routing, sensitivity/complexity routing (security/RED → local only)
- `core/inference/llm_providers.py` — 27 cloud providers including Anthropic, Google, OpenAI, Groq, DeepSeek, Mistral, OpenRouter, Together, Fireworks, etc.
- `vectorcode/src/neural_moe_router.py` — 8-expert MoE gating, top-k, load balancing

**What VECTOR does NOT have:**
1. Free-tier models with zero setup (ClawRouter's 10 free NVIDIA models work without any API keys)
2. USDC micropayment authentication (x402 protocol) — useful if VECTOR agents ever need to autonomously pay for model calls without a hardcoded API key
3. Image generation routing across 8 providers from a single endpoint (VECTOR's `districts/content/` has ComfyUI + SadTalker but no multi-provider image gen routing)
4. Video generation routing (VECTOR has SadTalker/FFmpeg locally but no Seedance/Grok Video access)
5. ClawRouter's 15-dimension scoring classifier as a reference for improving VECTOR's own routing

**Integration plan:**
ClawRouter is NOT an MCP server — it is a local OpenAI-compatible proxy. VECTOR's `provider_client.py` can already use it by adding `ClawRouter` as a provider with `base_url="http://localhost:8402"` and `api_key="x402"`. This requires no code changes beyond adding a config entry.

The **10 free NVIDIA models** are the primary value: if VECTOR's API keys are exhausted or unavailable, pointing `provider_client.py` at `localhost:8402` gives free access to DeepSeek V4 (1M context) and others. Add to `core/config.py`:
```python
"clawrouter": {
    "base_url": "http://localhost:8402/v1",
    "api_key": "x402",
    "free_models": ["nvidia/gpt-oss-120b", "nvidia/llama-3.1-nemotron-ultra-253b-v1"],
}
```

For image/video generation routing, the `/v1/images/generations` and `/v1/videos/generations` endpoints can be called directly via httpx from `districts/content/`.

The 15-dimension routing scoring is worth studying as a reference to improve VECTOR's `GNNRouter` tier classification, but direct absorption is not needed — VECTOR's routing is already more sophisticated (GNN + MoE layers).

**Verdict: PATCH VECTOR (config only, no code)**
ClawRouter does not need to be absorbed. Run `npx @blockrun/clawrouter` as a background process and add `clawrouter` as a fallback provider in `core/config.py`. The primary value is the 10 free NVIDIA models as a zero-cost fallback when Ollama is unavailable or API keys run out. The image/video generation routing is a bonus for `districts/content/`.

---

## Summary

| Repo | Language | Verdict | Action Required | Priority |
|------|----------|---------|-----------------|----------|
| **fastmcp-main** | Python | SAFE TO DELETE | Replace `core/mcp/client.py` with `fastmcp.Client` (optional cleanup) | Low |
| **modelcontextprotocol-main** | TypeScript | SAFE TO DELETE / PATCH VECTOR | Add `perplexity_research` tool to `core/mcp_server.py` using existing Perplexity provider | Low |
| **playwright-mcp-main** | TypeScript | INTEGRATE DIRECTLY | Run as sidecar: `npx @playwright/mcp@latest --headless --port 8931`; VECTOR's loop calls it via `MCPClient` | High |
| **firecrawl-mcp-server-main** | TypeScript | INTEGRATE DIRECTLY | Run as sidecar: `npx firecrawl-mcp`; wire into `districts/research/` and `districts/startups/` | High |
| **ClawRouter-main** | TypeScript | PATCH VECTOR (config only) | Run `npx @blockrun/clawrouter`; add as fallback provider in `core/config.py`; free NVIDIA models as Ollama fallback | Medium |

### Integration Priority Order

1. **Playwright MCP** (High) — adds a general-purpose browser automation loop VECTOR's agents currently lack. VECTOR's `core/browser/` absorption (dom_pruner + auth_profiles) was built for exactly this integration. One command starts it; `MCPClient` calls it from any district.

2. **Firecrawl MCP** (High) — fills the structured web extraction gap. `districts/research/`, `districts/startups/market_scanner.py`, and `districts/news_trends/` would all benefit. `firecrawl_agent` alone enables autonomous multi-step web research that VECTOR's WebScout cannot do.

3. **ClawRouter** (Medium) — zero-setup free model fallback. Start it as a background process alongside VECTOR; add one config entry. Costs nothing, provides safety net when Ollama is unavailable or API keys expire.

4. **Perplexity MCP** (Low) — already covered by `llm_providers.py`. Add a thin `perplexity_research` MCP tool if citation-grounded research becomes a priority.

5. **FastMCP repo** (Low) — delete, already installed. Optional: replace `core/mcp/client.py` with `fastmcp.Client` when time permits.

### What Changes in VECTOR

**For Playwright + Firecrawl integration, add to `core/mcp_server.py` or `core/loop/autonomous_loop.py`:**
```python
# In core/config.py, add sidecar MCP servers config
"mcp_sidecars": {
    "playwright": {"url": "http://localhost:8931/mcp"},
    "firecrawl":  {"command": "npx", "args": ["-y", "firecrawl-mcp"]},
}
```
VECTOR's `MCPClient` (`core/mcp/client.py`) already supports both stdio and HTTP transports — no new code needed, only configuration.

**For ClawRouter, add to `core/config.py`:**
```python
"clawrouter": {
    "base_url": "http://localhost:8402/v1",
    "api_key": "x402",
    "free_models": ["nvidia/gpt-oss-120b"],
    "enabled": False,  # set True after running: npx @blockrun/clawrouter
}
```
Then wire into `provider_client.py`'s fallback chain after Ollama.

### No Python Absorption Required
All three integrate repos (Playwright MCP, Firecrawl MCP, ClawRouter) are TypeScript/Node.js and expose clean APIs. They run as external processes — VECTOR consumes them via existing client infrastructure. Zero Python reimplementation.
