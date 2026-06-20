# Capability Proof — trading

**Verdict: BROKEN (real code bug, NOT the Phase 0 DB-contention issue — that's resolved)**

Run at: 2026-06-20T13:15:45.075547+00:00 — with Task 0.5c's temp-DB isolation
active and `PID 48532` still running. The original Phase 0 finding (SQLCipher
contention) is confirmed fully resolved; this is a new, different, genuine
bug that the DB error was previously masking.

## Output (verbatim)

```
{'status': 'error', 'ticker': 'AAPL', 'date': '2026-06-20', 'error': "[WinError 3] The system cannot find the path specified: ''"}
```

## Investigation (this far, then stopped — out of scope for Task 0.5c)

1. First layer: `ImportError: No module named 'langgraph.checkpoint.sqlite'`
   — missing pip package. **Fixed**: installed
   `langgraph-checkpoint-sqlite==2.0.4`, added to `requirements.txt` (this
   downgraded `aiosqlite` 0.22.1→0.20.0; verified nothing else in
   `requirements.txt` pins a specific `aiosqlite` version — safe).
2. After that fix, hit `WinError 3: cannot find the path specified: ''`.
   Checked `CONFIG["trading"]` — `results_dir`/`cache_dir`/`memory_log_path`
   are all correctly configured with real, non-empty paths under
   `~/.vector/trading/...`. Checked disk — none of those directories had
   ever been created. **Created them** (`logs/`, `cache/`, `memory/`) —
   error persisted identically. This rules out "missing directory" as the
   cause; the empty-string path is being constructed somewhere *inside*
   `core/trading/graph/trading_graph.py` (`VectorTradingGraph`), not from
   the config dict `trading_conductor_agent.py` passes in.

**Stopped here** — this is a real, code-level bug inside the absorbed
trading graph library, distinct from anything Task 0.5a/0.5b/0.5c were
scoped to fix. Needs its own fix sub-task (trace where `VectorTradingGraph`
constructs/joins an empty path — likely a config key the agent's `cfg` dict
doesn't supply but the graph expects, or an internal default that's `""`
instead of `None`) before `trading` can be scheduled autonomously.

## Triage implication

Phase 0's original finding (DB contention) is fully resolved by Task 0.5c.
This capability needs ONE more fix sub-task (the empty-path bug above)
before it's LIVE — scope it in Phase 2 alongside investment's asyncio
event-loop bug (`investment.md`), since both surfaced only after the DB
contention stopped masking them.
