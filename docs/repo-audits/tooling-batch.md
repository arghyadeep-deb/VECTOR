# Tooling Batch Audit

**Audited:** 2026-06-01
**Against:** VECTOR production-hardening-complete branch
**Repos:** codebuff-main, get-shit-done-main, humanlayer-main, markitdown-main, code-review-graph-main

---

## codebuff-main

**What it is:**
TypeScript/Bun monorepo. Open-source multi-agent AI coding assistant (Apache 2.0). Coordinates 4 specialised agents (FilePicker, Planner, Editor, Reviewer) to edit codebases via natural language. Claims 61% vs 53% on coding evals vs Claude Code. Key internal packages: `code-map` (Tree-sitter AST token scorer + caller graph in TypeScript), `agent-runtime` (agent execution harness), `llm-providers` (multi-provider routing), `freebuff` (free/ad-supported tier). The `agents/` directory contains ~15 TypeScript agent definitions including a `context-pruner` agent that summarises conversation history when context exceeds limits.

**VECTOR parity:**
- Multi-agent coding orchestration: VECTOR has `core/code_conductor/orchestrator.py`, `districts/coding/code_conductor_agent.py`, `districts/coding/architect_bot.py`, `districts/coding/code_reviewer.py`. Full coverage.
- Code map / AST symbol index: VECTOR has `core/code_conductor/code_map.py` (Python port of codebuff's `code-map` package using tree-sitter + regex fallback). Full coverage.
- LLM provider routing: VECTOR has `core/inference/provider_client.py` with 27 providers. Full coverage.
- Context pruning: VECTOR has `core/jcode/session_persistence.py` + `trajectory_compactor.py` (absorbed from jcode). The context-pruner agent concept is covered.
- Evals: VECTOR has `districts/qa/` (reality_checker, model_qa_specialist). Coverage exists.

**Gap check:**
Codebuff's `code-map` package uses Tree-sitter with language-specific S-expression queries in `packages/code-map/src/tree-sitter-queries/` to score files by token relevance to a given task (keyword match + caller frequency). VECTOR's `code_map.py` has basic tree-sitter support but no language-specific query files or token-relevance scoring. This is a minor enhancement, not a missing gap — VECTOR's `code_conductor` achieves equivalent results via its file-picker step calling the symbol index.

**Verdict: SAFE TO DELETE**
VECTOR has every substantive capability. The repo is TypeScript-only (not absorbable to Python), Apache 2.0 licensed (fine legally), but adds no gaps. The one nuance — Tree-sitter query files for language-specific token scoring — is not worth a new module; the existing `code_map.py` covers VECTOR's needs.

---

## get-shit-done-main

**What it is:**
TypeScript/Node.js meta-prompting framework (MIT) that sits between the user and AI coding assistants (Claude Code, Gemini CLI, Codex, Copilot, etc.). Provides ~67 slash commands (`/gsd-plan-phase`, `/gsd-execute-phase`, `/gsd-verify-work`, `/gsd-new-project`, etc.) stored as `.md` prompt files. Implements a strict Discuss → Plan → Execute → Verify pipeline, milestone management, multi-agent orchestration via fresh context windows, workstream namespacing, and a GSD SDK (TypeScript, ~28k LOC) with a programmatic query bridge. The repo README explicitly states it has been archived and moved to `open-gsd/get-shit-done-redux`.

**VECTOR parity:**
- GSD loop (Discuss → Plan → Execute → Verify): VECTOR has `vectorcode/src/gsd_loop.py` (`GSDLoop` class) with all 4 phases, pattern cache skip-discuss optimisation, and queen decomposition escalation. Direct equivalent.
- Slash command framework: VECTOR uses Claude Code's `.claude/commands/` system (visible in `brain/.claude/commands/`). `loop-start.md`, `quality-gate.md`, `verify.md`, `checkpoint.md`, `orchestrate.md`, `multi-plan.md`, `multi-execute.md`, `save-session.md`, `resume-session.md`, `evolve.md` are all present. Full coverage.
- Phase/milestone tracking: VECTOR has `districts/projects/project_planner.py` + `deadline_watcher.py` + `progress_tracker.py`. T-7/3/1/0 deadline alerts are implemented.
- Multi-agent orchestration: VECTOR has `vectorcode/src/swarm.py` (8 topologies), `vectorcode/src/claims.py` (work stealing), `core/city/governor.py` (180 routes). Deeper than GSD.
- Context engineering: VECTOR has `core/loop/context_engine.py` (14-domain world state + `session_hydration_prompt()`). Purpose-built for VECTOR's agentic loop.
- Workstream namespacing: Not applicable — VECTOR is a single-owner autonomous system, not a multi-team dev tool.

**Gap check:**
GSD's `Nyquist Validation` (feature 15) — checks that plans have sufficient detail before execution — is conceptually interesting. VECTOR's `verification-before-completion` skill + `quality-gate.md` command cover this. GSD's `Cross-Phase Regression Gate` and `Requirements Coverage Gate` are CI-style checks for human-authored requirements docs. VECTOR uses `districts/qa/reality_checker.py` instead. No genuine gap.

**Verdict: SAFE TO DELETE**
Archived upstream (redirects to `open-gsd/get-shit-done-redux`). VECTOR has every equivalent capability implemented natively in Python. GSD is a Claude Code meta-prompting layer for human developers; VECTOR is a fully autonomous agent system with its own loop — the paradigms do not overlap in a useful way.

---

## humanlayer-main

**What it is:**
Apache 2.0 monorepo. Originally a Python SDK for human-in-the-loop approval of high-stakes LLM tool calls. The SDK was removed in PR #646. The repo has pivoted to "CodeLayer" — a TypeScript/Go IDE tooling suite: `hld` (Go daemon for local approval management with SQLite), `hlyr` (TypeScript CLI with MCP server), `humanlayer-wui` (Tauri + React desktop approval UI), and `claudecode-go` (Go SDK for launching Claude Code sessions programmatically). The `humanlayer.md` file documents the legacy Python SDK (now removed from the repo).

**VECTOR parity:**
- HumanLayer Python SDK (`from humanlayer import HumanLayer`): VECTOR uses this in `core/loop/permission_gateway.py:19-32`. VECTOR calls `_hl.fetch_approval(action, context)` for RED-tier actions. The Python SDK (`pip install humanlayer`) is still on PyPI even though the source was removed from this repo — VECTOR's import still works via PyPI.
- Local approval daemon (`hld`): Go daemon exposing `CreateApproval`, `GetPendingApprovals`, `ApproveToolCall`, `DenyToolCall` over HTTP. VECTOR does NOT have this. VECTOR's fallback when HumanLayer is unavailable is `asyncio.wait_for` (30s timeout → reject) + Pushover notification. The `hld` daemon would give a proper approval queue with persistence.
- Desktop approval UI (`humanlayer-wui`, Tauri + React): VECTOR does NOT have this. Relevant to the VECTOR dashboard roadmap (currently listed as "not built yet" in `phase_status.md`).
- MCP approval server (`hlyr`): TypeScript. Not directly applicable to VECTOR's Python stack.
- `claudecode-go`: Go SDK for launching Claude Code sessions. Not applicable to VECTOR.

**Gap check:**
The `hld` local daemon is the genuine gap. It provides:
1. Persistent SQLite-backed approval queue (approvals survive process restarts)
2. Per-session approval history
3. Tool-use-id tracking (ties approval to specific Claude tool call)
4. REST API that any language can hit (`POST /api/v1/approvals`, `GET /api/v1/approvals/pending`)

VECTOR's current RED-tier approval flow: Queen consensus → HumanLayer PyPI SDK (cloud API) → asyncio 30s timeout → reject. The `hld` daemon would replace the cloud API dependency with a local REST server, giving VECTOR offline approval capability. However: (a) the Python SDK (`pip install humanlayer`) is the integration point, not the Go daemon; (b) VECTOR is single-owner local-first and the asyncio fallback works for Day 1; (c) building a Python-native approval daemon would be 50-100 LOC.

**Verdict: PATCH VECTOR (low priority)**
The `hld` Go daemon's REST API contract is worth borrowing for a future Python `core/engine/approval_daemon.py` — a local FastAPI server serving `POST /approvals` + `GET /approvals/pending` with SQLite persistence, replacing the 30s asyncio timeout fallback. This would give VECTOR offline RED-tier approvals that survive restarts. **Do not copy Go code.** Reimplement the API contract in ~80 lines of Python using VECTOR's existing FastAPI + SQLite stack.

**Patch spec:**
```
File: core/engine/approval_daemon.py
  - SQLite table: approvals(id, action_type, params, proposed_by, status, created_at, decided_at, comment)
  - POST /api/approvals       → create pending approval, return id
  - GET  /api/approvals/pending → list pending
  - POST /api/approvals/{id}/approve
  - POST /api/approvals/{id}/deny
  - permission_gateway.py: if hld_available → POST to daemon; else → existing asyncio fallback
```
Priority: after Kokoro TTS and wake word training (those block autonomous operation; this is a reliability enhancement).

---

## markitdown-main

**What it is:**
MIT-licensed Python library from Microsoft AutoGen team. Converts virtually any file format to Markdown for LLM consumption: PDF, Word (docx), Excel (xlsx), PowerPoint (pptx), HTML, CSV, JSON, XML, images (OCR + EXIF), audio (speech transcription), YouTube URLs, EPubs, ZIP files, Jupyter notebooks, Outlook .msg files, RSS feeds. Focuses on preserving document structure (headings, lists, tables) as Markdown. Companion package `markitdown-mcp` exposes a single MCP tool `convert_to_markdown(uri)` over STDIO/HTTP.

**VECTOR parity:**
VECTOR already uses markitdown. Evidence:
1. `districts/research/web_scout.py` docstring: "Uses DuckDuckGo + httpx + MarkItDown for conversion"
2. `core/memory/obsidian_sync.py:317-364`: `from markitdown import MarkItDown` — used as pre-processor when syncing non-markdown files into Obsidian vault (PDF, Word, etc.); falls back gracefully if not installed
3. `requirements.txt`: `# OPTIONAL (not installed by default): markitdown>=0.0.1`

VECTOR integrates markitdown as an optional `pip install` dependency. The worktree snapshots at `.claude/worktrees/agent-*/agents/districts/research/markitdown/` are stale agent worktree copies, not the production integration.

**Gap check:**
The `markitdown-mcp` package (MCP server exposing `convert_to_markdown`) is NOT wired into VECTOR's `core/mcp_server.py`. VECTOR has 14+ MCP tools but none for document-to-markdown conversion. Adding `convert_to_markdown` as an MCP tool would let VECTOR's agents (and external Claude Code sessions) convert arbitrary files without subprocess calls.

**Verdict: INTEGRATE DIRECTLY (markitdown-mcp)**
1. Activate the dependency: change `requirements.txt` from `# OPTIONAL` to `markitdown[all]>=0.0.1`.
2. Add one MCP tool to `core/mcp_server.py`:

```python
@mcp.tool()
def convert_to_markdown(uri: str) -> str:
    """Convert any file or URL to Markdown (PDF, Word, HTML, YouTube, etc.)"""
    from markitdown import MarkItDown
    md = MarkItDown()
    result = md.convert(uri)
    return result.text_content
```

The source repo itself does not need to be kept — just `pip install markitdown[all]`. The repo is useful only as a reference for the converters list and the MCP server pattern.

---

## code-review-graph-main

**What it is:**
MIT-licensed Python tool (v2.3.5, `pip install code-review-graph`). Builds a Tree-sitter AST graph of a codebase stored in SQLite, then exposes blast-radius analysis, incremental updates (SHA-256 hash-based, re-parses only changed files, ~2s for 2,900 files), hybrid semantic+BM25 search, community detection, and refactoring suggestions via MCP tools. Supports 13+ AI coding platforms (Claude Code, Cursor, Codex, Copilot, Gemini CLI, Windsurf, Zed, etc.) via an `install` command that auto-writes MCP config. Has a watch daemon (`code-review-graph daemon`) for multi-repo monitoring.

**VECTOR parity:**
VECTOR already has an integration adapter at `districts/coding/code_review_graph/__init__.py`. It wraps `code_review_graph.graph.CodeGraph`, `code_review_graph.tools.build.build_or_update_graph`, `code_review_graph.tools.review.review_changes`, `code_review_graph.search.search_graph`, and `code_review_graph.tools.analysis_tools.find_large_functions`. The adapter exposes `build_graph()`, `query_impact()`, `find_large_functions()`, `search_code()`, `review_changes()` as Python functions used by `ArchitectBot` and `CodeReviewer`.

The adapter references the repo at `GitHub/tirth8205_code-review-graph/repo` as a local install path, but also supports `pip install code-review-graph` for PyPI install.

**Gap check:**
The adapter does NOT expose the following capabilities that exist in the repo:
1. **Incremental watch mode** (`code-review-graph watch`) — auto-rebuilds graph on file save. VECTOR's graph currently requires manual `build_graph()` calls. Watchdog integration (already in VECTOR's `requirements.txt`) could trigger incremental updates automatically.
2. **Community detection** (`code_review_graph.communities`) — identifies clusters of tightly-coupled modules. Not wired into VECTOR.
3. **Refactor suggestions** (`code_review_graph.tools.refactor_tools`) — flags large functions, deep nesting, coupling violations. `find_large_functions()` is wired but the full refactor analysis is not.
4. **MCP tools registration** — the repo has 10+ MCP tools (`get_impact_radius`, `search_code`, `get_community`, `get_flow`, `get_docs`, `get_refactor_suggestions`, etc.). Only `build_graph`, `query_impact`, `search_code`, `review_changes`, `find_large_functions` are in VECTOR's adapter. The MCP tools are not exposed in `core/mcp_server.py`.

