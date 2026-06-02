# codebuff-main Audit

## 1. Repo Reality

Codebuff is an open-source AI coding assistant (TypeScript/Node.js + small Python app) that coordinates specialized sub-agents — File Picker, Planner, Editor, Reviewer — to make precise, multi-file code changes from natural language instructions. Its benchmark claim is 61% vs Claude Code's 53% on 175+ tasks. The repo also ships Freebuff, a free ad-supported variant.

Primary language: TypeScript (the `agents/`, `common/`, `cli/`, `sdk/`, `web/` directories are all TypeScript). The `python-app/` is a thin Python wrapper around the same agent logic.

---

## 2. VECTOR Parity

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| Multi-agent coding orchestrator | `core/code_conductor/orchestrator.py` | `code_conductor: ['agent_steps.py', 'code_map.py', 'git_eval.py', 'orchestrator.py', 'str_replace.py', '__init__.py', '__pycache__']` | COVERED |
| Symbol/AST code map (tree-sitter) | `core/code_conductor/code_map.py` | File confirmed present | COVERED |
| Precision str_replace file editor | `core/code_conductor/str_replace.py` | File confirmed present — port of `codebuff/sdk/src/tools/change-file.ts` | COVERED |
| Git-aware eval / diff | `core/code_conductor/git_eval.py` | File confirmed present | COVERED |
| Multi-agent coding agents (GitBot, CodeReviewer, ArchitectBot, BugHunter) | `districts/coding/` | `districts/coding/__init__.py` loaded successfully | COVERED |
| Code conductor district agent | `districts/coding/code_conductor_agent.py` | File confirmed present | COVERED |

**Verification output (exact):**
```
code_conductor: ['agent_steps.py', 'code_map.py', 'git_eval.py', 'orchestrator.py', 'str_replace.py', '__init__.py', '__pycache__']
```

### What codebuff has that VECTOR does NOT

- **TypeScript agent SDK** (`sdk/src/`) — not needed; VECTOR is Python-only
- **Evals harness** (`evals/buffbench/`) — 175+ task benchmark suite against open-source repos; VECTOR has no equivalent automated coding benchmark
- **Browser-based REPL** (`web/`) — not needed for VECTOR
- **Librarian agent** (`agents/librarian/`) — indexes external documentation for context; VECTOR has `paper_reader.py` + `web_scout.py` but no dedicated doc-librarian for third-party API docs
- **Context pruner** (`agents/context-pruner.ts`) — trims context window before expensive LLM calls; VECTOR has `TokenJuice` (absorbed from openhuman) which covers this

---

## 3. Frontend

N/A — codebuff's `web/` is a TypeScript REPL UI, not a design asset for VECTOR's dashboard.

---

## 4. Verdict

**SAFE TO DELETE**

VECTOR already has a direct Python port of codebuff's core architecture in `core/code_conductor/` (orchestrator, code map, str_replace, git_eval) and a full coding district with 10+ specialized agents. The TypeScript/Node.js shell of codebuff has zero value to add.

---

## 5. Gaps

| Gap | Priority | Notes |
|-----|----------|-------|
| Coding eval/benchmark harness | Low | Codebuff's `evals/buffbench` benchmarks agent quality on 175 real tasks. VECTOR has no equivalent. Could be a future `districts/qa/` enhancement. |
| External doc librarian | Low | `agents/librarian/` fetches and indexes external API docs (npm, PyPI, GitHub READMEs) for context. VECTOR's `paper_reader.py` handles ArXiv only. Gap is narrow. |
