# Problem 13 — Reasoning Chains Not Persisted (RULE 8)

**Severity: HIGH**
**Status: DOCUMENTED — requires wiring in autonomous_loop + decision_engine**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Symptom

The `reasoning_chains` table exists and is correctly defined. `store_chain()`
correctly tags `is_training_data=1` when `reward > 0.7`. But the table is
essentially empty at runtime because:

1. `autonomous_loop._act_on()` stores outcomes to `episodic_memory` via
   `store()` — NOT to `reasoning_chains` via `store_chain()`. The chains
   therefore miss the `is_training_data` flag entirely.

2. `inject_past_reasoning()` is implemented in `reasoning_memory.py` but is
   **never called** before any decision. Decision engine evaluates without
   past reasoning context every single time.

## Root Cause

`autonomous_loop._act_on()` lines 159–173 (original):

```python
# Wrong — stores to episodic_memory, not reasoning_chains
if winner.reasoning_chain:
    self._get_memory().store(
        event_type="reasoning_chain",
        content=json.dumps(winner.reasoning_chain),
        ...
    )
```

Should be:

```python
if winner.reasoning_chain:
    self._get_memory().store_chain(
        situation=str(winner.params),
        goal_ids=winner.goal_ids,
        steps=winner.reasoning_chain,
        action=winner.action_type,
        outcome=str(gate_result.result),
        reward=reward,
    )
```

## Fix Required

### Part 1 — Store to reasoning_chains (autonomous_loop.py)

In `_act_on()`, replace the `store()` call with `store_chain()` as above.
This ensures all thought-action-outcome triples get `is_training_data` flag.

### Part 2 — Call inject_past_reasoning before decisions (decision_engine.py)

In `evaluate()`:

```python
from core.memory.reasoning_memory import ReasoningMemory
past = ReasoningMemory().inject_past_reasoning(
    situation=str(actions[0].params) if actions else ""
)
# prepend past to context string passed to any LLM call within evaluate
```

### Part 3 — Verify training data accumulates

After fix, run VECTOR for one session and check:

```sql
SELECT COUNT(*), AVG(reward)
FROM reasoning_chains
WHERE is_training_data = 1;
```

Should show non-zero count for chains with `reward > 0.7`.

## Why This Matters

The entire custom LLM pipeline (OpenMythos / Karpathy track) depends on
`reasoning_chains` as its training data source. If no chains are written,
Month 2 fine-tuning starts from zero examples.
