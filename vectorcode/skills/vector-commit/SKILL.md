<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/SKILL.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: vector-commit
description: Create a git commit with the correct VECTOR commit message format. Determines the task day automatically.
---

The user wants to commit their VECTOR work. Use the correct VECTOR commit format.

## Commit Message Format

**Auto-commits by VECTOR:** `auto: [module] what changed`
**Manual commits:** `[T{day}] module: description done`

Examples:
- `[T1.4] main.py: FastAPI server + 6 routes complete`
- `[T2.1] context_engine: session_hydration_prompt + world state done`
- `auto: [episodic] FTS5 table schema updated`

## Steps

1. Run `git status` to see what files changed
2. Run `git diff --stat` to understand the scope
3. Determine the task day (T1-T7) from `vectorcode/rules/phase_status.md`:
   - T1 = config, episodic, multi_db, main
   - T2 = context_engine, goal_system, decision_engine, policy, reasoning_memory, permission_gateway, agent_base, governor
   - T3 = voice pipeline, autonomous_loop
   - T4 = sensing, control
   - T5 = coding/time_calendar/security/communications districts
   - T6 = memory_curator, research, cloud
   - T7 = obsidian_sync, llm_council, phone_node
4. Stage only the relevant files (`git add <specific files>` — never `git add -A` unless user confirms)
5. Write a commit message in the correct format
6. Commit

## Never commit
- `.env` files
- `*.db` SQLite databases
- `models/*.lgb` LightGBM model files
- `google_credentials.json`
- `__pycache__/` or `.pyc` files
