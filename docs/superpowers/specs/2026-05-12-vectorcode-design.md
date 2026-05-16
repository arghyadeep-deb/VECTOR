# VectorCode — Design Spec
**Date:** 2026-05-12  
**Goal:** Full Python port of VECTOR's architecture into VECTOR. VECTOR replaces Claude Code as the autonomous coding agent — locally, using Ollama models only.

---

## Architecture

VectorCode = VECTOR (completely ported to Python) + VECTOR infrastructure.  
Claude API removed everywhere. All inference via Ollama. RULE 11 enforced.

```
agents/districts/coding/vectorcode/
├── __init__.py
├── session.py          ← shared state across all 3 modes
├── router.py           ← SemanticRouter (which model for which task)
├── swarm.py            ← UnifiedSwarmCoordinator (60+ agents)
├── queen.py            ← QueenCoordinator (hive-mind task decomposition)
├── gsd_loop.py         ← discuss→plan→execute→verify workflow
├── repl.py             ← Mode A: interactive terminal REPL
├── autonomous.py       ← Mode B: fully autonomous task execution
├── hybrid.py           ← Mode C: autonomous + checkpoint gates
├── tools/
│   ├── file_tools.py   ← read/write/edit/grep/glob
│   ├── bash_tools.py   ← safe command execution (permission-gated)
│   ├── code_graph.py   ← code-review-graph AST + blast-radius analysis
│   └── browser_tools.py← Playwright browser automation
├── memory/
│   ├── faiss_index.py  ← replaces VECTOR HNSW WASM (FAISS C++ bindings)
│   ├── pattern_store.py← SONA port: patterns → reasoning_chains
│   └── auto_bridge.py  ← bidirectional sync: file memory ↔ FAISS
├── hooks/
│   ├── registry.py     ← 17 hooks (pre-edit, post-task, route, explain...)
│   └── workers.py      ← 12 background workers (ultralearn, optimize...)
├── security/
│   ├── validator.py    ← Pydantic input validation at all tool boundaries
│   └── safe_executor.py← path traversal + command injection protection
└── mcp_tools.py        ← expands mcp_server.py from 14 → 314 tools
```

---

## Three Interaction Modes (all simultaneous via TaskQueue)

### Mode A — Terminal REPL
`python -m agents.districts.coding.vectorcode.repl`  
You type → VECTOR reads/writes files, runs bash, replies. Same UX as Claude Code.  
Blocking in foreground. Full GSD loop per request.

### Mode B — Autonomous
`TaskQueue.submit(vectorcode_auto_task, name="...", priority=HIGH)`  
Give a task → runs completely unattended. Pauses only for RED actions.  
Runs as background TaskQueue task. Terminal notifies on complete/fail.

### Mode C — Hybrid
`python -m agents.districts.coding.vectorcode.hybrid`  
Autonomous but pauses at: plan approval, destructive edits, RED gateway actions.  
You approve checkpoints; everything else runs without you.

All three share `session.py` state. Mode B and C submit via TaskQueue so Mode A can run in parallel.

---

## SwarmCoordinator (VECTOR UnifiedSwarmCoordinator → Python)

### Agent Types (60+, all use Ollama)
```
Core agents:    Architect, Coder, Reviewer, Tester, Debugger, Optimizer
Security:       SecurityAuditor, CVEScanner, InputValidator, ThreatModeler
DevOps:         GitBot, CIWatcher, DeployManager, DocWriter
Research:       WebScout, PaperReader, PatternFinder, TrendAnalyzer
Specialized:    SQLExpert, APIDesigner, PerformanceProfiler, RefactorBot
Support:        ContextLoader, SummaryBot, ReportWriter, StatusChecker
```

### Topologies (VECTOR port)
- **Hierarchical** — Queen → Domain leads → Workers. Best for complex tasks.
- **Mesh** — All agents peer. Best for parallel independent subtasks.
- **Adaptive** — Starts hierarchical, switches to mesh when subtasks diverge.

