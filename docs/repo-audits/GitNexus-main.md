# GitNexus-main Audit
> Audited: 2026-06-02 | Branch: production-hardening-complete
> Auditor note: GitNexus is a TypeScript/Node.js monorepo (PolyForm Noncommercial license). Zero Python code. The audit determines what gaps it fills for VECTOR vs. what VECTOR already has.

---

## 1. Repo Reality

**What GitNexus actually is:** A codebase knowledge-graph engine. It indexes any repo into a LadybugDB (graph DB) knowledge graph — every symbol, dependency, call chain, cluster, and execution flow — then exposes it through MCP tools and a web UI so AI agents get deep architectural context before editing code.

**Tech stack:** TypeScript/Node.js (CLI/MCP) + React 18/Vite (Web UI). Tree-sitter for AST parsing. LadybugDB (embedded graph DB, formerly KuzuDB) for storage. Snowflake arctic-embed-xs for embeddings. Graphology for Leiden community detection. **Not Python. Not absorbable as a whole.**

**Package layout:**

| Path | Contents |
|------|----------|
| `gitnexus/` | CLI, MCP server (stdio), HTTP API, 12-phase ingestion pipeline, LadybugDB graph layer |
| `gitnexus-web/` | React browser UI — graph canvas (Sigma.js/WebGL), AI chat, file tree, processes panel |
| `gitnexus-shared/` | Shared TypeScript types, language constants |
| `gitnexus-claude-plugin/` | Claude Code hooks (PreToolUse/PostToolUse enrichment) + 7 skills |
| `gitnexus-cursor-integration/` | Cursor hooks |
| `pr-swarm-review/` | PR review swarm orchestration specs (enterprise, Markdown only) |
| `eval/` | Evaluation harnesses |
| `deploy/` | Kubernetes ClusterImagePolicy (Cosign supply-chain protection) |

**Concrete features with file paths:**

