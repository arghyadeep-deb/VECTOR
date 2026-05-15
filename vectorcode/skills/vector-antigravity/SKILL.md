<!-- VECTOR-INGESTED ASSET
  Source: .claude/skills/SKILL.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:55+00:00
-->

---
name: vector-antigravity
description: Quick workflow helpers for VECTOR development in Antigravity IDE terminal. Combines run, test, and commit steps.
---

The user is running VectorCode from the Antigravity IDE terminal. This skill provides quick workflow shortcuts for common VECTOR dev operations.

## Usage
`/vector-antigravity <action>`

Actions: `run`, `test`, `commit`, `status`, `sync`

---

## `/vector-antigravity run`
Start the VECTOR FastAPI server:
```bash
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
.venv\Scripts\activate && python core/main.py
```
Then open `http://127.0.0.1:8000/docs` in Antigravity's browser panel.

---

## `/vector-antigravity test`
Run all implemented module smoke tests in sequence:
```bash
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
.venv\Scripts\python.exe core/city/agent_base.py
.venv\Scripts\python.exe core/memory/episodic.py
.venv\Scripts\python.exe core/loop/permission_gateway.py
.venv\Scripts\python.exe core/loop/context_engine.py
.venv\Scripts\python.exe core/brain/goal_system.py
.venv\Scripts\python.exe core/loop/decision_engine.py
.venv\Scripts\python.exe core/memory/policy.py
.venv\Scripts\python.exe core/memory/reasoning_memory.py
```
Report: how many ✅ / total files.

---

## `/vector-antigravity commit`
Same as `/vector-commit` — create a properly formatted VECTOR commit. See that skill for details.

---

## `/vector-antigravity status`
Quick project health check:
1. `git status --short` — uncommitted changes
2. `ollama list` — which models are loaded
3. `python -c "import sqlite3; c=sqlite3.connect('vector_memory.db'); print(c.execute('SELECT COUNT(*) FROM episodic_memory').fetchone())"` — memory row count

---

## `/vector-antigravity sync`
Sync Antigravity with latest changes:
1. Run all smoke tests (`/vector-antigravity test`)
2. Show git diff summary
3. Ask if ready to commit

---

## Notes for Antigravity IDE
- VectorCode edits files directly on disk — Antigravity picks them up immediately, no reload needed
- The `.venv` is at the project root; always use `.venv\Scripts\python.exe` not system Python
- Python interpreter for Antigravity: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\.venv\Scripts\python.exe`
- All VectorCode hooks run in Antigravity's integrated terminal automatically
