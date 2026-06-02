# modelcontextprotocol-main Audit

**Repo:** Perplexity API MCP Server — TypeScript MCP server for Perplexity AI (MIT)
**Note:** Despite the folder name "modelcontextprotocol-main", this is actually the **Perplexity AI MCP server** (`@perplexity-ai/mcp-server`), not the MCP SDK itself.
**Audited:** 2026-06-02

---

## 1. Repo Reality

TypeScript MCP server exposing Perplexity AI's search/reasoning API as MCP tools:
- `perplexity_search` — real-time web search with citations
- `perplexity_ask` — question answering with reasoning
- `perplexity_research` — deep research with multi-step synthesis
- `perplexity_reason` — structured chain-of-thought reasoning

Run via: `npx @perplexity-ai/mcp-server` with `PERPLEXITY_API_KEY`.

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Status |
|---------|------------------|--------|
| Web search | `WebScout` (DuckDuckGo, no API key) | ⚠️ DDG only, no citations |
| AI-powered research with citations | ❌ No Perplexity integration | ❌ |
| 27-provider LLM routing | `provider_client.py` includes Perplexity | ✅ (text gen, not search) |

---

## 3. Frontend: N/A

---

## 4. Verdict

**PATCH VECTOR** — Add Perplexity as a search tool in `core/mcp_server.py`. Simpler than running MCP sidecar: use Perplexity's OpenAI-compat API directly via `provider_client.py` (already has the provider registered). Add `PERPLEXITY_API_KEY` to `.env`.

Alternatively: `npx @perplexity-ai/mcp-server` as a sidecar and call `perplexity_search` from the research district.

**Delete-readiness:** DELETE-NOW clone — `npx` handles it, no local code needed.

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | No real-time web search with citations — DDG returns snippets without sources | `districts/research/web_scout.py` | MED |
| G2 | `PERPLEXITY_API_KEY` not wired to search (only to text completions via provider_client) | `core/config.py` | LOW |
