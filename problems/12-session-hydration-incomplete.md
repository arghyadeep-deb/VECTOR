# Problem 12 — Session Hydration Incomplete (RULE 1)

**Severity: HIGH**
**Status: FIXED 2026-05-12 — All 3 parts complete. (A) context_engine.get_world_state() now has 14 domains including location/calendar/finance/academic/comms. (B) autonomous_loop._think_tick() calls get_world_state() first and passes snapshot into Candidate.situation. (C) All 30 district _call_ollama() methods inject ContextEngine().session_hydration_prompt() as system message.**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Part A — Only 4 of 9 Required Fields Present in Hydration Prompt

### Spec Requirement

`session_hydration_prompt()` must inject all 9 fields:

| Field | Required | Present |
|-------|----------|---------|
| `time` (hour, energy_window) | ✅ | ✅ |
| `location` (current, type) | ✅ | ❌ |
| `calendar` (next_event, free_blocks) | ✅ | ❌ |
| `health` (fatigue_score) | ✅ | ✅ (partial) |
| `comms` (urgent, unread) | ✅ | ❌ |
| `academic` (KIIT classes, attendance_risk) | ✅ | ❌ |
| `environment` (screen_activity, people_visible) | ✅ | ✅ |
| `finance` (monthly_spend) | ✅ | ❌ |
| `active_goals` | ✅ | ✅ |
| `recent_memory` (last 48h summary) | ✅ | ✅ |

Missing: `location`, `calendar`, `comms`, `academic`, `finance` (5 of 9).

### Fix Required

`core/loop/context_engine.py` — extend `get_world_state()` to pull from:
- `DeadlineManager.get_schedule_context()` → `calendar` field
- `HermesAdapter.get_pending_messages()` → `comms` field
- `KIITScraper.get_attendance_alerts()` → `academic` field
- `ExpenseTracker.get_monthly_summary()` → `finance` field

These district agents already exist and return the right data formats.
The context engine just needs to call them.

---

## Part B — Hydration Never Called in Autonomous Loop Think Path

### Symptom

`context_engine.session_hydration_prompt()` exists and is called correctly in:
- `ambient_listener.py` (voice path)
- All district agents with `_call_ollama()`

But it is **never called** in the main `autonomous_loop._think_tick()`.
Every LLM call made during the autonomous think cycle has no context.
VECTOR operates with amnesia every 10 seconds in its own core loop.

### Root Cause

`_think_tick()` builds candidates from goal actions and passes them to
`decision_engine.evaluate()`. Neither `_think_tick` nor `evaluate()` calls
`session_hydration_prompt()` before reasoning.

### Fix Required

`core/loop/autonomous_loop.py` — `_think_tick()`:

```python
async def _think_tick(self):
    # RULE 1 — inject full context before any LLM reasoning
    ctx = self._get_context().session_hydration_prompt()
    # Pass ctx as system prompt to decision_engine
    candidates = self._get_goals().generate_immediate_actions(limit=4)
    decision = self._get_engine().evaluate(candidates, context=ctx)
    ...
```

`core/loop/decision_engine.py` — `evaluate()`:

```python
def evaluate(self, actions: list, context: str = "") -> Decision:
    # Use context as system message prefix for any LLM calls within evaluate
```

---

## Part C — RULE 1 Violations in District Agents (30+ calls)

Districts calling `_call_ollama()` without hydration:

| District | File | Violation Count |
|----------|------|-----------------|
| languages | hindi_coach.py | 4 LLM calls |
| languages | bengali_coach.py | 3 LLM calls |
| languages | assamese_coach.py | 3 LLM calls |
| languages | japanese_coach.py | 3 LLM calls |
| languages | english_coach.py | 4 LLM calls |
| karpathy_lab | architecture_builder.py | multiple |
| karpathy_lab | progress_tracker.py | 1 call |

Pattern fix for all: add `session_hydration_prompt()` call before each
`_call_ollama()` in the method body:

```python
from core.loop.context_engine import ContextEngine
ctx = ContextEngine().session_hydration_prompt()
prompt = f"{ctx}\n\n{user_prompt}"
response = self._call_ollama(prompt)
```
