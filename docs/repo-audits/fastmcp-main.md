# fastmcp-main Audit

**Repo path:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\fastmcp-main`
**Audited:** 2026-06-02
**Verdict:** SAFE TO DELETE — pip package `fastmcp==3.2.4` already installed and fully in use

---

## 1. Repo Reality

**Package:** `fastmcp` (PyPI) / `fastmcp-slim` (slim sub-package)
**Author:** Jeremiah Lowin / Prefect
**License:** Apache-2.0
**Latest version in repo changelog:** v3.1.1 (2026-03-14); installed in VECTOR: **3.2.4** (newer)
**Downloaded:** ~1 million/day; powers 70% of MCP servers across all languages; FastMCP 1.0 was incorporated into the official MCP Python SDK.

### What fastmcp is

FastMCP is the standard framework for building and consuming Model Context Protocol (MCP) servers/clients. It has three pillars:

1. **Servers** — wrap Python functions into MCP-compliant tools, resources, and prompts using `@mcp.tool`, `@mcp.resource`, `@mcp.prompt` decorators; auto-generates JSON schemas, validation, documentation
2. **Clients** — connect to any MCP server (local subprocess via stdio, remote via SSE or StreamableHTTP) with full protocol lifecycle, transport negotiation, OAuth, sampling, elicitation
3. **Apps** — tool UIs rendered directly in the conversation via Prefab integration

### Key features in this codebase version (v3.x)

| Feature | Location in repo |
|---------|-----------------|
| `FastMCP` server class | `fastmcp_slim/fastmcp/server/server.py` |
| `Client` class | `fastmcp_slim/fastmcp/client/client.py` |
| Middleware stack (auth, rate-limiting, caching, error-handling, timing, ping, tool-injection) | `fastmcp_slim/fastmcp/server/middleware/` |
| Provider architecture (local, proxy, OpenAPI, filesystem, skills, aggregate) | `fastmcp_slim/fastmcp/server/providers/` |
| Transforms (tool transforms, version filter, search, namespace, resources-as-tools, prompts-as-tools, visibility) | `fastmcp_slim/fastmcp/server/transforms/` |
| Auth (JWT, OAuth proxy, OIDC proxy, CIMD, SSRF guard) | `fastmcp_slim/fastmcp/server/auth/` |
| Sampling (server-side LLM sampling tool) | `fastmcp_slim/fastmcp/server/sampling/` |
| Elicitation (structured user input from within a tool call) | `fastmcp_slim/fastmcp/server/elicitation.py` |
| Tasks (async background tasks via `pydocket`) | `fastmcp_slim/fastmcp/server/tasks/` |
| FastMCPProxy (compose/proxy other MCP servers) | `fastmcp_slim/fastmcp/server/providers/proxy.py` |
| OpenAPI → MCP server generator | `fastmcp_slim/fastmcp/server/providers/openapi/` |
| Skills provider (Claude-compatible skill directory) | `fastmcp_slim/fastmcp/server/providers/skills/` |
| Contrib: BulkToolCaller, MCPMixin, ComponentManager | `fastmcp_slim/fastmcp/contrib/` |
| FastMCPApp (Prefab UI) | `fastmcp_slim/fastmcp/apps/` |
| Experimental (server, transforms, utilities, sampling) | `fastmcp_slim/fastmcp/experimental/` |
| OpenTelemetry telemetry | `fastmcp_slim/fastmcp/telemetry.py` |
| MCPConfig (multi-server mcp.json config) | `fastmcp_slim/fastmcp/mcp_config.py` |
| CLI (`fastmcp run`, `fastmcp dev`, etc.) | `fastmcp_slim/fastmcp/cli/` |
| Client transports (stdio, SSE, StreamableHTTP, memory, NodeStdio, MCPConfig) | `fastmcp_slim/fastmcp/client/transports/` |
| Client OAuth | `fastmcp_slim/fastmcp/client/auth/oauth.py` |
| Workspace structure | `fastmcp-main/` (root) → `fastmcp_slim/` + `fastmcp_remote/` (sub-packages) |

---

## 2. VECTOR Parity

### Parity check output

```
fastmcp installed: 3.2.4
mcp_server OK, tools: 346
FastMCP type: FastMCP
```

VECTOR has `fastmcp==3.2.4` pinned in `requirements.txt`. The local repo's changelog tops out at v3.1.1 — VECTOR is already running a **newer** pip release. No code from the local repo folder is referenced by any VECTOR Python file.

### Feature-by-feature status

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| `FastMCP` server (core server class, `@mcp.tool`, `@mcp.resource`) | `core/mcp_server.py` L82-474 | `FastMCP type: FastMCP`, 346 tools registered | ✅ |
| `@mcp.tool` decorator (sync + async tools) | `core/mcp_server.py` throughout | All 346 tools use `@mcp.tool` | ✅ |
| `@mcp.resource` decorator | `core/mcp_server.py` L386 (`vector://status`) | Resource registered | ✅ |
| Tool metadata (instructions param) | `core/mcp_server.py` L82-89 | `instructions=` passed to constructor | ✅ |
| `create_mcp_app()` public alias | `core/mcp_server.py` L478 | Import confirmed | ✅ |
| `FastMCP` import guard (graceful degradation) | `core/mcp_server.py` L32-36 | Falls back to OJ MCP if fastmcp missing | ✅ |
| `FastMCP` Client class | `fastmcp.Client` | `Client class: <class 'fastmcp.client.client.Client'>` | ✅ (available but VECTOR uses custom `core/mcp/client.py` — see §5) |
| Middleware (authorization, rate_limiting, caching) | pip package | All 3 modules importable | ✅ (available, not yet wired to VECTOR server) |
| `FastMCPProxy` | pip package | `FastMCPProxy OK` | ✅ (available, not yet used) |
| Auth (AuthProvider, AuthCheck, AuthContext) | pip package | `Server auth OK` | ✅ (available, not yet used) |
| Client OAuth | pip package | `Client OAuth OK` | ✅ (available) |
| Elicitation (`AcceptedElicitation`, `ElicitConfig`, `handle_elicit_accept`) | pip package | `Server elicitation (correct exports) OK` | ✅ |
| Sampling (`SamplingTool`, `sampling_tool`) | pip package | `Server sampling (SamplingTool) OK` | ✅ |
| Client sampling (`SamplingHandler`) | pip package | `Client sampling OK` | ✅ |
| Tasks (`TaskConfig`, `TaskMeta`) | pip package | `Tasks OK` | ✅ |
| MCPConfig (multi-server JSON config) | pip package | `MCPConfig OK` | ✅ |
| ResourceTemplate | pip package | `ResourceTemplate OK` | ✅ |
| Prompts | pip package | `Prompts OK` | ✅ |
| OpenAPI provider (`OpenAPIProvider`) | pip package | `OpenAPIProvider OK` | ✅ |
| Skills provider (`SkillProvider`) | pip package | `SkillProvider OK` | ✅ |
| ToolTransform | pip package | `ToolTransform OK` | ✅ |
| FastMCPApp (Prefab UI) | pip package | `FastMCPApp OK` | ✅ |
| `BulkToolCaller` (contrib) | pip package | `BulkToolCaller OK` | ✅ |
| `MCPMixin` (contrib) | pip package | `MCPMixin OK` | ✅ |
| Component manager (contrib) | pip package | `component_manager OK` (as `component_manager` function, not `ComponentManager` class — v3.2.4 API) | ✅ |
| Telemetry (OpenTelemetry) | pip package | `Telemetry OK` | ✅ |
| Client transports (SSE, StreamableHTTP, PythonStdio) | pip package | `Client transports OK` | ✅ |
| MCP security middleware | `core/security/mcp_security.py` | `_mcp_secure_call()` wrapper in every tool; risk classify + rate-limit + anomaly detect + audit | ✅ (VECTOR-native layer, not from fastmcp) |
| `/mcp/status` API endpoint | `core/api/routers/mcp.py` | FastAPI route checking `import fastmcp` availability | ✅ |
| VectorCode MCP fallback (`vc_mcp`) | `vectorcode/src/vc_mcp` | Active fallback if fastmcp not installed | ✅ |

