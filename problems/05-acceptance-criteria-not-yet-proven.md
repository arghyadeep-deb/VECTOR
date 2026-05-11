# Problem 05 - Ship Criteria Are Not Yet Proven

## Symptom

The acceptance criteria require all three to pass:

1. VECTOR did something useful without being asked.
2. VECTOR learned from last week's mistake.
3. VECTOR remembers the last 3 days after a crash.

The current repo has pieces for these, but no end-to-end proof.

## Why It Matters

These criteria are the difference between a promising framework and a living
assistant.

## Implemented Solution

The new `run_vector.py smoke` command creates a concrete startup check for:

- agent bootstrap
- session hydration
- immediate goal generation
- four-candidate decision scoring
- SQLite memory writes

This is not the final ship test, but it creates a measurable spine check.

## Remaining Work

- Add a proactive alert scenario.
- Add a policy-learning scenario.
- Add a restart-memory scenario.
- Put all three behind one command, e.g. `python run_vector.py acceptance`.