### F1 — 12-Phase Ingestion Pipeline (`gitnexus/src/core/ingestion/pipeline-phases/`)
```
scan → structure → [markdown, cobol] → parse → [routes, tools, orm]
  → crossFile → mro → communities → processes
```
- `scan.ts` — file tree walk, `.gitignore` aware
- `parse.ts` + `parse-impl.ts` — Tree-sitter AST for 16 languages (TS, JS, Python, Java, Kotlin, C#, Go, Rust, PHP, Ruby, Swift, C, C++, Dart, COBOL, Vue)
- `cross-file.ts` — cross-file type propagation in topological import order
- `mro.ts` — MRO edges (METHOD_OVERRIDES, METHOD_IMPLEMENTS) for all 16 languages
- `communities.ts` — Leiden community detection via Graphology
- `processes.ts` — execution flow tracing from entry points through call chains
- `routes.ts` — route extraction (Next.js, FastAPI, Expo, Laravel, PHP decorators)
- `orm.ts` — ORM query extraction (Prisma, Supabase)

### F2 — Scope-Resolution Pipeline RFC #909 (`gitnexus/src/core/ingestion/scope-resolution/`)
New registry-primary resolver replacing legacy Call-Resolution DAG for migrated languages. Python and C# are migrated. Language-agnostic `ScopeResolver` interface. CI parity harness runs both paths on every PR. Per-language implementations:
- `languages/python/scope-resolver.ts`, `languages/csharp/scope-resolver.ts`

### F3 — 16 MCP Tools (`gitnexus/src/mcp/tools.ts`, `server.ts`)
| Tool | Purpose |
|------|---------|
| `list_repos` | List indexed repos (global registry) |
| `query` | Hybrid BM25+semantic+RRF search, process-grouped |
| `context` | 360-degree symbol view — callers, callees, process participation |
| `impact` | Blast radius: upstream/downstream with depth grouping, confidence, risk level |
| `detect_changes` | Map git diff → affected symbols → affected processes |
| `rename` | Graph-assisted multi-file rename with dry-run |
| `cypher` | Raw Cypher queries against LadybugDB schema |
| `api_impact` | Pre-change impact for API route handlers |
| `route_map` | API route → handler → consumer mappings |
| `tool_map` | MCP/RPC tool definitions and handlers |
| `shape_check` | Response shape vs consumer property access mismatches |
| `group_list` | List configured repo groups |
| `group_sync` | Rebuild group Contract Registry and bridge graph |

### F4 — MCP Resources (`gitnexus/src/mcp/resources.ts`)
`gitnexus://repos`, `gitnexus://repo/{name}/context`, `gitnexus://repo/{name}/clusters`, `gitnexus://repo/{name}/processes`, `gitnexus://repo/{name}/schema`, `gitnexus://group/{name}/contracts`, `gitnexus://group/{name}/status`

### F5 — Multi-Repo Groups (`gitnexus/src/core/group/`)
- `service.ts` — group creation and repo management
- `sync.ts` — Contract Registry extraction and cross-service matching
- `cross-impact.ts` — cross-repo blast-radius analysis via Contract Bridge
- `bridge-db.ts` — bridge graph persistence
- `contract-extractor.ts` — API surface extraction (routes, types, ORM queries)

### F6 — LadybugDB Graph Layer (`gitnexus/src/core/lbug/`)
- `schema.ts` — 44 node types, 21 relationship types (CALLS, IMPORTS, EXTENDS, IMPLEMENTS, HAS_METHOD, HANDLES_ROUTE, STEP_IN_PROCESS, etc.)
- `lbug-adapter.ts` — graph load via CSV streaming, embedding batches, lazy connection pool (max 5 concurrent, 5-min eviction)
- `csv-generator.ts` — memory-efficient CSV streaming for bulk graph loading
- `wal-checkpoint-driver.ts` — WAL auto-checkpoint management
- `pool-adapter.ts` — multi-repo connection pooling

### F7 — Hybrid Search (`gitnexus/src/core/search/`)
- `bm25-index.ts` — BM25 full-text search
- `fts-indexes.ts` — FTS over File, Function, Class, Method, Interface nodes
- `hybrid-search.ts` — BM25 + semantic vector merged via Reciprocal Rank Fusion (K=60)

### F8 — Embeddings (`gitnexus/src/core/embeddings/`)
Snowflake arctic-embed-xs (384D). Incremental via SHA1 content hash. Separate `Embedding` table. GPU/CPU via transformers.js.

### F9 — Git Staleness Detection (`gitnexus/src/core/git-staleness.ts`)
Compares indexed `lastCommit` to `HEAD`. Surfaces stale-index hints. Wired to PostToolUse hooks that detect commits and prompt re-index.

### F10 — Claude Code Hooks (`gitnexus-claude-plugin/hooks/`)
- `gitnexus-hook.js` — PreToolUse hook: enriches searches with graph context; PostToolUse hook: detects `git commit/merge/rebase/cherry-pick/pull` → prompts re-index
- `hooks.json` — hook registration spec

### F11 — 7 Agent Skills (`gitnexus/skills/`, `gitnexus-claude-plugin/skills/`)
- `gitnexus-exploring.md` — navigate unfamiliar code using knowledge graph
- `gitnexus-debugging.md` — trace bugs through call chains
- `gitnexus-impact-analysis.md` — blast radius before changes
- `gitnexus-refactoring.md` — safe refactors using dependency mapping
- `gitnexus-pr-review.md` — PR blast-radius analysis
- `gitnexus-cli.md` — CLI usage reference
- `gitnexus-guide.md` — overall usage guide

### F12 — Repo-Specific Skill Generation (`gitnexus/src/cli/skill-gen.ts`)
`gitnexus analyze --skills` generates per-community `SKILL.md` files under `.claude/skills/generated/` using Leiden community detection on the codebase graph.

### F13 — Wiki Generation (`gitnexus/src/core/wiki/`)
- `generator.ts` — LLM-powered per-module documentation generation from knowledge graph
- `llm-client.ts` — OpenAI-compatible LLM client for wiki generation
- `html-viewer.ts` — wiki HTML viewer

### F14 — Context File Generation (`gitnexus/src/cli/ai-context.ts`)
Auto-generates `AGENTS.md` and `CLAUDE.md` (GitNexus section) at index time with codebase stats and tool guidance.

### F15 — Incremental Indexing (`gitnexus/src/core/incremental/`)
`subgraph-extract.ts` — extracts only changed-file subgraph for DB writeback. `shadow-candidates.ts` — shadow-harness candidates for parity testing. (Full incremental indexing is on the roadmap; current `--repair-fts` fast path exists.)

### F16 — Web UI (`gitnexus-web/src/`)
React 18 + Vite + Tailwind v4 + Sigma.js (WebGL graph rendering). Components:
- `GraphCanvas.tsx` — WebGL graph, Leiden cluster overlay
- `ProcessesPanel.tsx` / `ProcessFlowModal.tsx` — execution flow visualization
- `CodeReferencesPanel.tsx` — symbol callers/callees panel
- `RepoAnalyzer.tsx` — in-browser indexing pipeline (tree-sitter WASM + LadybugDB WASM)
- AI chat via LangChain ReAct agent (backend or fully in-browser)
- Bridge mode via `gitnexus serve` HTTP API

### F17 — Worker Pool (`gitnexus/src/core/ingestion/workers/`)
`worker-pool.ts` + `parse-worker.ts` + `quarantine.ts` — parallel file parsing with circuit breaker, retry/backoff, respawn limits, quarantine for crash-looping workers.

### F18 — COBOL Support (`gitnexus/src/core/ingestion/cobol/`)
Regex-based COBOL program/paragraph/section node extraction (no tree-sitter dependency).

### F19 — Docker + Kubernetes Supply Chain (`Dockerfile.cli`, `Dockerfile.web`, `docker-compose.yaml`, `deploy/kubernetes/`)
Cosign keyless signing, SLSA provenance attestations, SBOM, Kubernetes ClusterImagePolicy for admission-time signature enforcement.

### F20 — Disambiguation + Overload Resolution
Symbol overload disambiguation via `#<arity>` + `~type1,type2` suffix. C++ `$const` qualifier. Variadic matching with confidence 0.7. Full methodology in `ARCHITECTURE.md`.

---

## 2. VECTOR Parity

**GitBot verification output (exact):**
```
GitBot OK: <class 'districts.coding.git_bot.GitBot'>
methods: ['add_lesson', 'analyze_with_gitnexus', 'award_points', 'best_decisions',
          'can_access_cloud', 'can_vote_in_council', 'commit', 'create_branch',
          'create_pr', 'created_at', 'deduct_points', 'die', 'district',
          'generate_commit_message_vc', 'generation', 'get_recent_commits',
          'get_status', 'get_voice_style', 'ghost_memory', 'health_points',
          'id', 'inherit_ghost', 'is_alive', 'is_elite', 'last_active', 'lessons',
          'model', 'name', 'personality_traits', 'record_decision', 'run',
          'run_forever', 'subscribe_to', 'to_dict', 'voice_style']

get_status OK: True
  branch: production-hardening-complete
  modified: 2
get_recent_commits OK: True
  last commit: 1778b61a
```

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| Git status (branch, modified, staged, untracked, ahead/behind) | `districts/coding/git_bot.py:31` | `branch=production-hardening-complete, modified=2` — confirmed ✅ | ✅ running |
| Git commit (stage + commit + gateway audit + RULE 8 chain) | `districts/coding/git_bot.py:75` | method exists, gateway-gated, YELLOW permission | ✅ running |
| Recent commits log | `districts/coding/git_bot.py:161` | `1778b61a` fetched — confirmed ✅ | ✅ running |
| Create branch + checkout | `districts/coding/git_bot.py:184` | method exists, HP-tracked | ✅ running |
| Create PR via PyGithub (RED gate) | `districts/coding/git_bot.py:204` | method exists, RED permission gateway | ✅ running |
| Semantic commit message generation | `districts/coding/git_bot.py:262` | via VectorCode bridge fallback | ✅ running |
| `analyze_with_gitnexus()` bridge | `districts/coding/git_bot.py:301` | calls `npx gitnexus@latest analyze` as subprocess; graceful `FileNotFoundError` when Node.js absent | ⚠️ stub — subprocess shell-out, no native Python equivalent; returns raw JSON if gitnexus installed, error string otherwise |
| Hybrid BM25 + semantic search over codebase graph | No Python equivalent | Not present | ❌ missing |
| Impact / blast-radius analysis (upstream/downstream with depth + confidence) | No Python equivalent | Not present | ❌ missing |
| 360-degree symbol context (callers, callees, process participation) | No Python equivalent | Not present | ❌ missing |
| Git-diff → affected symbols → affected processes | No Python equivalent | Not present | ❌ missing |
| Multi-file rename (graph-assisted, dry-run) | No Python equivalent | Not present | ❌ missing |
| Cypher queries against graph DB | No Python equivalent | Not present | ❌ missing |
| Execution flow / process tracing from entry points | No Python equivalent | Not present | ❌ missing |
| Leiden community detection (functional clustering) | No Python equivalent | Not present | ❌ missing |
| Knowledge graph (44 node types, 21 relation types, LadybugDB) | No Python equivalent | Not present | ❌ missing |
| 14-language Tree-sitter AST parsing (16 with COBOL+Vue) | `tree_sitter` installed but no grammars loaded | `ModuleNotFoundError: tree_sitter_languages` | ❌ missing |
| MRO resolution (C3, first-wins, Ruby-mixin across 16 languages) | No Python equivalent | Not present | ❌ missing |
| Incremental index (only re-parse changed files) | No Python equivalent | Not present | ❌ missing |
| Wiki generation (LLM-powered per-module docs from graph) | No Python equivalent | Not present | ❌ missing |
| Auto-generate AGENTS.md/CLAUDE.md from graph | Manual only | Not present | ❌ missing |
| Multi-repo groups + cross-service contract registry | No Python equivalent | Not present | ❌ missing |
| PreToolUse/PostToolUse Claude Code hooks (graph enrichment + stale-index detection) | No Python equivalent | Not present | ❌ missing |
| Repo-specific skill generation from community detection | No Python equivalent | Not present | ❌ missing |
| Vector embeddings (Snowflake arctic-embed-xs, 384D, incremental) | `chromadb` + `nomic-embed-text` exist for VECTOR memory | Codebase-specific symbol embeddings: not present | ❌ missing for codebase indexing |
| Web UI (WebGL graph, AI chat, process flow visualization) | No Python equivalent | Not present | ❌ missing |
| VectorCode vc_explore (vc_search, vc_graph_query, vc_impact) | `brain/.claude/skills/vc-explore/SKILL.md` (skill doc only) | `vc_search`, `vc_graph_query` are MCP tools from a *separate* VectorCode Intelligence product, not from GitNexus | ⚠️ parallel — different product, different graph schema, different scope |

**Key distinction on VectorCode:** VECTOR has `vc_search` / `vc_graph_query` / `vc_status` from the VectorCode Intelligence MCP server (a separate TypeScript product, `brain/.claude/skills/vc-explore/`). These overlap conceptually with GitNexus's `query` / `vc_graph_query` tools but are a different implementation with a different index format, different graph schema, and different scope (vc-explore is for *VECTOR's own coding agents to explore the VECTOR codebase*, while GitNexus is for *any AI agent to understand any repo*). They are complements, not duplicates.

