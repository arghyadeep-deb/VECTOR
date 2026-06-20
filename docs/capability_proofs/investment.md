# Capability Proof — investment

**Verdict: LIVE (event-loop bug fixed, 2026-06-21 — real LLM-backed analysis confirmed)**

## Fix (2026-06-21)

Root cause confirmed: `VectorProviderModel._sync_call()` in
`districts/investment/vector_finagent/agents/finagent_core/registries/vector_model.py`
called `asyncio.get_event_loop()` directly. `_sync_call` always runs inside a
`ThreadPoolExecutor` worker thread — every district agent that reaches it
(`finagent_agent.py`'s `investor_analysis`/`corporate_finance`/
`alpha_discovery`/`geopolitics_analysis`/`quant_backtest`, and
`trading_conductor_agent.py`'s `run_analysis`) dispatches its blocking work
via `loop.run_in_executor(None, _run)`. On Python 3.10+, worker threads never
get an event loop set on them automatically, so `asyncio.get_event_loop()`
there raised `RuntimeError: There is no current event loop in thread
'asyncio_0'/'ThreadPoolExecutor-0_0'/...` every single time — and
`_sync_call`'s except-clause swallowed it into a fallback placeholder string
that looked like real (degraded) analysis content.

**Fix applied:** added a `VectorProviderModel._ensure_legacy_event_loop()`
static method (mirrors the already-established house pattern in
`core/city/agent_base.py::_ensure_legacy_event_loop()`) and call it at the
top of `_sync_call()`, right before `asyncio.get_event_loop()`. It creates
and sets a fresh event loop on the current thread if `get_event_loop()`
raises `RuntimeError`. No other code path needed changes — `core_agent.py`'s
own `asyncio.get_event_loop()` call (inside `_connect_mcp_servers`, used only
when `config["mcp_servers"]` is non-empty) is never reached from
`finagent_agent.py` today, since no caller populates `mcp_servers`.

## Output (verbatim, live run 2026-06-21, ticker=AAPL, persona=buffett)

The event-loop crash is gone. The call now produces a complete, real,
multi-section LLM-generated investment report (routed through the
provider_client fallback chain — groq/github_models 404'd on the
`vector-focus` model name as expected, then succeeded via Ollama):

```
{'status': 'ok', 'ticker': 'AAPL', 'persona': 'buffett', 'result': {'success': True, 'response': '# PROFESSIONAL INVESTMENT REPORT & RECOMMENDATION\n\n**Company:** Apple Inc. (AAPL)\n**Ticker:** AAPL\n...\n### **FINAL INVESTMENT RECOMMENDATION: BUY (Strong Conviction)**\n...'}}
```

(Full response is ~4,500 chars covering business overview, financial
analysis table, risk assessment, and final recommendation — truncated here
for brevity; the placeholder string
`"[VECTOR provider_client error: There is no current event loop in thread"`
no longer appears anywhere in the output.) HP was awarded
(`+25.0HP`, `500->525.0`) and episodic memory write succeeded, same as
before — but now backing real analysis content instead of a degraded
fallback.

## Regression tests

- `tests/integration/test_capability_live.py::test_vector_provider_model_sync_call_survives_worker_thread_with_no_loop`
  — fast, deterministic unit test (ProviderClient.chat stubbed) that
  reproduces the exact worker-thread conditions that triggered the
  `RuntimeError` and asserts it's gone.
- `tests/integration/test_capability_live.py::test_finagent_investor_analysis_does_not_hit_event_loop_error`
  (`@pytest.mark.live`) — full end-to-end real-LLM regression proof via
  `FinAgentAgent.run()`.

## Known unrelated finding (not fixed here, not blocking)

`provider_client`'s `groq` and `github_models` cloud routes 404/400 on the
literal model name `vector-focus` (these providers don't recognize VECTOR's
internal model aliases) before falling back to Ollama — this is a pre-existing,
separate model-name-mapping gap in `core/inference/provider_client.py`'s
cloud routing, not the asyncio bug, and not in scope for this fix. The
fallback chain still works correctly (Ollama succeeds), so it's not currently
blocking real output, just adding latency via 2 failed attempts per call.
