# Capability Proof — intelligence

**Verdict: NEEDS-CONFIG (port mismatch with the currently-running shadowbroker instance — not a code defect)**

Run at: 2026-06-20T13:16:28.256420+00:00 — re-confirmed identical after Task
0.5c's temp-DB isolation (this capability never touched `EpisodicMemory` in
the first place, so it was never affected by the DB-contention finding).

## What this tests

`VectorIntelAgent.get_flights(lat=28.6, lon=77.2, radius_km=500)` — calls out
to the shadowbroker OSINT backend (a **standalone service**, confirmed via
`tools/start_shadowbroker.bat` — not loop-governed, matches the plan's own
note in its "Verified findings" section).

## What happened

```
WARNING VectorIntel unavailable: [WinError 10061] No connection could be made
because the target machine actively refused it.
Start: run tools/start_shadowbroker.bat from VECTOR Codebase root
```
(then degraded gracefully to empty-list output, shown below)
```
{'military_flights': [], 'commercial_flights': [], 'tracked_flights': [], 'private_jets': []}
```

## Root cause — isolated

`vectorintel_agent.py` defaults to `VECTORINTEL_HOST=http://127.0.0.1:8002`,
which matches shadowbroker's own documented default exactly (`main.py` line
11698: `PORT = os.environ.get("PORT", 8002)`; `tools/start_shadowbroker.bat`
also sets `PORT=8002`). **The code and its documented default are internally
consistent — this is not a code bug.**

The actual mismatch: a shadowbroker_server process IS already running on
this machine (PID 44996, confirmed via `Get-CimInstance Win32_Process`), but
it's bound to port **8765**, not 8002 (confirmed via `netstat -ano`). That
instance was evidently started with a `PORT` env override from an earlier,
unrelated session — nothing in this work changed that.

## Triage implication

Either (a) restart shadowbroker normally via `tools/start_shadowbroker.bat`
(binds 8002, matches the default `vectorintel_agent.py` expects), or (b) set
`VECTORINTEL_HOST=http://127.0.0.1:8765` to match the instance that's
currently running. Either way, this is a one-line environment fix, not a
code change — `intelligence`'s connector logic and graceful-degradation path
(empty lists instead of a crash) both worked exactly as designed.