### QueenCoordinator
Decomposes the user's task into subtasks. Routes each subtask to the right domain.  
Uses `vector-reasoning` for planning. Respects RULE 4 — plans model switches upfront.

---

## SemanticRouter (VECTOR's provider routing → Ollama routing)

| Task Type | Model | Switch Cost |
|-----------|-------|-------------|
| Discuss / understand | `vector-reasoning` | baseline |
| Write code | `vector-coder` | 1 switch |
| Review / verify | `vector-dev` | 1 switch |
| Quick status / answers | `vector-fast` | 1 switch |
| Deep analysis (>32K) | `vector-deep` | 1 switch |
| Architecture decisions | `vector-chairman` | 1 switch |

Router minimizes total switches per GSD cycle. Pattern cache skips discuss phase on repeat tasks (SONA port). Max 3 switches per full cycle: reasoning → coder → dev.

---

## Memory Layer

### FAISSIndex (VECTOR HNSW → FAISS)
- `faiss.IndexHNSWFlat` — same algorithm, C++ bindings, faster than WASM
- Embeddings: `nomic-embed-text` via Ollama (already installed)
- Dimensions: 768 (nomic-embed-text output)
- Persistence: SQLite metadata + FAISS binary index on disk
- Search: cosine similarity, top-k with confidence threshold

### PatternStore (VECTOR SONA → reasoning_chains)
Stores successful (task_description, plan, execution_steps, outcome) tuples.  
On new task: embed → FAISS search → if similarity > 0.85, reuse plan (skip discuss).  
Reward updates write back to `policy_memory` (RULE 7).  
High-reward patterns (>0.7) tagged `is_training_data=1` (RULE 8).

### AutoMemoryBridge (VECTOR AutoMemoryBridge → Python)
Bidirectional sync between:
- VECTOR file-based memory (`~/.claude/projects/.../memory/`)
- FAISS index + episodic_memory
- Runs as background worker every 5 minutes
- Insight categories: patterns, debugging, architecture, performance, security, preferences

---

## Hooks (VECTOR 17 hooks → Python)

```python
PRE_EDIT       POST_EDIT      PRE_TASK       POST_TASK
SESSION_START  SESSION_END    ROUTE          EXPLAIN
PRETRAIN       BUILD_AGENTS   TRANSFER       TEAMMATE_IDLE
TASK_COMPLETE  NOTIFY         INTELLIGENCE   SESSION_RESTORE
POST_COMMAND
```

All hooks registered in `HookRegistry`. Priority-ordered. Timeout-protected.  
Hooks fire around every tool call and task lifecycle event.

---

## Background Workers (VECTOR 12 workers → Python TaskQueue)

All submitted as low-priority `TaskQueue` tasks. Run between user tasks.

```
ultralearn    — extracts patterns from completed tasks → PatternStore
optimize      — tunes FAISS index, compacts SQLite
consolidate   — merges redundant patterns (EWC-style)
predict       — pre-fetches likely next tasks from PatternStore
audit         — security scan of recent file edits
map           — updates repo AST graph (CodeGraph)
preload       — warms up most-likely-next model in Ollama
deepdive      — overnight deep analysis of codebase
document      — auto-generates/updates docstrings for changed files
refactor      — suggests refactors for high-complexity functions
benchmark     — profiles recent code changes
testgaps      — detects untested functions → feeds test_writer.py
```

---

## Security Layer (VECTOR @claude-flow/security → Pydantic + Python)

### InputValidator
Pydantic models for every tool input. No raw strings pass through tool boundaries.

### PathValidator
- Blocks: `../`, absolute paths outside repo root, symlink traversal
- Allowlist: only paths inside `CONFIG["coding"]["repo_path"]`

