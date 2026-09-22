# Laya Decision Logging — Design Spec

Date: 2026-09-23
Status: Approved (step 2-3 scope only)

## Context

VECTOR uses `tools/vector_dev_orchestrator/` as its Claude/Codex dev bridge: a
deterministic, fully-tested system that alternates implementation ownership
between Codex and Claude (`router.py`), classifies task difficulty/category
by keyword rules, and escalates to a human only for rare safety cases
(`NEEDS_HUMAN`).

Laya (`pip install laya` v0.3.6, already installed, CUDA-verified on the
RTX 5070 Ti) is a 421M-param non-autoregressive decision model: given a
"state" string plus a typed question (`choice`, `score`, `noul`), it returns
a calibrated probability in ~30-40ms. Base checkpoints are near-random
zero-shot — Laya is useless here until fine-tuned on real logged examples.

This spec covers **only** steps 2-3 of the six-step integration plan:
designing the typed-question schemas and building logging so real human
decisions get captured as labeled training examples. Steps 4-6 (adapting the
Kaggle fine-tune notebook, running training, wiring confidence-gated
inference into live decisions) are explicitly out of scope until a real
dataset exists.

## Investigation Findings

The user's original spec assumed the bridge has: (a) a live agent-routing
choice, (b) mid-task multi-option prompts, (c) a task queue with
urgency/complexity scoring, (d) input/content guard screening, (e) a
completion/success signal. Reading the actual orchestrator code showed:

- **Routing is already deterministic** (`router.py: ModelRouter.route()`),
  fully unit-tested (50/50 alternation, category floors, quota conservation,
  escalation ladder). The only human-authored signal is the optional
  `--difficulty` / `--task-category` CLI override on `autonomous_worker.py
  add`, which defaults to the auto-classifier's output when omitted.
- **No mid-task multi-choice prompts exist.** The only human touchpoint is
  binary: `DevOrchestrator.approve_task()` (approve) vs. a `NEEDS_HUMAN`
  item staying blocked (reject/defer).
- **`backlog.next_pending()` is plain FIFO** — there is no urgency or
  complexity scoring in the queue at all today. This is a genuine gap, not
  a reframing.
- **No prompt-injection screening exists inside the orchestrator.** It only
  runs at the outer API boundary (`core/api/routers/commands.py:scan_text`).
  Task descriptions entering the backlog are unscreened.
- **`postflight_guard.py: PostflightPolicy.evaluate()`** already produces a
  deterministic `requires_human` verdict via keyword rules (security,
  migration, permission_gateway, dependency). This is the closest existing
  analog to "completion/success detection."
- **Task history already exists** (`DevTask.notes`, worktree/task state),
  so multi-turn conditioning is a matter of what goes into `state`, not a
  separate build.

## Decision: Reframed Schema Set

Per user approval, the seven originally-requested decisions map to four
concrete logging hooks. Two decisions are reframed to match what the
codebase actually does; one gap (backlog urgency) gets a new but
logging-only field; guard screening is added as a no-op logger.

| Schema | Laya question type | Real hook | State includes |
|---|---|---|---|
| `routing_override` | `choice` (category) + `choice` (difficulty) | `autonomous_worker.py add` | task description, auto-classified category, auto-default difficulty, previous_owner, quota bands |
| `approval_resolution` | `noul` ("should this be approved without further review?") | `DevOrchestrator.approve_task` / persisted `NEEDS_HUMAN` items | task description, task_category, difficulty, postflight reasons that triggered `NEEDS_HUMAN`, task.notes history |
| `task_urgency` | `score` (0.0-1.0) | new `--urgency` flag on `add` (optional, logging-only, not wired into scheduling) | task description, category, difficulty |
| `completion_review_required` | `noul` | `execution_cycle.py` postflight call site | diff summary / files changed, postflight_guard's own deterministic verdict + reasons, actual human resolution once known |

Guard-question screening (schema 5 in the original spec) is designed now
but ships as a **no-op logger**: it runs `guard_questions()`-style checks
against `--description` at `add` time, logs the result, and never blocks
task intake in this pass. Confidence gating (#3) and multi-turn awareness
(#7) are cross-cutting properties of the logging format below, not separate
schemas.

## Logging Design

One new module: `tools/vector_dev_orchestrator/laya_log.py`.

- Append-only JSONL at `tools/vector_dev_orchestrator/.state/laya/decisions.jsonl`
  (sits next to the existing `.state/` dir this package already uses for
  `state_store.py`/backlog persistence — same convention, own subfolder).
- One function: `log_decision(schema: str, state: str, question: str, choice, meta: dict | None = None) -> None`.
  Never raises — a logging failure must not block the orchestrator (matches
  the codebase's existing resilience convention: log and continue).
- Each JSONL row: `{"ts", "schema", "state", "question", "choice", "meta"}`.
  `meta` carries whatever the deterministic system already computed (e.g.
  the auto-classifier's guess) so a later fine-tune script can compute
  "did Laya's prediction match the human" without re-deriving it.
- Four call sites add a single `log_decision(...)` call each:
  1. `autonomous_worker.py`, end of the `add` command handler.
  2. `orchestrator.py`, inside `approve_task()`, and inside
     `mark_needs_human()` for the reject/defer side.
  3. `autonomous_worker.py`, same `add` handler, for the new optional
     `--urgency` flag (skipped entirely if the flag is omitted — no
     synthetic labels).
  4. `execution_cycle.py`, at the existing postflight evaluation call.

No new dependency on Laya's model classes is introduced in this pass —
`laya_log.py` only writes JSONL. Loading Laya to run inference is step 4-6
work, deferred.

## Out of Scope (explicit)

- Running Laya inference against any of these schemas.
- Wiring `--urgency` into `backlog.next_pending()` scheduling.
- Blocking task intake based on guard-question output.
- Fine-tuning, the Kaggle notebook, or a held-out eval set.
- Phase 2 (VECTOR's own internal decision points).

## Testing

Each touched file keeps its existing `if __name__ == "__main__":` self-test
convention. `laya_log.py` gets its own self-test: write a decision, read it
back, assert JSON round-trips, assert a raised exception inside
`log_decision` is swallowed and logged via `loguru` rather than propagated.
