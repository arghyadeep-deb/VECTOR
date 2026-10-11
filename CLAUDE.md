# VECTOR — Claude Code Project Memory

> This file is read automatically by Claude Code at session start.
> For full project context, see `CONTEXT.md` and `.claude/rules/*`.

---

## What VECTOR Is

Virtual Entity for Cognitive Tasks & Operational Reasoning — a Darwinian multi-agent autonomous AI running 24/7 on a local machine (Legion Pro 5, RTX 5070 Ti). VECTOR governs a city of 274 manifest agents across 41 configured districts that evolve, die, and are reborn.

Owner: Arghyadeep Deb

---

## Authoritative Sources

Read these in order of priority:

1. **`CONTEXT.md`** — Full project memory, terminology, architecture
2. **`.claude/rules/*`** — Binding rules for architecture, code style, models, libraries, districts, tools
3. **`.claude/FABLE.md`** — Operating constitution (behavioral standard)
4. **`VECTOR_RULEBOOK.md`** — Owner's operational guide
5. **`README.md`** — Project overview
6. **`docs/`** — Architecture docs, ADRs, design docs
7. **`../V.E.C.T.O.R. Brain/`** — Obsidian vault, a sibling directory of this repo (there is no `brain/` junction inside the repo). Architecture, goals, blueprints, district specs

---

## Key Rules (non-negotiable)

1. **`context_engine.session_hydration_prompt()` before EVERY LLM call** — no exceptions
2. **Autonomous loop must never die** — every coroutine catches all exceptions, restarts
3. **Permission Gateway is the ONLY path to real-world actions** — LLM proposes, Gateway executes. GREEN/YELLOW/RED. Nothing bypasses this
4. **`policy.py` wired both ways** — `get_score()` BEFORE every decision, `update_from_outcome()` AFTER every action
5. **Routed inference** — `core/inference/route_policy.py` decides per task: security/privacy/RED-tier/secret-bearing tasks stay on local Ollama only; other tasks use pooled free cloud keys (heavy ones try premium free providers first); Ollama is the terminal fallback. Never crash
6. **No `print()` in production** — `loguru` everywhere
7. **SQLCipher for main DB** — always go through `core.memory.episodic.get_db_connection()`
8. **Never use `requests`, `flask`, `threading`, `pickle`** — use `httpx`, `fastapi`, `asyncio`, `json/msgpack`
9. **`core/config.py` CONFIG dict for all configurable values** — never hardcode paths/keys in business logic
10. **Free-tier only at runtime** — no paid Anthropic/OpenAI keys at runtime (owner decision 2026-07-08)

---

## Architecture Layers

```
observe(0.5s) → think(event-driven) → act(permission-gated) → reflect(2AM)
```

```
context_engine → goal_system → decision_engine → policy_check → permission_gateway → execution
```

---

## File Conventions

- Python 3.12+ (PEP 695 generics)
- `snake_case.py` for files, `PascalCase` for classes, `snake_case` for functions
- Every file ends with `if __name__ == "__main__":` block (real test, no mocks)
- Logging: `logger.info("[VECTOR][module] message")`
- Git: `[T#] module: what changed` or `auto: [module] what changed`

---

## What Exists

- **41 configured manifest districts** with **274 manifest-registered agents**; regenerate these counts from `config/agent_manifest.yaml` and `ManifestLoader.inventory()` rather than editing them by hand
- **31 LLM providers** in `core/inference/llm_providers.py`
- **30 Claude Code commands** in `.claude/commands/`
- **113 skill directories** in `.claude/skills/`
- **8 hooks** (file protection, lint, auto-commit, auto-test, screenshot)
- **7 ADRs** in `docs/adr/`
- **~6,050 test functions** in 405 files (6,254 collected by pytest)
- Counts regenerated from the code on 2026-09-24; re-run the counts rather than editing by hand.

---

## Working on VECTOR

Before any change:

1. Read the relevant `.claude/rules/*`
2. Search for existing implementations
3. Check `docs/OPEN_ISSUES.md` for current status (`.claude/rules/phase_status.md` is a historical tracker, last updated 2026-06-11)
4. Follow the mandatory workflow: brainstorming → writing-plans → executing-plans → verification-before-completion

See `CONTRIBUTING.md` for branch/commit/PR conventions.
See `STYLE_GUIDE.md` for code style.
See `TASKS.md` for current sprint.
