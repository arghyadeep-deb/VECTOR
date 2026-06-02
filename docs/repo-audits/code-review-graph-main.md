# code-review-graph-main Audit

## 1. Repo Reality

code-review-graph is a Python/MIT tool that parses a codebase into a structural knowledge graph using Tree-sitter (multi-language AST), stores it in SQLite, and exposes it via 30+ MCP tools so AI coding assistants (Claude Code, Cursor, Copilot, Codex, etc.) read only the minimal context they need for a review. Its headline claim is 38x–528x token reduction on real repositories. It supports incremental updates via git diff, watch mode, community/cluster detection via the Leiden algorithm, semantic+BM25 hybrid search, and cross-repo queries.

---

## 2. VECTOR Parity

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| `build_graph()` entrypoint | `districts/coding/code_review_graph/__init__.py` | `code_review_graph OK` — `from districts.coding.code_review_graph import build_graph` imports successfully | COVERED (adapter) |
| Impact radius query | `districts/coding/code_review_graph/__init__.py` → `query_impact()` | Wraps `code_review_graph.graph.CodeGraph.get_impact_radius()` | COVERED (adapter) |
| Large function finder | `districts/coding/code_review_graph/__init__.py` → `find_large_functions()` | Wraps upstream `tools.analysis_tools.find_large_functions` | COVERED (adapter) |
| Semantic code search | `districts/coding/code_review_graph/__init__.py` → `search_code()` | Wraps `code_review_graph.search.search_graph` | COVERED (adapter) |
| Graph-aware code review | `districts/coding/code_review_graph/__init__.py` → `review_changes()` | Wraps `tools.review.review_changes`; fallback to `query_impact` per file | COVERED (adapter) |
| Core graph store (SQLite + NetworkX) | **upstream package** `code_review_graph.graph` | VECTOR's adapter imports from the pip package — the SQLite/NetworkX engine lives in the upstream package, not reimplemented | UPSTREAM DEPENDENCY |

**Verification output (exact):**
```
code_review_graph OK
```

### Architecture clarification

VECTOR's `districts/coding/code_review_graph/` is a **thin adapter** (80 lines) that wraps the upstream `code-review-graph` pip package. It does NOT reimplement the graph engine. The upstream package must be installed (`pip install code-review-graph`) for the adapter to function — currently it degrades gracefully with `logger.warning("[CRG] code-review-graph not installed: pip install code-review-graph")`.

### What the upstream repo has beyond VECTOR's adapter

The upstream contains 35+ MCP tools not yet exposed through VECTOR's adapter:

| Upstream tool | VECTOR gap |
|--------------|------------|
| `build_or_update_graph` (incremental, git-diff-aware) | VECTOR calls this via `build_graph()` — covered |
| `get_architecture_overview` | NOT in VECTOR adapter |
| `get_bridge_nodes` (architectural connectors) | NOT in VECTOR adapter |
| `get_hub_nodes` (high-centrality nodes) | NOT in VECTOR adapter |
| `list_communities` / `get_community` (Leiden clustering) | NOT in VECTOR adapter |
| `list_flows` / `get_flow` (call flow traces) | NOT in VECTOR adapter |
| `generate_wiki` / `get_wiki_page` | NOT in VECTOR adapter |
| `get_knowledge_gaps` | NOT in VECTOR adapter |
| `semantic_search_nodes` (embedding-based) | NOT in VECTOR adapter |
| `cross_repo_search` | NOT in VECTOR adapter |
| `apply_refactor` | NOT in VECTOR adapter |
| `get_suggested_questions` | NOT in VECTOR adapter |
| `traverse_graph` | NOT in VECTOR adapter |
| Watch mode / daemon (`daemon.py`) | NOT wired into VECTOR's autonomous loop |
| MCP server (`main.py` via FastMCP) | NOT exposed in `core/mcp_server.py` |

---

## 3. Frontend

N/A — code-review-graph has no UI. It exposes MCP tools and a CLI.

---

## 4. Verdict

**INTEGRATE (expand adapter + wire MCP tools)**

The repo is already integrated as an adapter. The current adapter covers 5 of 35+ available tools. The upstream package is the right implementation — Tree-sitter AST parsing, Leiden community detection, and BM25+semantic hybrid search are non-trivial to reimplement and the package is MIT licensed.

Two integration actions:

1. **`pip install code-review-graph`** — activates all 5 adapter functions (currently failing silently)
2. **Expand `core/mcp_server.py`** — add 5-10 high-value MCP tools from the upstream (`architecture_overview`, `hub_nodes`, `bridge_nodes`, `list_flows`, `communities`) so VECTOR agents can query the code graph during reviews without writing Python

The upstream source repo can be deleted once the pip package is confirmed installed.

---

## 5. Gaps

| Gap | Priority | Notes |
|-----|----------|-------|
| `pip install code-review-graph` | HIGH | Without this, all 5 adapter functions log a warning and return `{"status": "not_installed"}`. Zero code changes needed — just install. |
| Architecture overview MCP tool | Medium | `get_architecture_overview_func` returns a token-efficient map of the entire codebase structure. Critical for ArchitectBot reviews. Add to `core/mcp_server.py`. |
| Community/cluster MCP tool | Medium | `list_communities` groups related code by Leiden clustering. Useful for `code_reviewer.py` to scope reviews to a community instead of scanning all files. |
| Watch mode in autonomous loop | Low | The upstream daemon watches for file changes and updates the graph incrementally. Could be launched as a background coroutine in `autonomous_loop.py` alongside `_sense_tick`. |
| Flow trace MCP tool | Low | `get_flow` traces call chains end-to-end. Directly useful for `bug_hunter.py` to map how a bug propagates. |
