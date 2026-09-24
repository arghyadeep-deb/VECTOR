# plans/ - VECTOR Work Plans

Plans are small task folders executed by dependency order. Context,
requirements, and design should live in source docs rather than being
duplicated across many stale task files.

## Rules For Executing Agents

1. Load one task file at a time.
2. Start a task only when every dependency is already complete.
3. Re-read any design links before changing code.
4. A task is done only when every acceptance check passes.
5. Owner-marked tasks are surfaced to the owner, not executed autonomously.
6. After finishing a task, update the plan index.

## Active Plans

- [`cloud-inbox-brain-bridge.md`](./cloud-inbox-brain-bridge.md): email worker ↔
  brain bridge — Phases 1–2 done, Phase 3 (TS Worker hook) deferred to deploy.
- [`GROWTH_ENGINE_STATUS.md`](./GROWTH_ENGINE_STATUS.md): autonomous growth engine —
  built + tested; remaining items are owner-action (enable flags, IG setup, etc.).

Remaining owner activation/deployment work and the open-issues list live in
[`docs/OPEN_ISSUES.md`](../docs/OPEN_ISSUES.md) (the single owner-facing tracker).
Completed plan folders (production-hardening, audit-remediation, repo-absorption,
vector-activation, post-training, governor-wiring) were executed and removed —
their full detail is preserved in git history. Use
`python run_vector.py readiness-check` for the live readiness gate.

## Creating A New Plan

Copy `TEMPLATE.md` per task. Keep tasks at one day or less; split anything
bigger.
