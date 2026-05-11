# Problem 08 — EpisodicMemory.self.conn Never Assigned

**Severity: CRITICAL**
**Status: FIXED**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Symptom

Any call to `remember()`, `recall_fact()`, `store_chain()`, `get_training_data()`,
`update_skill()`, `get_skill()`, `get_stats()`, or `close()` raises:

```
AttributeError: 'EpisodicMemory' object has no attribute 'conn'
```

## Root Cause

`core/memory/episodic.py` underwent a singleton refactor. The `__init__` was
changed to call `get_db_connection()` for side-effects only, but the return
value was never assigned:

```python
# BROKEN (before fix)
def __init__(self):
    get_db_connection()   # returns connection but discards it
```

Only `store()` and `recall()` were migrated to use `get_temp_cursor()` (which
calls the module-level singleton correctly). The remaining 7 methods still
reference `self.conn` — which never existed.

## Blast Radius

This single bug cascades to break:
- **RULE 7 (RL Policy):** `policy.py` calls `self._get_mem().conn` in both
  `get_score()` and `update_from_outcome()` — both crash → RL loop is dead
- **RULE 8 (Reasoning Chains):** `reasoning_memory.store_chain()` crashes →
  no training data ever tagged `is_training_data=1`
- **RULE 9 (Darwinism):** `agent_registry._persist_ghost()` crashes →
  ghost memory never written to `agent_history` table
- Ghost memory on agent death is permanently lost on process restart

## Secondary Bug Fixed

Dead code block at lines 180–192 (original numbering) was unreachable — a
leftover `cursor.execute()` after a `return []` with undefined variables
`conditions` and `params`. Removed.

## Solution Implemented

`core/memory/episodic.py` — `__init__` line 111:

```python
# FIXED
def __init__(self):
    self.conn = get_db_connection()
    logger.info("Episodic memory initialized (singleton connection)")
```

Dead code block removed (13 lines after `return result` in `recall()`).

## Verification

All 9 methods (`store`, `recall`, `remember`, `recall_fact`, `store_chain`,
`get_training_data`, `update_skill`, `get_skill`, `get_stats`) now share the
same singleton connection. The `__main__` block smoke test covers
`store_chain` and `get_training_data`.
