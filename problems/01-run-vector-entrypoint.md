# Problem 01 - `run_vector.py` Was A Stub

## Symptom

`run_vector.py` returned `{"status": "stub"}` instead of starting VECTOR.

## Why It Matters

The acceptance criteria define `python run_vector.py` as the Day 1 and long-run
entrypoint. If this file is a stub, VECTOR cannot honestly be called alive,
even if individual modules exist.

## Implemented Solution

Replaced the stub with a real launcher:

- `python run_vector.py` starts the autonomous loop.
- `python run_vector.py smoke` runs a one-shot spine check.
- `python run_vector.py api` starts the local FastAPI server.
- startup now bootstraps baseline district agents into `AgentRegistry`.

## Remaining Work

- Prove the default loop can run for 72 hours.
- Add a Windows service or scheduled startup path later.
- Add structured logs to a persistent `vector.log`.

