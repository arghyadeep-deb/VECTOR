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

## Honesty check (added after review feedback) — design_source assertion

Owner feedback, correctly: "graceful degradation silently becomes permanent
degradation" if the LLM path never actually succeeds once this is scheduled
autonomously — a capability could be "LIVE" forever while quietly only ever
producing rule-based filler. Two actions taken:

1. Confirmed `ollama list` actually has `vector-reasoning` installed (9.3GB,
   present). The model genuinely exists — this isn't a missing-model issue.
2. Added `ExperimentDesign.design_source` (`"llm"` or `"rule_based"`) and a
   new assertion in the live test
   (`test_research_engine_full_cycle_produces_real_statistics`) that fails
   loudly if a run's output came from the fallback, not the model. This is
   the honesty mechanism the feedback asked for.

**That assertion is currently FAILING — for real, currently-true reasons:**

- First measured cold-load (model not in VRAM at all): ~58s for a *trivial*
  one-word prompt — almost entirely load time, not inference.
- Bumped `_llm_design()`'s httpx timeout 60s→120s to give real margin.
- Re-ran moments later, expecting a now-"warm" model (`OLLAMA_KEEP_ALIVE=30m`
  is configured) — instead measured **133s**, *longer* than the cold load,
  and the live test's actual run timed out again even at 120s.

**This means the model is not staying warm between calls despite
`OLLAMA_KEEP_ALIVE=30m`**, which is a real, currently-active problem bigger
than "tune one timeout." Likely cause: `OLLAMA_MAX_LOADED_MODELS=1` (per
project config) means any *other* model load on this machine — and a lot
has been running across this long session — evicts `vector-reasoning`,
forcing a fresh ~60-130s reload on the next call. Not investigated further
here (out of scope for this fix pass) — flagging as its own item, separate
from Task 0.5b, before `research` gets scheduled autonomously in Phase 2:
a hand that calls this every N minutes while other Ollama traffic exists on
the same machine will reload constantly and may regularly exceed even a
generous timeout, falling back to rule-based design every single run —
exactly the "LIVE but hollow one layer up" failure mode the feedback warned
about, now caught by a real, currently-failing assertion instead of papered
over.