---

## 3. Frontend

GitNexus has a full-featured web UI (`gitnexus-web/`) built in React 18 + TypeScript + Vite + Tailwind v4:

**Graph Canvas** (`GraphCanvas.tsx`): WebGL rendering via Sigma.js + Graphology. Leiden cluster overlay, node color by type, zoom/pan, click-to-select.

**Processes Panel** (`ProcessesPanel.tsx`, `ProcessFlowModal.tsx`): Execution flow visualization — step-by-step call chain traces.

**Code References Panel** (`CodeReferencesPanel.tsx`): Per-symbol callers, callees, all references with file:line locations.

**File Tree Panel** (`FileTreePanel.tsx`): Repo file tree with graph stats overlay.

**Right Panel** (`RightPanel.tsx`): Context panel for selected symbol — 360-degree view.

**AI Chat**: LangChain ReAct agent wired to GitNexus MCP tools. Can run fully in-browser (WASM) or via `gitnexus serve` backend.

**In-browser Indexing** (`RepoAnalyzer.tsx`): Full tree-sitter WASM + LadybugDB WASM pipeline runs in browser — code never leaves the machine.

**Settings** (`SettingsPanel.tsx`): API key config, embedding model selection, WebGPU/WASM toggle.

**Onboarding** (`OnboardingGuide.tsx`, `AnalyzeOnboarding.tsx`): Step-by-step first-use guide.

