# Architecture Decisions Index

> Individual ADRs live in `docs/adr/`. This file is the index and template.
> Every significant decision gets documented to prevent contradictory suggestions.

---

## Decision Log

| # | Title | Date | Status |
|---|-------|------|--------|
| 0001 | [Local-first, no cloud runtime](docs/adr/0001-local-first-no-cloud-runtime.md) | 2026 | Accepted |
| 0002 | [Darwinian HP over static agents](docs/adr/0002-darwinian-hp-over-static-agents.md) | 2026 | Accepted |
| 0003 | [Permission Gateway as only action interface](docs/adr/0003-permission-gateway-only-action-interface.md) | 2026 | Accepted |
| 0004 | [VectorCode replaces legacy comms layer](docs/adr/0004-vectorcode-replaces-legacy-comms-layer.md) | 2026 | Accepted |
| 0005 | [One Ollama model at a time](docs/adr/0005-one-ollama-model-at-a-time.md) | 2026 | Accepted |
| 0006 | [SQLite not PostgreSQL for local runtime](docs/adr/0006-sqlite-not-postgres-for-local-runtime.md) | 2026 | Accepted |
| 0007 | [JWT authentication with refresh tokens](docs/adr/0007-jwt-authentication-with-refresh-tokens.md) | 2026-08-06 | Accepted |

---

## Template

Copy this for new ADRs. Filename: `NNNN-short-title.md`

```markdown
# ADR-NNNN: Title

**Date:** YYYY-MM-DD

**Status:** Proposed | Accepted | Deprecated | Superseded

## Problem

What needed to be solved.

## Context

Relevant technical and business constraints.

## Options Considered

### Option A: [Name]

Description.

Pros:
- ...

Cons:
- ...

### Option B: [Name]

Description.

Pros:
- ...

Cons:
- ...

## Decision

What was chosen and why.

## Tradeoffs

What was gained and what was sacrificed.

## Consequences

- ✅ Positive outcomes expected
- ❌ Known downsides accepted
- ⚠️ Risks to monitor

## Future Implications

How this affects future decisions. What would need to change to revisit this.

## Related

- Links to other ADRs, rules, or docs
```

---

## Decision Principles

1. **Document before implementing** — decisions without ADRs get lost
2. **One decision per ADR** — atomic, reviewable
3. **Include rejected alternatives** — prevents re-litigation
4. **State tradeoffs explicitly** — nothing is free
5. **Link to rules** — connect decisions to `.claude/rules/*`
6. **Review quarterly** — decisions decay; revisit during planning

---

## Upcoming Decisions Needed

Resolved in code but never written up as ADRs (candidates to record):

- Gap 4 (`core/memory/counterfactual.py`) and Gap 6 (`core/memory/causal_graph.py`, SQLite-backed) are implemented
- Dashboard: the `frontend/` HUD (served at `/hud/`) replaced the Next.js/Streamlit plan; `dashboard/src` does not exist
- Cloud deployment: Cloudflare Worker + D1 + KV is live (`api/wrangler.toml`); Fly.io was dropped

Still open:

- OpenMythos: training pipeline architecture (verify `train.py` exists first)
- Runtime inference policy: ADR 0001 says local Ollama only, but the code routes non-sensitive tasks to pooled free cloud keys (`core/inference/route_policy.py`, owner decision 2026-07-08) — needs a superseding ADR
