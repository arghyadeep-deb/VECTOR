# Capability Proof — trading

**Verdict: LIVE — fixed and verified 2026-06-21**

## Resolution (2026-06-21)

The `[WinError 3]` reported below did **not** reproduce in this session —
not even before the fixes. Reproducing with a full (non-swallowed)
traceback surfaced two completely different, real bugs that the prior
session's top-level `str(e)` message had hidden:

1. **`core/config.py` `CONFIG["trading"]["llm_provider"]` was hardcoded to
   `"openai"`** while `deep_think_llm`/`quick_think_llm` are Ollama custom
   models (`vector-reasoning`, `vector-focus`). `VectorTradingGraph.__init__`
   → `create_llm_client(provider="openai", model="vector-reasoning", ...)`
   → `ChatOpenAI(...)` → `openai.OpenAIError: Missing credentials. Please
   pass an api_key ... or set the OPENAI_API_KEY ... environment variable.`
   This is a violation of RULE 11 (Ollama is VECTOR's primary local-first
   runtime) — the trading module's own `core/trading/llm_clients/openai_client.py`
   already has full, working `"ollama"` routing (`http://localhost:11434/v1`,
   no API key required — see `api_key_env.py`: `"ollama": None`), it just
   was never selected by default.
   **Fix**: `core/config.py` — `"llm_provider": os.environ.get("TRADING_LLM_PROVIDER", "ollama")`.

2. **`core/trading/graph/setup.py` was missing two imports.** `setup_graph()`
   calls `create_msg_delete()` (lines 59/70/77/84) and `create_trader()`
   (line 91), but neither was imported — they exist and are exported from
   `core.trading.agents` (`agent_utils.py` / `trader/trader.py`
   respectively) and are even already listed in
   `core/trading/graph/trading_graph.py`'s own unused import block, just
   never added to `setup.py`'s `from core.trading.agents import (...)`.
   This raised `NameError: name 'create_msg_delete' is not defined` the
   moment `VectorTradingGraph.__init__` called
   `self.graph_setup.setup_graph(...)`.
   **Fix**: added `create_msg_delete, create_trader` to the import in
   `core/trading/graph/setup.py`.

Both bugs were only reachable once a *third*, already-fixed issue (the
prior session's missing `langgraph-checkpoint-sqlite` dependency) stopped
masking them — consistent with this capability having several
layered/masking bugs, each surfaced only after the one in front of it was
fixed.

The `[WinError 3]` empty-path error from the original investigation below
is presumed to have been an artifact of that earlier broken-import state
(very plausibly `Path("").mkdir()`/`sqlite3.connect("")` somewhere in the
aborted construction path before the dependency fix landed) — it does not
recur now, and the construction path that could have produced it
(`os.makedirs(self.config["data_cache_dir"]/["results_dir"])` in
`trading_graph.py`) was independently re-verified with non-empty,
correctly-populated config values in this session before either fix above
was applied.

## Live verification (verbatim)

```python
agent = TradingConductorAgent()
graph = agent._get_graph()
final_state, decision = graph.propagate("AAPL", "2026-06-21")
```

```
Reddit fetch failed for r/wallstreetbets · AAPL: HTTP Error 403: Blocked
Reddit fetch failed for r/stocks · AAPL: HTTP Error 403: Blocked
Reddit fetch failed for r/investing · AAPL: HTTP Error 403: Blocked
Portfolio Manager: structured-output invocation failed ('NoneType' object has no attribute 'rating'); retrying once as free text
PROPAGATE OK
decision: Overweight
```

Full 11-node pipeline (4 analysts → bull/bear debate → research manager →
trader → 3 risk debators → portfolio manager) ran end-to-end through local
Ollama (`vector-reasoning` + `vector-focus`), no API keys, and returned a
real decision (`Overweight`). The Reddit 403s are sentiment-analyst data
source failures (Reddit blocks unauthenticated scraping) — non-fatal,
already handled gracefully by the analyst's existing fallback. The
structured-output retry on the Portfolio Manager node is also an existing,
working fallback path (free-text retry), not a crash.

## Test suite

`core/trading/tests/` — 149 passed, 1 skipped after the fix (no
regressions). 4 pre-existing failures are unrelated to this bug:
`test_google_api_key.py` (collection error,
`langchain_google_genai`/`langchain_core` version mismatch —
`ContextOverflowError` missing) and `test_api_key_env.py` /
`test_ticker_symbol_handling.py` / `test_ollama_base_url.py`
(`ModuleNotFoundError: No module named 'cli'` — a separate absorbed-CLI
import-path issue, `core/trading/cli` exists but tests import it as a
top-level `cli` package). Neither touched by this fix; both pre-date it.

## Triage implication

`trading` capability is now LIVE. Ready to be scheduled autonomously per
Phase 2 of `plans/wire-absorbed-repos-autonomy.md`.
