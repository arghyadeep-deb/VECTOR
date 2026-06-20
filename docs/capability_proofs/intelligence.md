# Capability Proof — intelligence

**Verdict: ✅ LIVE (2026-06-21) — fixed via option (b) below, confirmed with real data**

Fix applied: added `VECTORINTEL_HOST=http://127.0.0.1:8765` to `.env` (option
(b) from the triage below — the running shadowbroker instance wasn't
restarted, since it's a long-lived process up since before this session and
restarting an owner-managed service unilaterally isn't appropriate). Re-ran
`VectorIntelAgent.get_flights(lat=28.6, lon=77.2, radius_km=500)`:

```
INFO VectorIntel platform connected at http://127.0.0.1:8765
```

Returned ~3.5MB of real, structured live aircraft-tracking data — genuine
callsigns, ICAO24 hex codes, registrations, lat/lng/altitude/heading/speed,
GPS trails, fuel burn + CO2 emissions estimates. Sample (private jet):

```python
{'callsign': 'a19d64', 'registration': 'N203CK', 'model': 'GLF4',
 'icao24': 'a19d64', 'speed_knots': 453.8, 'alt': 12192.0,
 'emissions': {'fuel_gph': 330, 'co2_kg_per_hour': 3158.1},
 'trail': [[48.95089, -66.77794, 12184.4, 1781973419], ...]}
```

This is genuinely real-time OSINT data, not a stub. `intelligence` is LIVE.

---

## Original finding (2026-06-20), preserved for context

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