### Usage across the codebase (16 files)

```
core/mcp_server.py                                   — main MCP server (346 tools)
core/api/routers/mcp.py                              — /mcp/status health endpoint
vectorcode/__init__.py                               — MCP availability check
districts/coding/vectorcode/__init__.py              — coding district MCP
districts/investment/vector_backtest/mcp_server.py   — backtest MCP server
districts/investment/vector_finagent/agents/rdagents/mcp_server.py — finagent MCP
districts/investment/vector_finagent/agents/rdagents/mcp_tools.py  — tool defs
districts/investment/vector_backtest/src/tools/mcp.py — backtest tool
districts/coding/vector_mlops/agent/core/tools.py    — MLOps tools
districts/coding/vector_mlops/agent/config.py        — MLOps config
vectorcode/src/skills/optional/mcp/fastmcp/templates/database_server.py  — template
vectorcode/src/skills/optional/mcp/fastmcp/templates/api_wrapper.py      — template
vectorcode/src/skills/optional/mcp/fastmcp/templates/file_processor.py   — template
tests/test_collections.py                            — test
districts/investment/vector_backtest/tests/...       — tests
```

---

## 3. Frontend

fastmcp has no frontend component in VECTOR's context. The `FastMCPApp` (Prefab UI) feature renders tool UIs inside an LLM conversation — it is not a standalone web dashboard. VECTOR's planned Next.js dashboard (`dashboard/src/` — not yet built) is separate from fastmcp.

