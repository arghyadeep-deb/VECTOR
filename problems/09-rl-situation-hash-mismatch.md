# Problem 09 — RL Situation Hash Mismatch (Policy Loop Broken)

**Severity: CRITICAL**
**Status: FIXED 2026-05-11 — autonomous_loop._act_on() now uses sha256(action_type:params_json)[:12] matching decision_engine. PolicyMemory.make_situation_hash also upgraded MD5→SHA256.**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Symptom

The RL policy records reward data that is permanently invisible to the scoring
phase. `policy.py`'s `update_from_outcome()` writes rows that `get_score()`
can never find. The system appears to learn but is actually writing to a
black hole.

## Root Cause

Two different hash functions compute the "situation" key for the same action:

**During scoring** (`decision_engine._score_candidate()` line 108):
```python
situation_hash = hashlib.md5(
    f"{candidate.action_type}{str(candidate.params)}".encode()
).hexdigest()[:12]
```
Hash input: `action_type + params` combined.

**During reward update** (`autonomous_loop._act_on()` line 156):
```python
sit_hash = PolicyMemory.make_situation_hash(winner.params)
```
Hash input: `params` alone (action_type excluded).

The lookup key and the write key are different strings → `get_score()` reads
a row that `update_from_outcome()` never writes, and vice versa. The RL loop
accumulates zero usable learning signal.

## Secondary Issue

`decision_engine` uses MD5 for the hash. MD5 is flagged as deprecated/weak
by security tooling. SHA-256 with `[:12]` is equivalent length and not
deprecated.

## Fix Required

In `core/loop/autonomous_loop.py` in `_act_on()`, replace:

```python
sit_hash = PolicyMemory.make_situation_hash(winner.params)
```

with:

```python
import hashlib
sit_hash = hashlib.sha256(
    f"{winner.action_type}{str(winner.params)}".encode()
).hexdigest()[:12]
```

Also update `decision_engine._score_candidate()` line 108 to use SHA-256
instead of MD5:

```python
situation_hash = hashlib.sha256(
    f"{candidate.action_type}{str(candidate.params)}".encode()
).hexdigest()[:12]
```

And update `PolicyMemory.make_situation_hash()` to match the same formula
so all three callsites are consistent.

## Verification

After fix: run VECTOR for one full think cycle, then query:

```sql
SELECT action_type, situation_hash, avg_reward, sample_count
FROM policy_memory
ORDER BY last_updated DESC
LIMIT 10;
```

Should show non-zero `sample_count` on the same `situation_hash` values
that `decision_engine` queries. Before fix, this table stays empty at runtime.
