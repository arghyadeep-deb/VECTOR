# AUTONOMOUS SUPERVISOR READINESS REPORT

Mission: VECTOR DEV ORCHESTRATOR - AUTONOMOUS SUPERVISOR COMPLETION (2026-09-22).
Scope: `tools/vector_dev_orchestrator/**` only. No VECTOR production code, no RG-D2, no
IntentMatcher/JWT work, no V1 engineering, no Windows configuration change, nothing pushed.

## 1. Git

| | |
|---|---|
| Starting HEAD | `d3994e586de5689f4b5d6f1c209b97d65d0ca16d` (`production-hardening-complete`) |
| Bridge commit | `e89f208a83c53393739917d3610ac2abfaadcbf9` - 27 files, all under `tools/vector_dev_orchestrator/` |
| Final HEAD | the docs-only commit that adds this report, directly after `e89f208a8` (`git log -2`) |
| Pushed | no |

The bridge directory was entirely untracked before this mission; it is now tracked. Protected
files (`.claude/settings.local.backup-2026-09-14.json`, `docs/CODEX_VECTOR_V1_HANDOFF.md`,
`docs/VECTOR_FORENSIC_AUDIT_REPORT_2026-09-15.md`, `docs/VECTOR_OS_LONG_TERM_VISION.md`) were
not touched (mtimes predate the mission). Pre-existing unrelated modified files
(`data/council_log.jsonl`, `data/models/neural_policy.*`, `OWNER_ROUTING_CLOSURE_REPORT.md`) were
not staged. The pre-commit gate rejected a UTF-8 BOM in 12 older bridge files; the BOMs were
removed (not bypassed) and the gate then passed.

## 2. Files changed

New: `planner.py`, `supervisor.py`, `supervisor_scenarios.py` (scenarios A-O),
`difficulty_inference.py`, `quota.py`, `.gitignore`.
Modified: `README.md` (rewritten), `models.py`, `state_store.py`, `router.py`, `orchestrator.py`,
`dev_driver.py`, `execution_cycle.py`, `approval.py`, `backlog.py`, `autonomous_worker.py`,
`text_signals.py`. Others in the commit only lost a BOM / were first tracked.

## 3. Planner behaviour (`planner.py`)

Input: goal + repo state (HEAD, branch, dirty files, existing reports under
`VECTOR_TECHNICAL_KNOWLEDGE/`) + accepted-evidence ledger + known blockers. Output: <= `max_packages`
work packages with objective, scope, allowed mutation paths, forbidden scope (safe defaults always
appended), acceptance criteria, relevant tests, behavioural evidence, dependencies, risk/difficulty,
preferred owner (kept only with a stated reason), independent-reviewer policy and stop conditions.

A model (Claude sonnet, read-only tools, strict JSON schema; Codex optional) only *proposes*.
Code decides: required fields; sane paths (rejects root, absolute, `..`, protected owner/audit
files, the bridge itself); scope width cap; dependency DAG (unknown/cyclic dropped, topological order);
duplicate ids; ledger de-duplication (never reopens accepted work, stem-normalised similarity);
known-blocker de-duplication; approval-gate screening (`needs_owner`); difficulty inference.
Read-only is enforced: the working tree is fingerprinted around the proposer call and a change
aborts the plan (`PlannerMutationError`). Review-only packages are rejected (the worker cannot
execute them).

## 4. Difficulty inference (`difficulty_inference.py`)

Every task persists `requested_difficulty`, `inferred_difficulty`, `effective_difficulty` and
`difficulty_reason`. `effective = max(inferred, floor, requested)`. Floors: security/auth (wording or
path segment) -> hard; migrations -> hard; architecture, concurrency/persistence/recovery, external
side effects -> serious. A requested level may raise but never lower a floor. Scope-based inference
(production vs test-only, path/subsystem count, acceptance-critical, vague description) applies only
when structured scope is supplied. Phrase list tightened after the smoke test (a bare "replace the"
falsely floored a task to serious).

## 5. Quota semantics (`quota.py`)

`UNKNOWN / NORMAL / CONSTRAINED / EXHAUSTED` per provider, persisted with source and expiry.
Codex: real local telemetry (`~/.codex/sessions/**/rollout-*.jsonl` `rate_limits`); the live probe
during this mission read NORMAL (1-9% used). Claude: no local telemetry, therefore UNKNOWN unless
the owner sets it or a call reveals a usage-limit error. UNKNOWN reduces no capability.
CONSTRAINED conserves routine implementers only; never review, hard/critical or security work.
EXHAUSTED (telemetry, observed error, or owner) makes work `deferred` with state preserved - the
other provider is never used as a substitute reviewer. Exhaustion expires to UNKNOWN after 6h;
owner-set levels are never overwritten. CLI: `autonomous_worker.py quota show|refresh|set|clear`.

## 6. Run-budget semantics

| | Scheduled maintenance | Owner-started program |
|---|---|---|
| Work | manual backlog only (`next_pending(manual_only=True)`) | that program's packages only |
| Limits | daily cap (3/day in the scheduled command) + max tasks per run | `RunBudget`: max_packages, max_provider_calls, max_correction_cycles, max_elapsed_seconds |
| Interaction | never advances a program | never consumes the daily cap |

Worst-case provider calls (`2 + 2*max_retries`) are checked before a package starts, so no package
is half-run for budget reasons. Exhaustion is resumable via `program extend` (budgets can only be raised).
Continuation is bounded: accepted -> integrated onto `vector-integration` (tests re-run on the merged
tree) -> ledger -> next package cut from `vector-integration`; blocked -> one correction -> retest ->
re-review; same blocker survives -> one re-plan; else `needs_human`.

