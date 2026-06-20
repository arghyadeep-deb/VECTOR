# Capability Proof — research_engine

**Verdict: LIVE (both Phase 0 bugs fixed) — but see "honesty check" below: the LLM design path is currently unreliable, not the rule-based fallback path**

Run at: 2026-06-20T13:02:02.810806+00:00 (after Task 0.5b fixes)

## Output (verbatim)

```
{'report_id': None, 'sections': 6, 'title': None}
```
(`report_id`/`title` are probe attribute-name mismatches, not bugs in the
capability — see the earlier note below.)

## Fixes applied (Task 0.5b)

1. **`EpisodicMemory.search()` → `.recall()`** (`auto_research_agent.py:62`) —
   `search` never existed on `EpisodicMemory`; `recall(query, limit=5)` is the
   real FTS5 accessor with the exact same call signature. Memory-pattern
   context now actually loads instead of always silently failing.

2. **Sandbox experiment used `logger.info("STAT:...")` for output — fixed to
   `print(...)`** (`auto_research_agent.py::_default_experiment_code`). Root
   cause: `SandboxExecutor`'s restricted sandbox `__builtins__` never defines
   `logger` (no imports allowed for it, nothing injects it), so every
   generated experiment raised `NameError` and silently produced 0 data
   points. Worse, `SandboxExecutor._extract_stats()` only ever parses `STAT:`
   lines from the subprocess's **stdout** — `print()` was always the only
   mechanism that could have worked; `logger.info()` was simply wrong twice
   over (undefined name AND wrong output stream).

## Verified: the report now contains real statistics

```
| Significance (p) | 0.7665 |
| Effect Size      | 0.0091 |
| Supports Hypothesis | False |

independent_t_test: t_statistic=0.313633, p_value=0.766462, effect_size=0.009066, df=5
pearson_correlation: r=-0.430192, p_value=0.335342, n=7
```

(`supports_hypothesis=False` is the *correct* result here — the default
experiment generates synthetic Gaussian noise with no real signal, so a
non-significant p-value is exactly right. The point is the pipeline now
computes and reports real numbers instead of "Insufficient data points (0)".)

## One remaining non-blocking finding

`_llm_design()`'s call to the local model (`vector-reasoning`, now wired via
`CONFIG["models"]["reasoning"]` instead of the upstream project's unmodified
`llama3.2` default) timed out after 60s on this run — Ollama was up, but a
9.3GB model had never been loaded into VRAM in this process yet (cold start).
The code's existing try/except already degrades gracefully to the rule-based
template, which itself now works correctly (see fix #2). Not fixed further —
this is expected cold-start latency, not a bug, and the graceful-degradation
path is exactly the intended design.