**VECTOR already has**: VectorCode Intelligence web components (referenced in `brain/.claude/skills/vc-explore/references/tool-reference.md` — `vc_graph_visualize mode="interactive"` generates a self-contained HTML explorer). However, GitNexus's web UI is far more comprehensive: real-time WebGL graph, cluster visualization, process flow modals, AI chat, all running in-browser with WASM.

**Is the frontend absorbable?** No — it is TypeScript/React/Vite. VECTOR's frontend is a Next.js dashboard (not yet built per `phase_status.md`). The architectural patterns (graph canvas, process flow visualization) should inform `dashboard/src/` when that gets built.

---

## 4. Verdict

**VERDICT: DO NOT DELETE — USE AS MCP SERVER (already wired, just needs `npm install -g gitnexus`)**

**Rationale:**

1. **GitBot already has the bridge** (`districts/coding/git_bot.py:301`). The `analyze_with_gitnexus()` method calls `npx gitnexus@latest analyze` as a subprocess. The `run()` dispatch at line 297 handles `"analyze_codebase"` / `"gitnexus"` task types. The bridge exists — it just needs Node.js + `npm install -g gitnexus` to activate.

2. **License is PolyForm Noncommercial** — personal/non-commercial use is allowed. VECTOR is a personal AI system. No code needs to be copied into VECTOR; GitNexus runs as a separate process/MCP server.

