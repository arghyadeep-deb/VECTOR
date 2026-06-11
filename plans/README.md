# plans/ — VECTOR work plans (Grove-format pilot)

Each plan is a folder of small task files executed strictly by dependency.
Context, requirements, and design are NOT duplicated here — they live in
`brain/VECTOR/` (Architecture.md, Decisions/, Districts/) and are linked from
task files when needed.

## Rules for the executing agent

1. Load ONE task file at a time. Do not preload the whole plan.
2. A task may start only when everything in its `Depends on:` line is green.
3. Before starting, re-read any `Design:` links in the task file.
4. A task is done only when every Acceptance checkbox passes — run the checks,
   don't assert them.
5. Owner-marked tasks (`Who: OWNER`) are never executed autonomously; surface
   the copy-paste command and wait.
6. After finishing a task, tick its row in the plan's `INDEX.md`.

## Active plans

- [`vector-activation/`](./vector-activation/INDEX.md) — remaining activation,
  deployment, and security-closeout work (2026-06-11).
- [`vector-production-hardening/`](./vector-production-hardening/INDEX.md) — task-wise
  hardening plan for production/JARVIS-readiness issues (2026-06-11).

## Creating a new plan

Copy `TEMPLATE.md` per task. Keep tasks ≤1 day of work; split anything bigger.
