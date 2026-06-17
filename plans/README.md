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

- [`vector-activation/`](./vector-activation/INDEX.md): remaining activation,
  deployment, and owner-triggered work.

Superseded production-hardening and audit-remediation plan folders were
consolidated into [`docs/REPO_STATUS.md`](../docs/REPO_STATUS.md). Use
`python run_vector.py production-check` for the live readiness gate.

## Creating A New Plan

Copy `TEMPLATE.md` per task. Keep tasks at one day or less; split anything
bigger.