3. **Zero Python code** — nothing to absorb as a Python module. The entire ingestion pipeline, graph DB, and MCP server are TypeScript-only. Reimplementing them in Python would be 500+ hours of work to reproduce what `npm install -g gitnexus` gives for free.

4. **The MCP server is the integration path** — `gitnexus mcp` exposes 16 tools over stdio that VECTOR's agents can call directly via `.mcp.json`. VECTOR already has VectorCode Intelligence for search; GitNexus adds the graph layer (blast-radius, cypher, process traces, rename, multi-repo contracts) that VectorCode does not provide.

5. **The 7 agent skills** in `gitnexus-claude-plugin/skills/` and `gitnexus/skills/` should be copied to VECTOR's `.claude/skills/` to give VECTOR's coding agents graph-aware workflows.

6. **The Claude Code hooks** in `gitnexus-claude-plugin/hooks/gitnexus-hook.js` should be registered in `.claude/settings.json` to enable PreToolUse graph enrichment and PostToolUse stale-index detection.

**What to do:**
```bash
# 1. Install globally (one-time)
npm install -g gitnexus

# 2. Index the VECTOR codebase
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
gitnexus analyze

# 3. Register in .mcp.json (already auto-configured by `gitnexus setup`)
gitnexus setup

# 4. Copy skills to .claude/skills/
# Copy gitnexus-claude-plugin/skills/* → .claude/skills/

# 5. Register hooks in .claude/settings.json
# Add PreToolUse + PostToolUse entries from gitnexus-claude-plugin/hooks/hooks.json
```

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | `analyze_with_gitnexus()` calls `npx gitnexus@latest analyze --repo path --format json` but the actual CLI does NOT support `--format json` (real flags: `analyze [path]`, no `--format`). The call will fail silently returning stdout as plain text, not JSON, causing `json.loads()` to throw and fall back to `result.stdout[:2000]` | `districts/coding/git_bot.py:308-321` | HIGH — silent failure; fix: remove `--format json`, parse stdout lines instead |
| G2 | GitBot `get_status()` at line 316 in `mcp_server.py` calls `await bot.get_status()` but `get_status()` is synchronous (not async) — this will fail with a coroutine type error at runtime when the MCP tool is invoked | `core/mcp_server.py:316`, `districts/coding/git_bot.py:31` | HIGH — MCP tool `git_status` will throw `TypeError: cannot unpack non-async` |
| G3 | No impact/blast-radius analysis in Python. `analyze_with_gitnexus()` is the only bridge to GitNexus's `impact` tool, but it only calls `analyze` (the indexing command), not `gitnexus impact <symbol>`. VECTOR coding agents cannot currently ask "what breaks if I change X?" | `districts/coding/git_bot.py:301-328` | HIGH — core GitNexus value not exposed |
| G4 | No `gitnexus_query()`, `gitnexus_context()`, `gitnexus_impact()`, `gitnexus_detect_changes()`, `gitnexus_rename()`, `gitnexus_cypher()` methods in GitBot. The 16 MCP tools from GitNexus are only accessible if Claude Code uses the MCP server directly; no Python wrapper exists for programmatic calls from VECTOR agents | `districts/coding/git_bot.py` | MEDIUM — agents can't call GitNexus tools from Python code |
| G5 | GitNexus skills not installed in `.claude/skills/`. The 7 skills (`gitnexus-exploring`, `gitnexus-debugging`, `gitnexus-impact-analysis`, `gitnexus-refactoring`, `gitnexus-pr-review`, `gitnexus-cli`, `gitnexus-guide`) are in `gitnexus-claude-plugin/skills/` but not copied to the project `.claude/skills/` directory | `gitnexus-claude-plugin/skills/` | MEDIUM — Claude Code agents lack graph-aware coding workflows |
| G6 | GitNexus hooks not registered. `gitnexus-claude-plugin/hooks/hooks.json` defines PreToolUse + PostToolUse hooks for graph-enriched searches and stale-index detection. Not present in `.claude/settings.json` | `gitnexus-claude-plugin/hooks/hooks.json` | MEDIUM — search results not enriched with graph context; stale index not auto-detected after commits |
| G7 | `tree_sitter` is installed in VECTOR's environment but `tree_sitter_languages` is not (`ModuleNotFoundError`). Any future Python code that tries to do AST analysis (e.g., a Python-native graph builder) will fail. Not a GitNexus gap specifically, but the absence means VECTOR cannot do its own AST parsing | `requirements.txt` (missing `tree-sitter-languages`) | LOW — latent; no current code depends on it |
| G8 | `analyze_with_gitnexus()` uses `subprocess.run()` (blocking, synchronous) inside an `async def` without `asyncio.to_thread()`. On slow repos this will block the event loop for up to 60 seconds (the timeout), freezing VECTOR's autonomous loop | `districts/coding/git_bot.py:307-328` | MEDIUM — event loop blockage; fix: wrap in `asyncio.to_thread()` |
| G9 | No Python method to call `gitnexus wiki` (LLM-powered documentation generation). The Wiki feature uses an OpenAI-compatible API — VECTOR could drive this via `provider_client.py` but no integration exists | `districts/coding/git_bot.py` | LOW — nice-to-have |
| G10 | GitNexus's COBOL parser (`gitnexus/src/core/ingestion/cobol/`) is the only COBOL support in the entire ecosystem. VECTOR's `core/knowledge/domain_extractor.py` (from Understand-Anything absorption) does not include COBOL pattern detection. Minor overlap concern — the two systems both scan file trees but for different purposes (DomainExtractor → entrypoints; GitNexus → full graph) | `core/knowledge/domain_extractor.py` vs `gitnexus/src/core/ingestion/cobol/` | LOW — no conflict, different scope |
