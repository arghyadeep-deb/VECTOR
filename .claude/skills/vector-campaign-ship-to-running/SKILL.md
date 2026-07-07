---
name: vector-campaign-ship-to-running
description: Load to run the decision-gated campaign for VECTOR's HARDEST LIVE PROBLEM — getting it from "built and tested" to "running as a supervised service and surviving a 14-day burn-in." Numbered phases, exact commands, expected observations, branch points. Triggers: "get VECTOR running", "install and stabilize", "burn-in", "why won't it stay up", "ship to running", "the campaign", "24/7".
---

# CAMPAIGN: Ship VECTOR to Running

The single hardest live problem (confirmed across every session + three harness
analyses): VECTOR is ~90% built and has NEVER run as a service. The binding
constraint is operation, not capability (`plans/strategy/life-work-strategy.md` #5).
This is an executable, decision-gated campaign. Follow phases in order; at each
GATE, compare the real observation to EXPECTED and branch. Success is MEASURED,
never eyeballed, and lands through VECTOR's change control.

## When NOT to use this skill
If VECTOR is already running stably, use `vector-run-and-operate` for day-to-day.
For a specific crash use `vector-debugging-playbook`.

## Pre-flight (must pass before Phase 1)
```
python scripts/smoke_test.py          # EXPECTED: Smoke tests: 38/38 PASS
python scripts/integration_check.py   # EXPECTED: ALL WIRING VERIFIED (51/51)
python .claude/skills/vector-diagnostics-and-tooling/scripts/health_snapshot.py  # EXPECTED: SNAPSHOT: OK
```
If any FAIL → fix first (`vector-debugging-playbook`); do not proceed.

## Phase 1 — Run the loop in the foreground (prove it starts)
```
python run_vector.py --mode loop
```
EXPECTED: startup logs, `agents_registered > 0`, observe/think ticks begin, no
immediate traceback. Let it run 10 minutes.
- GATE 1a: `agents_registered == 0` → the bootstrap regression is back
  (`run_loop()` must call `bootstrap_agents()`); branch to debugging-playbook.
- GATE 1b: a coroutine traceback in logs → note which loop; the loop should
  catch+backoff, not die. If the process exits → that's the bug to fix.
- GATE 1c: runs 10 min clean → proceed to Phase 2.

## Phase 2 — Install as a supervised service (survives crashes + reboot)
```
# ADMIN PowerShell:
powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1
Get-Service VECTOR        # EXPECTED: Status Running
```
- GATE 2a: script errors on `--mode` → confirm it passes `loop` not `autonomous`
  (historical bug, fixed 2026-06). 
- GATE 2b: NSSM download blocked → cache `nssm.exe` at `data/tools/` manually.
- GATE 2c: service Running → kill the python child; EXPECTED: NSSM auto-restarts
  it within seconds. If not → AppExit/restart config wrong.

## Phase 3 — 14-day burn-in (the real test; this is where the true last 10% lives)
Daily:
```
python scripts/check_soak.py          # loop alive, no dead coroutines
ls -lh vector_memory.db               # EXPECTED: stays < ~200MB; NOT climbing to GBs
python core/memory/multi_db_manager.py  # cloud sync healthy (Supabase/Turso/D1)
```
- GATE 3a: DB climbing toward GBs → the context_budget FTS-dump bug; DROP+CREATE
  the FTS table + stop the dump (`vector-debugging-playbook`, `failure-archaeology`).
- GATE 3b: a coroutine silently dead (soak reports it) → that loop swallowed an
  exception without backoff; fix the handler.
- GATE 3c: memory quota/cost drift → check the quota ledger
  (`~/.vector_ca/metering/provider_quota.json`); a provider stuck saturated.
- GATE 3d: 14 days, loop alive, DB bounded, cloud synced, no owner-facing errors
  → SUCCESS. Promote (below).

## Solution menu for "won't stay up" (ranked, with the obligation for each)
1. **Unhandled exception kills a coroutine** (most likely) — every loop coroutine
   must `try/except Exception → log → asyncio.sleep(backoff)`. OBLIGATION: show the
   traceback + the exact coroutine before patching.
2. **Blocking call stalls the loop** — a sync call (screen/face/DB) not wrapped in
   `asyncio.to_thread`. OBLIGATION: prove which call blocks (timing/log).
3. **Memory bloat OOM/slowdown** — the FTS dump. OBLIGATION: measure DB size trend.
4. **Model routing hard-fails** — a provider 4xx not falling through to ollama.
   OBLIGATION: prove the chain didn't terminate on ollama.

## Known WRONG paths (fenced off — do not)
- Do NOT "fix" instability by disabling loops/senses wholesale — that's hiding the
  bug, not fixing it. Find the failing coroutine.
- Do NOT increase timeouts to mask a blocking call — wrap it in a thread.
- Do NOT delete memory to shrink the DB — DROP+CREATE the FTS index (DELETE only
  tombstones; see failure-archaeology).

## Validation & promotion (through change control)
Success = MEASURED: 14 days, `check_soak` green daily, DB bounded, cloud 4/4,
zero owner-facing errors. Record the burn-in result in
`plans/FABLE5-MASTER-HANDOFF.md` EXECUTION LOG + a memory file. Only then flip
`repo_maintenance` / expand trust-ladder autonomy. Never declare "stable" by eye.

## Provenance and maintenance
2026-07-07. Pre-flight commands verified this session (smoke 38/38). Service +
burn-in phases are `[UNVERIFIED-CMD: require a running box + admin + 14 days]` —
they are the campaign to RUN, not claims that it's done. Ties to
`run_vector.py`, `scripts/install_service.ps1`, `scripts/check_soak.py`.
