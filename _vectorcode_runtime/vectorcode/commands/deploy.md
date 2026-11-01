<!-- VECTOR-INGESTED ASSET
  Source: .claude/commands/deploy.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

---
name: deploy
description: Pre-deploy verification checklist for any VECTOR district or module.
argument-hint: "[district-name or module]"
---

Pre-deploy check for $ARGUMENTS:

**Step 1 — Tests**
`pytest tests/ -x -q` — all green, zero failures

**Step 2 — Three-question shipped test (from critical_rules.md)**
- [ ] Did VECTOR do something useful today you did NOT ask it to do?
- [ ] Last week's mistake — is VECTOR still making it this week?
- [ ] Laptop crashes right now — does VECTOR remember the last 3 days?
All three must be YES before marking shipped.

**Step 3 — Safety gates**
- [ ] `permission_gateway.py` wired — no direct action execution
- [ ] HumanLayer gates on all RED-tier actions
- [ ] No `.env` files referenced at runtime — values from `CONFIG` only
- [ ] `OLLAMA_MAX_LOADED_MODELS=1` confirmed in env

**Step 4 — Memory continuity**
- [ ] `episodic_memory` table schema unchanged
- [ ] `session_hydration_prompt()` tested with a cold start
- [ ] Ghost memory preserved for any agents with HP < 100

**Step 5 — Visual check**
If dashboard is involved: `gstack /browse <url>` to confirm UI renders

Report: READY / BLOCKED (list what's blocking)
