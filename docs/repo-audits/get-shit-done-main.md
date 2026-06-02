# get-shit-done-main Audit

## 1. Repo Reality

GSD (Get Shit Done) is an **archived** Node.js/TypeScript CLI and SDK for AI-assisted project planning and phase execution. It manages a `.planning/` workspace: roadmaps, milestones, phases, state tracking, and workflow prompts for AI coding agents (Claude Code, Gemini CLI, Codex, Grok). The repo README explicitly redirects to `github.com/open-gsd/get-shit-done-redux` — this codebase is no longer maintained. The core value is its collection of 30+ workflow prompt templates (AGENTS.md workflows) and a sophisticated milestone/phase state machine.

---

## 2. VECTOR Parity

| Feature | VECTOR file | Verified output | Status |
|---------|-------------|-----------------|--------|
| Phase/milestone planning | `brain/.claude/commands/multi-plan.md`, `brain/.claude/commands/execute-plan.md` | VECTOR has plan → execute skill chain via superpowers plugin | COVERED |
| Project state tracking | `districts/projects/project_planner.py`, `districts/projects/deadline_watcher.py` | Districts confirmed built per phase_status.md | COVERED |
| Roadmap management | `brain/VECTOR/Roadmap.md` + goal_system.py (3 horizons) | `core/brain/goal_system.py` loaded — LONG/MID/SHORT horizons active | COVERED |
| Workflow prompt templates | `brain/.claude/commands/` (30+ commands), `brain/.claude/skills/` | Skills: loop-start, orchestrate, multi-execute, quality-gate, etc. | COVERED |
| Agent context injection | `core/loop/context_engine.py` — `session_hydration_prompt()` | Context engine loaded per verification | COVERED |
| STATE.md / progress tracking | `districts/projects/progress_tracker.py` | File confirmed present | COVERED |

**GSD is an archived redirect** — `README.md` first line: `<!-- GSD 2 - Archived repository redirect -->`. Active development is at open-gsd/get-shit-done-redux.

### What GSD has that VECTOR does NOT

- **Sync Runtime Bridge** (`sdk/src/runtime-bridge-sync/`) — synchronous `Atomics.wait` bridge from CJS to async SDK; TypeScript-specific, not applicable to Python
- **Workstream isolation** — parallel named workstreams with independent `.planning/workstreams/` dirs; VECTOR's goal system has horizons but not true workstream sandboxing
- **gsd-prompt-guard / gsd-read-injection-scanner** hooks (`get-shit-done/hooks/`) — pre-tool hooks that scan for prompt injection in read operations; VECTOR has `PromptInjectionScanner` in `core/security/` but not wired as a pre-read hook
- **Automated phase runner** — SDK `GSD.run()` discovers and executes phases sequentially without human confirmation per phase; VECTOR executes plans via `executing-plans` skill but requires human review checkpoints

---

## 3. Frontend

N/A — GSD has no UI component. It is a CLI/SDK tool.

---

## 4. Verdict

**SAFE TO DELETE**

GSD is explicitly archived and redirects to a new repo. VECTOR already covers roadmap/phase/milestone management via `districts/projects/`, `core/brain/goal_system.py`, and 30+ brain skills. The TypeScript/Node.js runtime is not applicable to VECTOR's Python stack.

---

## 5. Gaps

| Gap | Priority | Notes |
|-----|----------|-------|
| Named workstream isolation | Low | GSD supports parallel named workstreams (separate `.planning/workstreams/<name>/` dirs) per project. VECTOR's goal system doesn't sandbox parallel initiative tracks. Could be added to `districts/projects/` if VECTOR manages multiple concurrent projects. |
| Pre-read prompt injection hook | Medium | `gsd-read-injection-scanner.js` scans file content before injecting into context. VECTOR's `PromptInjectionScanner` exists in `core/security/` but is only called at the API boundary (`/commands` endpoint) — not on every file read in the autonomous loop. Low real-world risk but a genuine gap vs GSD's defense depth. |
