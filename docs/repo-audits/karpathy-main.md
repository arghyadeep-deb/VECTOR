# karpathy-main Audit

**Audited:** 2026-06-02
**Repo path:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\karpathy-main`
**VECTOR codebase:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase`

---

## 1. Repo Reality

**What it is:** A thin ADK (Google Agent Development Kit) orchestration shell that wraps an agentic ML engineer persona named "Karpathy". It is NOT Andrej Karpathy's work — the README explicitly disclaims this. It is made by K-Dense Inc. as a showcase for their "Scientific Agent Skills" library.

**Source files (5 total):**

| File | Role |
|------|------|
| `karpathy/__init__.py` | Package init |
| `karpathy/agent.py` | Defines `main_agent` using Google ADK `LlmAgent` + `LiteLlm` wrapper |
| `karpathy/instructions.yaml` | System prompt YAML defining the agent + 12 sub-expert roles |
| `karpathy/tools.py` | Single tool: `delegate_task()` which spawns a Claude Code sub-agent via `claude_agent_sdk` |
| `karpathy/utils.py` | `load_instructions()` helper |
| `start.py` | Bootstraps a `sandbox/` venv, pulls "Scientific Agent Skills" from GitHub, copies `.env`, starts `adk web` |

**What it actually does:** On startup it creates a `sandbox/` directory, installs ML packages (PyTorch, transformers, scikit-learn), and launches a web UI at `localhost:8000`. The user then chats with the "Karpathy" agent, which delegates sub-tasks (data discovery, experiment management, code writing, etc.) to Claude Code sub-agents running inside the sandbox.

**Stack:** Google ADK + `claude_agent_sdk` + OpenRouter (any model via `AGENT_MODEL` env var). No local inference. All LLM calls go through OpenRouter cloud API. No VECTOR integration.

**License:** MIT

**Dependencies:** `google-adk`, `claude-agent-sdk`, `litellm`, `python-dotenv`, `uv` (runtime package manager for sandbox).

---

## 2. VECTOR Parity

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| 30-min daily ML session tracker | `districts/karpathy_lab/progress_tracker.py` | `ProgressTracker OK: <class '...ProgressTracker'>` | COVERED |
| Training run management | `districts/karpathy_lab/progress_tracker.py` | `generate_report`, `get_progress` methods confirmed | COVERED |
| Architecture design | `districts/karpathy_lab/architecture_builder.py` | `ArchitectureBuilder OK` | COVERED |
| AutoResearch pipeline | `districts/karpathy_lab/autoresearch_runner.py` | `AutoresearchRunner OK: train=data\training_runs\train.py` | COVERED |
| Data preparation | `districts/karpathy_lab/data_prep.py` | file present in district | COVERED |
| Code writing/typing | `districts/karpathy_lab/code_typer.py` | file present in district | COVERED |
| ADK web UI | NONE | N/A | NOT PRESENT (not needed) |
| Google ADK orchestration | NONE | N/A | INTENTIONALLY ABSENT |
| OpenRouter cloud routing | `core/inference/provider_client.py` | 27-provider routing including OpenRouter | COVERED |

**VECTOR karpathy_lab district files confirmed:**
```
['architecture_builder.py', 'autoresearch_runner.py', 'code_typer.py', 'data_prep.py', 'progress_tracker.py', '__init__.py']
```

**What VECTOR has that karpathy-main does NOT:**
- HP-aware agent lifecycle (born at 500 HP, inherits ghost memory across generations)
- Local Ollama inference (zero cloud cost, zero latency overhead)
- Episodic memory: every session stored in SQLite FTS5
- Reasoning chain storage (becomes training data per RULE 8)
- Integration with the autonomous loop (karpathy sessions scheduled via APScheduler)
- `data/training_runs/train.py` wired directly into AutoresearchRunner

**What karpathy-main has that VECTOR does NOT:**
- ADK web chat UI (localhost:8000) — a browser-based chat interface for interacting with the ML agent
- 12 named sub-expert delegation roles with sandboxed execution (the sub-agents run inside an isolated `sandbox/` venv with their own `pyproject.toml`)
- "Scientific Agent Skills" integration (130+ pre-built ML workflow skills pulled from GitHub at runtime)

---

## 3. Frontend

karpathy-main has no purpose-built frontend. The UI is entirely provided by `adk web`, Google's ADK development server (React-based, runs at localhost:8000). It is a generic chat interface — not customizable, not VECTOR-aware.

VECTOR does not have an equivalent ML engineer chat UI. The `dashboard/` directory noted in phase_status.md is not yet built (`❌ Not built yet`).

**Gap for VECTOR:** If VECTOR ever needs a chat UI for Karpathy Lab sessions, this would need to be built in the Next.js dashboard (planned but not started).

---

## 4. Verdict

**SAFE TO DELETE — no absorption needed.**

VECTOR's `districts/karpathy_lab/` already implements all meaningful features of karpathy-main (session tracking, experiment management, architecture building, autoresearch, data prep, code typing). VECTOR's implementation is superior: local-first (Ollama), HP-aware, episodic memory, reasoning chain storage, autonomous loop integration.

The only things karpathy-main adds are:
1. Google ADK orchestration — a framework VECTOR does not use and should not adopt (VECTOR uses LangGraph + its own decision engine).
2. The "Scientific Agent Skills" library — a collection of Claude Code SKILL.md files for ML workflows. These are usable in any Claude Code session without importing this repo.
3. A sandbox isolation model (sub-agents run in an isolated venv) — an interesting pattern but not required for VECTOR's single-owner architecture.

**Do not absorb.** The ADK dependency conflicts with VECTOR's inference stack. The skills library is independently usable. The sandbox pattern is not applicable to VECTOR's agentic loop.

---

## 5. Gaps

No genuine Python gaps. VECTOR already covers all functional ground.

**Optional future enhancement (not a gap):** VECTOR could adopt the "sandbox isolation" pattern for Karpathy Lab — running training experiments in a dedicated venv with its own `pyproject.toml` instead of the global `.venv`. This would prevent ML library version conflicts from affecting VECTOR's core. Implementation: add a `KARPATHY_SANDBOX_DIR` to `CONFIG` and have `data_prep.py` create/manage an isolated environment via `uv sync`.
