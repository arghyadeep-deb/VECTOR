# Phase 5 Autonomy Proof — Task 5.1

**Verdict: PASS — the engine is genuinely autonomous, not just functional.**

Test: `tests/integration/test_absorbed_autonomy.py::test_scheduler_fires_hands`
Run: 2026-06-21, `1 passed in 3.72s`

## What this proves and how

The trigger path is **scheduler → callable → hand → memory**, with zero calls
to `HandRunner.run_hand()` anywhere in the test body. A real
`apscheduler.schedulers.asyncio.AsyncIOScheduler` was started, a job
registered with a `'date'` trigger ~1.5s in the future (same registration
primitive `register_all()` uses for cron, just pointed at a near-future
timestamp instead of `vault_sync`'s real "every 6h"), and the test only
`await asyncio.sleep(3.0)`'d — waiting for the *scheduler* to fire it on its
own, exactly as it would in production.

Only `HandRunner._dispatch` (the LLM/governor leaf) was stubbed — for speed
and to decouple this proof from the already-documented, separate Ollama
model-warmth issue (`research_engine.md`). Every other side effect is real,
unstubbed code: episodic persistence, HP award, policy update.

## The actual artifact

```json
// episodic_memory row (event_type="hand_run", source="vault_sync")
{
  "id": "7b5f3304-b282-4a0b-8f2f-008dca26056a",
  "event_type": "hand_run",
  "content": "{\"hand\": \"vault_sync\", \"district\": \"security\", \"output\": \"autonomy proof: vault sync scan complete, no exposures found\", \"status\": \"ok\", \"hp_delta\": 50, \"error\": null, \"started_at\": \"2026-06-20T20:19:05.873992+00:00\"}",
  "tags": "[\"hand_run\", \"vault_sync\", \"security\", \"ok\"]",
  "source": "vault_sync",
  "timestamp": "2026-06-20T20:19:05.873992+00:00"
}
```

```
HP: 500 -> 550.0 (delta=50.0)   // AgentBase.award_points(50, "hand_run:vault_sync"), real, unstubbed
```

```json
// policy_memory row (action_type="vault_sync")
{
  "action_type": "vault_sync",
  "situation_hash": "0138406be925",
  "avg_reward": 1.0,
  "sample_count": 1
}
```

All three closed-loop side effects (episodic, HP, policy) are real, queried
from the actual SQLite tables after the scheduler fired the job — not
mocked, not asserted from in-memory state the test itself constructed.

## What this does and does not close

**Closes:** the autonomy engine itself. The 9 Hands (`hands/registry.py`)
and the ~12 pre-existing cron jobs (2AM reflect, audit verify, daily
review/journal, biometrics, DSPy optimize, etc.) were silently dead —
`_get_scheduler()` returned a prompt/LLM-agent scheduler with no
`add_job`/`schedule`/`register`/`add`, so every registration attempt
no-op'd. Task 1.6 (`apscheduler.schedulers.asyncio.AsyncIOScheduler`) fixed
the root cause; this test proves the fixed path actually fires a hand,
persists a real result, and closes the HP/policy feedback loop — with
nothing prompting it.

**Does NOT close:** that every capability produces real output *on its own
schedule* yet. That's Phase 2 — per-capability live proofs (already done
for `coding_assistant`/`scraper`/`research_engine`/partially `investment`/
`trading`/`intelligence` in `docs/capability_proofs/`), the research
User-Agent provenance scrub (Task 2.0), and the Ollama model-warmth fix
before `research`/`collector`/`predictor`/`trader` actually get scheduled
for real (today they'd reliably fire on time, per this proof — but the LLM
leaf itself is the separate, already-documented open item).

**Honest status:** autonomy engine — shipped and proven. Capabilities —
being brought online one at a time, each with its own live proof.