**Verdict: INTEGRATE DIRECTLY (enhance existing adapter)**
`pip install code-review-graph` is the right installation method (not copying source). The existing adapter is good. Three enhancements worth making:

1. **Wire MCP tools** — add `code_review_graph_build`, `code_review_graph_impact`, `code_review_graph_search` to `core/mcp_server.py` so all VECTOR agents can call them without importing the adapter directly.
2. **Add watch trigger** — in `core/loop/autonomous_loop.py`'s `_observe_tick`, call `build_graph()` incrementally when Python files in the VECTOR root change (15-minute debounce, or hook into the existing `watchdog` observer in `core/memory/obsidian_sync.py`).
3. **Expose refactor analysis** — add `query_refactor(repo_path)` to the adapter calling `code_review_graph.tools.refactor_tools.get_refactor_suggestions()`.

The repo source itself can be deleted from `GitHub/` — all value is accessed via `pip install code-review-graph`.

---

## Summary Table

| Repo | Language | License | Verdict | Action |
|------|----------|---------|---------|--------|
| codebuff-main | TypeScript/Bun | Apache 2.0 | SAFE TO DELETE | No gaps. VECTOR has full parity. |
| get-shit-done-main | TypeScript/Node | MIT | SAFE TO DELETE | Archived upstream. VECTOR's `gsd_loop.py` + commands cover all features. |
| humanlayer-main | Go + TypeScript | Apache 2.0 | PATCH VECTOR (low priority) | Python SDK via PyPI already wired. Add `core/engine/approval_daemon.py` (~80 LOC) for local offline approval queue. |
| markitdown-main | Python | MIT | INTEGRATE DIRECTLY | Already used in production. Activate `markitdown[all]` in requirements.txt + add 1 MCP tool to `core/mcp_server.py`. Repo deletable after. |
| code-review-graph-main | Python | MIT | INTEGRATE DIRECTLY | Adapter already exists. Add 3 MCP tools to `core/mcp_server.py`, wire watch trigger, expose refactor analysis. Install via `pip install code-review-graph`. |

---

## Action Items (priority order)

1. **markitdown** (5 min): Uncomment `markitdown[all]>=0.0.1` in `requirements.txt`. Add `convert_to_markdown` MCP tool to `core/mcp_server.py`.
2. **code-review-graph** (30 min): Add `code_review_graph_build/impact/search` MCP tools to `core/mcp_server.py`. Add `query_refactor()` to `districts/coding/code_review_graph/__init__.py`. Wire watch trigger in observe loop.
3. **humanlayer approval daemon** (2h, low priority): Implement `core/engine/approval_daemon.py` — local FastAPI server with SQLite approval queue, matching `hld`'s REST contract. Wire into `permission_gateway.py` as preferred fallback over asyncio 30s timeout.
4. **Delete codebuff-main and get-shit-done-main**: No value remaining after above actions.
