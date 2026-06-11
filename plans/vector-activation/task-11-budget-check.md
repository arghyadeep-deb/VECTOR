# Task 11 — Budget sanity after 24h always-on

- **Depends on:** Task 08
- **Who:** me
- **Effort:** ~10 min

## Objective

Confirm Ollama-primary routing holds under autonomous load: cloud spend ≈ ₹0,
no agent burning provider credits in a loop.

## Implementation

Read `core/metering/budget_meter.py` per-agent totals for the first 24h;
cross-check provider dashboards (post-rotation keys) for unexpected usage.

## Acceptance

- [ ] Cloud provider spend ≈ 0 for the period
- [ ] No agent with anomalous call volume
- [ ] Any cloud calls map to explicit fallback events in the log