## 7. Scheduler / worker behaviour

Windows Task Scheduler job "VECTOR Dev Orchestrator Worker" (every 4h, Interactive logon,
`run --integrate --max-tasks 2 --daily-cap 3`, IgnoreNew, 3h limit): **runs only while the owner is
logged in** (documented in the README). Verified deterministically: daily cap and next-day rollover,
STOP file, lock and stale-lock reclaim, circuit breaker, crash fail-closed, provider-exhausted hold,
and program packages neither pulled by nor counted against the scheduled run.

## 8. Restart behaviour

State is written atomically. Verified (scenario H): process death mid-package -> accepted work and
ledger survive, the interrupted package becomes `needs_human` and is not replayed; a package whose
backlog item finished before the supervisor recorded it is reconciled from the item (never re-run);
completed programs/packages never rerun; paused programs stay paused across restart; an unfinished
queued item is reused, never duplicated; a pause requested during a run is honoured between packages.

## 9. Safety boundaries

Autonomy stops (`needs_human`, before any model runs) for destructive owner-data operations,
credential/API-key changes, spending, publishing/pushing/PRs, irreversible external actions, major
product-scope decisions, unresolved high-impact security trade-offs, architecture replacement,
dependency changes and migrations. Ordinary code/test/review/retry needs no approval. Unchanged
invariants: commits only to `vector-dev/*` with the exact file set; never push/merge live/reset/clean
or delete worktrees; no `--dangerously-*`; hooks never bypassed; allowed-path violations block;
reviewers receive spec, accepted baseline, real diff and raw test output plus an explicit instruction
not to defer.

## 10. Tests

- 23 module self-tests (`python <module>.py`) pass, including new `difficulty_inference`, `quota`,
  `planner`, `supervisor`, plus `python -m py_compile *.py`. Re-run after the BOM strip: 23/23.
- Supervisor scenarios (`python supervisor.py`, mocked providers, no quota spent):
  A planner decomposes a program; B under-labelled security task floored; C routine work avoids the
  strongest route; D/E Claude-owned -> Codex review and Codex-owned -> Claude review; F rejection ->
  one correction -> re-review; G persistent blocker -> one re-plan -> stop (call counts hard-bounded);
  H restart; I scheduled cap vs program budget distinct (plus elapsed / provider-call / correction
  budgets); J quota UNKNOWN honest and routes unchanged; K unavailable provider never replaced (also
  mid-task and recovery); L owner-approval work pauses safely and resumes after `skip`;
  N integration failure stops dependents; O Codex new-file sandbox handling; M README covers every
  operating topic. All pass.
- Bugs found and fixed by this work: `lstrip("./")` path normalisation in three modules stripped
  leading dots (`../x` -> `x`, `.claude/x` -> `claude/x`); the review-evidence collector let one large
  diff consume the whole budget.

## 11. Real dual-provider smoke test

Sandbox git repo (`Desktop\V.E.C.T.O.R\_bridge_smoke\vector_smoke_k2qta8jh`, outside the VECTOR repo;
sandbox HEAD unchanged). Codex telemetry NORMAL before the run. Goal: add `clamp` then `lerp`
(dependent) to `mathx.py`. Real Claude read-only planner produced 2 packages with a dependency.

| Package | Implementer | Reviewer | Tests | Result |
|---|---|---|---|---|
| pkg-clamp | codex `gpt-5.6-sol` | claude `sonnet` | pytest exit 0 | PASS, committed, merged to `vector-integration` |
| pkg-lerp | claude `sonnet` | codex `gpt-5.6-sol` | pytest exit 0 (clamp + lerp) | PASS, committed, merged to `vector-integration` |

Both directions ran live under one supervisor; pkg-lerp's baseline was the integration commit
containing pkg-clamp (dependent work built on accepted work); final `vector-integration` holds both
functions. 5 provider calls counted, 0 corrections, ~330 s. The two-provider difficulty was `serious`
because the planner marked the packages acceptance-critical (over-labelling; costs capability, not safety).

Earlier smoke attempts (kept as evidence, all fail-closed) found real problems, since fixed:
1. Codex's Windows elevated sandbox creates NEW files owned by the sandbox account and unreadable to
   the owner -> `PermissionError` crash (program -> `needs_human`, worktree preserved). Modifying
   existing files is fine. Fix: packages whose concrete allowed file paths do not exist are implemented
   by Claude (Codex still reviews); a `PermissionError` crash gets one bounded fallback retry with
   Claude (scenario O).
2. Sandbox repo lacked `.gitignore`, so the guarded commit refused stray `__pycache__` (correct behaviour).
3. A Codex attempt "reported success but changed no files"; the bounded correction handed the package to
   Claude and it passed. Diagnostic capture of the implementer's final message was added.

## 12. Remaining limitations

- Scheduled worker runs only while logged in; asleep/off/logged-out runs are not made up.
- The Codex new-file mitigation (routing + fallback) is proven by scenarios, not yet live; the live smoke
  used existing files. Directory-only allowed paths that hide new files rely on the fallback retry.
- Claude quota is UNKNOWN by nature; Codex telemetry lags slightly.
- A plan is not regenerated on success; large goals need successive programs. Review-only packages are unsupported.
- Planner-labelled `acceptance_critical` inflates difficulty (and Codex usage); tune the planner prompt if it recurs.
- Integration uses each item's own targeted tests on the merged tree, not the whole suite.
- Sandbox folders from the smoke runs remain under `Desktop\V.E.C.T.O.R\_bridge_smoke` and `%TEMP%`
  (evidence; safe to delete).

AUTONOMOUS_SUPERVISOR_READY — V1 HANDOFF READY
