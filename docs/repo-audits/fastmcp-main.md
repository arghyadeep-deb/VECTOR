# fastmcp-main Audit

**Repo path:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\fastmcp-main`
**Audited:** 2026-06-02
**Verdict:** SAFE TO DELETE — pip package `fastmcp==3.2.4` already installed and fully wired into VECTOR's MCP server

---

## 1. Repo Reality

| Field | Value |
|-------|-------|
| Package name | `fastmcp` (PyPI) — workspace of `fastmcp-slim` + `fastmcp-remote` |
| Author | Jeremiah Lowin / Prefect |
| License | Apache-2.0 |
| Version in local repo | Dynamic via `uv-dynamic-versioning` (git tag-based); repo is a dev workspace |
| Version pip-installed in VECTOR | **3.2.4** (confirmed live) |
| Requires-Python | >= 3.10 |
| Downloads | ~1 million/day; powers 70% of MCP servers across all languages |
| FastMCP 1.0 heritage | Incorporated into the official MCP Python SDK in 2024; this standalone project is the actively maintained evolution |

### What fastmcp provides

Three pillars: **Servers** (expose Python functions as MCP-compliant tools/resources/prompts), **Clients** (connect to any MCP server with full protocol support, stdio/SSE/HTTP), and **Apps** (interactive UIs rendered inside conversations). Key features:

- `@mcp.tool` decorator → auto-generates JSON schema, validation, and docs from Python type hints
- Transport negotiation: stdio (default), SSE, Streamable HTTP
- Auth support: OAuth 2.0, API keys, Bearer
- OpenTelemetry telemetry built in
- Sampling (LLM-calls-LLM), resource templates, prompt management
- FastMCP proxy for mounting sub-servers
- Optional extras: `[anthropic]`, `[openai]`, `[gemini]`, `[apps]`, `[azure]`, `[tasks]`, `[code-mode]`

### Repo structure (notable)

```
fastmcp_slim/fastmcp/
  server/          — FastMCP, low_level, proxy, apps, auth, middleware, http
  client/          — Client, OAuth callback
  tools/           — tool registration + schema generation
  resources/       — resource templates
  prompts/         — prompt registry
  contrib/         — community extensions
fastmcp_remote/    — remote transport support
```

---

## 2. VECTOR Parity

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| `fastmcp` pip-installed | `.venv` site-packages | `fastmcp installed: 3.2.4` | DONE |
| FastMCP used in MCP server | `core/mcp_server.py:31` | `from fastmcp import FastMCP` with try/except | DONE |
| FastMCP instantiated | `core/mcp_server.py:82` | `mcp = FastMCP(...)` | DONE |
| Fallback when FastMCP absent | `core/mcp_server.py:38-42` | Falls back to `vectorcode.src.vc_mcp.MCPServer` | DONE |
| VECTOR MCP tools | `core/mcp_server.py` | 14 real tools + kanban(4) + claims(7) + guidance(3) + browser(3) + voice(2) + collections(3) | DONE |
| Transport modes | `core/mcp_server.py` | stdio (default) + SSE (`--transport sse --port 9000`) | DONE |
| Repo copy needed? | — | No. pip package 3.2.4 is newer than the local workspace source | SAFE TO DELETE |

**Key finding:** The local GitHub repo is a developer workspace (uses `uv-dynamic-versioning` from git tags; `pyproject.toml` has zero hardcoded version). VECTOR already imports and instantiates `FastMCP` from the pip-installed 3.2.4 package — the repo copy adds no value and is not referenced by path anywhere.

---

## 3. Frontend

No web UI in this repo. FastMCP is a Python SDK; the optional `[apps]` extra lets tools return interactive UI components rendered inside the conversation, but VECTOR's `core/mcp_server.py` does not currently use the `[apps]` extra.

**Gap:** If VECTOR ever wants tool outputs to render interactive forms or cards inside Claude Code, install `pip install fastmcp[apps]` and use `fastmcp.apps.App` inside a tool return. Not urgent — text-based tool returns are sufficient for the autonomous loop.

---

## 4. Verdict

**SAFE TO DELETE** — the GitHub repo folder is a developer source workspace for FastMCP itself. VECTOR consumes it as a pip dependency (`fastmcp==3.2.4`) which is already installed and confirmed working. The local repo is not pip-installed editably; it is dead weight.

Deleting `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\fastmcp-main` has zero runtime impact.

---

## 5. Gaps

| Gap | Priority | Action |
|-----|----------|--------|
| `fastmcp[apps]` not installed | Low | `pip install fastmcp[apps]` if interactive tool UIs are needed in future |
| `fastmcp[anthropic]` not installed | Low | Enables Claude sampling (LLM-inside-tool) — install if needed |
| MCP client outbound | Already built | `core/mcp/client.py` (MCPClient) handles outbound MCP consumption |
| No FastMCP version pin in requirements.txt | Medium | Pin `fastmcp>=3.2.4` to prevent silent downgrades |
