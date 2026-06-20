# Capability Proof — intelligence

**Verdict: ✅ LIVE (2026-06-21) — fixed, confirmed with real data**

## What this tests

`VectorIntelAgent.get_flights(lat=28.6, lon=77.2, radius_km=500)` — calls out
to the shadowbroker OSINT backend (a **standalone service**, confirmed via
`tools/start_shadowbroker.bat` — not loop-governed; the plan's "Verified
findings" section already noted this).

## Fix applied

Root cause (found 2026-06-20): `vectorintel_agent.py` defaults to
`VECTORINTEL_HOST=http://127.0.0.1:8002`, which matches shadowbroker's own
documented default exactly (`main.py`: `PORT = os.environ.get("PORT", 8002)`;
`tools/start_shadowbroker.bat` also sets `PORT=8002`) — the code was never
buggy. The actual mismatch: a shadowbroker_server process was already
running (PID 44996, up since before this session) bound to port **8765**,
not 8002 — started with a `PORT` env override from an earlier, unrelated
session.

Fix: added `VECTORINTEL_HOST=http://127.0.0.1:8765` to `.env` (matching the
already-running instance, rather than restarting an owner-managed long-lived
process unilaterally — chose option (b) from the original triage). Also
fixed `scripts/capability_smoke.py` to call `load_dotenv()` like the real
`run_vector.py` entrypoint does — without that, the standalone test tool's
verdict didn't match production behavior even after the `.env` fix landed.

## Verified live — genuinely real data, not a stub

```
INFO VectorIntel platform connected at http://127.0.0.1:8765
```

Returned ~3.5MB of real, structured, live aircraft-tracking data — genuine
callsigns, ICAO24 hex codes, registrations, lat/lng/altitude/heading/speed,
GPS trails, fuel burn + CO2 emissions estimates. Sample (one private jet,
truncated):

```python
{'callsign': 'a19d64', 'registration': 'N203CK', 'model': 'GLF4',
 'icao24': 'a19d64', 'speed_knots': 453.8, 'alt': 12192.0,
 'heading': 236.87, 'aircraft_category': 'plane',
 'emissions': {'fuel_gph': 330, 'co2_kg_per_hour': 3158.1},
 'trail': [[48.95089, -66.77794, 12184.4, 1781973419],
           [48.89992, -66.8992, 12192.0, 1781973480],
           [48.63098, -67.52958, 12192.0, 1781973719]]}
```

Re-confirmed via `scripts/capability_smoke.py --live intelligence` →
`verdict=LIVE` (the full raw payload is too large for this file — ~3.5MB —
captured separately during manual verification, not committed in full).

## Triage decision (made with owner asleep — flagged for review)

The Phase 2 sub-list asked: map shadowbroker's 34 governed task types to a
scheduled hand, OR document it as a standalone service + health-poll loop.
**Decided: standalone service**, not a hand — it's a long-running,
always-on OSINT backend, not a "run once, produce a report" task the Hand
model fits naturally. **Not done, deliberately deferred**: the health-poll
loop itself, and re-evaluating whether some subset of the 34 task types
*should* become a scheduled hand on top of (not instead of) the standalone
service. This is a real product-shape decision, not just a bug fix — owner
should confirm or override.