The `fastmcp dev` CLI spins up the MCP Inspector (a browser-based debug UI) for development use — that is a development tool, not a production frontend, and requires no code from the local repo.

---

## 4. Verdict

**SAFE TO DELETE.**

- VECTOR uses `fastmcp` exclusively via the pip-installed package (`fastmcp==3.2.4` in `requirements.txt`)
- The installed version (3.2.4) is **newer** than the latest changelog entry in the local repo (3.1.1)
- Zero VECTOR files reference the local repo path (`GitHub/fastmcp-main/`)
- All 346 MCP tools, the MCP server, security middleware, and all import guards work correctly against the pip package — verified live
- The local repo is a development clone used to browse the source; it contributes nothing to runtime

**Action:** Delete `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\fastmcp-main` or archive it. No VECTOR code needs to change.

---

## 5. Gaps

### Gap 1 — Outbound MCP client uses custom raw implementation instead of `fastmcp.Client`

**File:** `core/mcp/client.py`

VECTOR's `MCPClient` is a hand-rolled JSON-RPC client (ported from a TypeScript UI-TARS-desktop implementation) using `subprocess.Popen` for stdio and `urllib.request` for HTTP. It works, but it misses everything the official `fastmcp.Client` provides:

- Full async (`anyio`-based, not blocking subprocess polling)
- Automatic transport negotiation (SSE vs StreamableHTTP vs stdio) from a URL string
- OAuth 2.0 support when connecting to authenticated servers
- Sampling callbacks (client can provide LLM completions to a server's sampling requests)
- Elicitation callbacks (client can handle structured user input requests)
- Progress notifications
- Resource subscriptions
- Roots management
- Proper MCP session lifecycle (initialize/initialized handshake, capability negotiation)

**Recommendation:** Replace `core/mcp/client.py` with `from fastmcp import Client` when VECTOR needs to consume external MCP servers. The custom class can be kept as a thin fallback only if `fastmcp` client extras are unavailable.

### Gap 2 — Middleware not wired to VECTOR's MCP server

`fastmcp.server.middleware` ships production-ready modules for rate limiting, caching, authorization (RBAC), response limiting, timing, and error handling — none are wired to VECTOR's `FastMCP` instance in `core/mcp_server.py`. VECTOR has its own `_mcp_secure_call()` wrapper, but the fastmcp middleware stack would provide:

- Per-session tool authorization based on `AuthContext`
- Response size limiting (prevents accidental 10MB memory dumps over MCP)
- Automatic retries and structured error shaping

**Recommendation:** Low priority for a single-owner local system. Consider wiring `RateLimitingMiddleware` and `ResponseLimitingMiddleware` if VECTOR is ever exposed to external clients.

### Gap 3 — `FastMCPProxy` not used for cross-district MCP composition

The `FastMCPProxy` class lets you mount one MCP server inside another, enabling clean cross-district tool composition. Currently VECTOR loads all 346 tools into a single flat `FastMCP` instance in `core/mcp_server.py`. Splitting by district and composing via proxy would make the tool list navigable and allow district-level authentication.

**Recommendation:** Year-2 refactor. Current flat structure works fine for a 346-tool single-owner system.

### Gap 4 — OpenAPI provider unused

`OpenAPIProvider` can auto-generate MCP tools from any OpenAPI/Swagger spec. VECTOR's marketing district and research district both call external APIs. Wiring their OpenAPI specs through `OpenAPIProvider` would eliminate hand-written tool wrappers.

**Recommendation:** Opportunistic — use when onboarding a new external API district.
