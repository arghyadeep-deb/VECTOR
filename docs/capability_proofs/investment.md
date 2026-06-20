# Capability Proof — investment

**Verdict: LIVE (Task 0.5c isolation confirmed working — but one new, separate finding below)**

Run at: 2026-06-20T13:11:48.288048+00:00 — with `PID 48532` (the leftover
process from earlier in this session) **still running**, confirming the
temp-DB isolation (Task 0.5c) fully resolves the Phase 0 DB-contention issue
with zero process killing required.

## Output (verbatim)

```
{'status': 'ok', 'ticker': 'AAPL', 'persona': 'buffett', 'result': {'success': True, 'response': "[VECTOR provider_client error: There is no current event loop in thread 'asyncio_0'.]"}}
```

## New finding, surfaced now that the DB error no longer masks it

The pipeline genuinely runs end-to-end (HP was awarded: `+25.0HP`, episodic
memory write succeeded), but the underlying LLM call failed 5 times with
`VectorProviderModel._sync_call: There is no current event loop in thread
'asyncio_0'/'ThreadPoolExecutor-0_0'/...` — and degraded gracefully to a
fallback response that wraps the error text as if it were real analysis
content. This means the Buffett-persona analysis didn't actually run; what
came back is a graceful-degradation placeholder.

This is a **different, separate bug** from the Phase 0 DB-contention finding
(now resolved) — likely `vector_model.py`'s registry calling
`asyncio.get_event_loop()` from worker/executor threads that never had one
set, the same class of problem `agent_base.py::_ensure_legacy_event_loop()`
already handles for the main thread, but apparently not for these executor
threads. **Out of scope for Task 0.5c** (which was specifically about test
isolation, not this). Flagging for a Phase 2 fix sub-task when `investment`
gets actually wired/scheduled — running this capability autonomously today
would silently produce degraded-fallback "analysis" forever without the fix.