### SafeExecutor
- Command allowlist for BashTools (git, python, pytest, pip, npm, cargo...)
- Blocks: `rm -rf`, `dd`, `mkfs`, `curl | bash`, pipe-to-shell patterns
- All executions log to episodic_memory
- RED-gates anything not on allowlist → permission_gateway.py

---

## GSD Loop (get-shit-done workflow)

```
DISCUSS  → vector-reasoning understands task, asks clarifying questions (Mode A/C)
           skipped if PatternStore similarity > 0.85 (Mode B always skips)
PLAN     → vector-reasoning generates step-by-step plan
           Mode A/C: print plan, wait for approval
           Mode B: execute immediately
EXECUTE  → vector-coder writes/edits files, runs bash, tracks progress
           hooks fire: PRE_EDIT, POST_EDIT per file
           RED actions → permission_gateway.py (always)
VERIFY   → vector-dev reviews output, runs tests, checks coverage
           if tests fail: re-enter EXECUTE with failure context
           max 3 retry cycles before escalating to user
```

---

## MCP Tool Expansion (14 → 314)

Grouped into categories matching VECTOR's 314 tools, all pointing to VECTOR internals:

| Category | Count | Backend |
|----------|-------|---------|
| Agent tools (spawn, status, pool) | 9 | SwarmCoordinator |
| Swarm tools (init, submit, assign) | 8 | SwarmCoordinator |
| Memory tools (store, search, semantic) | 12 | FAISSIndex + EpisodicMemory |
| Hook tools (register, execute, route) | 17 | HookRegistry |
| Task tools (create, assign, complete) | 8 | TaskQueue |
| Security tools (scan, audit, validate) | 10 | SecurityLayer |
| Neural/pattern tools (train, predict) | 8 | PatternStore |
| File tools (read, write, edit, grep) | 10 | FileTools |
| Git tools (commit, pr, diff, blame) | 12 | GitBot |
| Test tools (generate, run, coverage) | 8 | TestWriter |
| Doc tools (generate, update) | 6 | DocWriter |
| Browser tools (navigate, screenshot) | 8 | BrowserTools |
| Code graph tools (ast, blast-radius) | 8 | CodeGraph |
| Performance tools (profile, benchmark) | 8 | Workers |
| Background worker tools | 12 | Workers |
| Config/status tools | 10 | CONFIG + ContextEngine |
| Existing 14 tools | 14 | Already in mcp_server.py |

---

## Implementation Phases

### Phase VC-1: Core Foundation
`session.py`, `router.py`, `tools/file_tools.py`, `tools/bash_tools.py`,
`security/validator.py`, `security/safe_executor.py`

### Phase VC-2: Memory Layer
`memory/faiss_index.py`, `memory/pattern_store.py`, `memory/auto_bridge.py`

### Phase VC-3: Swarm + Queen + GSD
`swarm.py`, `queen.py`, `gsd_loop.py`, 60+ agent type definitions

### Phase VC-4: Three Modes
`repl.py`, `autonomous.py`, `hybrid.py`

### Phase VC-5: Hooks + Workers
`hooks/registry.py`, `hooks/workers.py`

### Phase VC-6: Code Graph + Browser
`tools/code_graph.py`, `tools/browser_tools.py`

### Phase VC-7: MCP Expansion
`mcp_tools.py` → expand `core/mcp_server.py` to 314 tools

### Phase VC-8: Modelfile + Skill Upgrades (Sub-project B)
Improve all 10 modelfile system prompts using system_prompts_leaks patterns.
Harvest all 10 skill collection repos into `~/.claude/skills/`.

---

## Rules Compliance
- RULE 2: run_forever() in autonomous.py never crashes
- RULE 3: all actions through permission_gateway.py
- RULE 4: SemanticRouter loads one model at a time, minimizes switches
- RULE 7: PatternStore reward → policy_memory after every task
- RULE 8: all task chains stored in reasoning_chains
- RULE 9: VectorCode agents have HP, die at 0, ghost memory preserved
- RULE 11: zero Claude API calls — all Ollama local
