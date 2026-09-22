# VECTOR Dev Orchestrator (Claude <-> Codex bridge + autonomous supervisor)

Plain-Python machinery that lets Claude Code and Codex build VECTOR with as little
owner involvement as possible: it plans work, routes each piece to the right model,
implements it in an isolated worktree, has the **other** provider review it
independently, fixes what the review finds (bounded), and records evidence. The owner
only sees the things it cannot decide.

Claude and Codex never talk to each other. A **controller** (this code, no LLM) routes
tasks and passes raw evidence between them.

> If you are a fresh Claude/Codex session asked to "do work through the bridge":
> **queue it (section 4 or 5). Do not implement it yourself.** Then read `status`.

**`POLICY.md` is the authoritative owner policy** for model routing, task categories,
quota bands and the review contract (sections 1-16 there); this README explains how to
operate the bridge. If code and `POLICY.md` disagree, the code is wrong. `POLICY.md`
section 17 maps every rule to the code and test that implements it.

## 1. Architecture (three layers)

```
owner ── starts a PROGRAM (goal) ─────────────►  SUPERVISOR   supervisor.py      (host process, no LLM)
                                                    │  planner.py: read-only, proposes work packages;
                                                    │  code validates them (scope, DAG, ledger, approval gate)
                                                    ▼
scheduled task (every 4h) ───────────────────►  WORKER       autonomous_worker.py (backlog -> run_task -> commit -> integrate)
                                                    ▼
                                                 BRIDGE       dev_driver.py -> orchestrator.py + router.py
                                                    │  route -> approval gate -> isolated worktree
                                                    │  implement -> targeted pytest -> independent review -> bounded fix
                                                    ▼
                                             Claude CLI  /  Codex CLI  (adapters; strict JSON verdicts)
```

- **Host supervisor** = `supervisor.py`. It runs on the Legion (not in a model). It owns
  programs, run budgets, the accepted-evidence ledger, continuation, correction/re-plan and
  restart recovery. It executes packages only through the worker/bridge; it never edits code.
- **Worker** = `autonomous_worker.py`. Drains the manual backlog (scheduled maintenance)
  and executes program packages on the supervisor's behalf. Commits only to `vector-dev/*`.
- **Bridge** = `dev_driver.py` (`run_task`): one bounded task end to end.

How a single task flows:

```
route (difficulty + category + quota) -> approval gate (stops before any model call)
 -> worktree ../.vector_dev_worktrees/<task_id> on branch vector-dev/<task_id>
 -> implementer edits -> allowed-path check -> targeted pytest
 -> OTHER provider reviews (strict JSON verdict, raw evidence, told not to defer)
 -> changes requested & retries left: findings -> fix -> retest -> re-review
 -> PASS: worker commits exactly the changed files to the task branch
 -> integration: merged into `vector-integration` only if tests pass on the merged tree
 -> owner promotes `vector-integration` to the live branch (never automatic)
```

### How Claude and Codex are invoked (do not "simplify" these)

- **Claude**: native `claude` executable, `--safe-mode --setting-sources local`, `--tools Read`
  (review/planning) or `Read,Edit,Write` (implementation), verdict via inline `--json-schema`.
- **Codex**: Windows `.CMD` shim. The prompt is sent on **stdin** (`-`), never argv (cmd.exe
  truncates multi-line arguments). `-c shell_environment_policy.inherit=all`, `--output-schema
  <file>` (strict schema: all properties required, `additionalProperties: false`), `-o` for the
  final message, sandbox `read-only` (review/plan) or `workspace-write` (implement).
- No `--dangerously-*` flags, ever. Hooks/signing/permissions are never bypassed.

## 2. Difficulty, model routing, ownership

Difficulty levels and models (`router.py`). Reviewer = the other provider, same tier.

| Difficulty | Use for | Claude | Codex |
|---|---|---|---|
| scout | tiny test-only / mechanical edits | haiku | gpt-5.6-luna |
| routine | ordinary fix / feature / test repair | sonnet | gpt-5.6-terra |
| serious | cross-module, state/recovery, hard debugging | sonnet (high) | gpt-5.6-sol |
| hard | architecture, complex concurrency, security | sonnet (high) | gpt-6-astra |
| critical | strongest reasoning, used sparingly | opus | gpt-6-astra (medium) |

**Automatic classification** (`difficulty_inference.py`). Nothing has to be labelled correctly.
Each task records `requested_difficulty`, `inferred_difficulty`, `effective_difficulty` and a
plain-language `difficulty_reason`. Inputs: wording (security/auth, architecture,
concurrency/persistence/recovery, migrations, external side effects), and - for planner
packages - the structured scope (files/subsystems touched, production vs tests only, path
count, acceptance-critical, vague/uncertain scope). Safety **floors**: security/auth
-> `hard`, migrations -> `hard`, architecture / concurrency / external effects -> `serious`.
`effective = max(inferred, floor, requested)`: a caller may raise a level but can never
lower a safety floor. Routine work is therefore not sent to the strongest models.

**Ownership**: balanced ~50/50 via persisted scheduler state, not forced literal alternation:
Claude-implemented work is reviewed by Codex; Codex-implemented work by Claude. A planner
package may name a `preferred_owner` only with a stated reason. The reviewer receives the
spec, acceptance criteria, accepted baseline commit, the real diff, the raw test output, the
implementer's identity/model and any previously-resolved structured findings; it is told to
verify independently and not to soften findings. No self-certification.

**Quota bands override the scheduler (`POLICY.md` sec. 8-11).** If the 50/50 scheduler's
choice of owner is in quota `EMERGENCY` while the other provider is not, the OTHER provider
implements instead (a note records this; the scheduler's own alternation state is left
untouched, so it resumes exactly where it was once the constraint lifts). If a provider is
merely `CONSERVE`/`RESERVE`, only its *implementer* tier is capped (never review, never
hard/critical/security work). If the REVIEWER provider is in `EMERGENCY`, the task is never
given a fake or same-provider review: it stops at `waiting_review` after tests pass (see
section 3b) instead of a false PASS.

**Escalation**: at most once per task, one tier up, only after a genuine BLOCKER review
finding (never for malformed output, tooling errors, provider outages or approvals).

## 3. Provider quota (honest states)

Per provider: `UNKNOWN` / `NORMAL` / `CONSTRAINED` / `EXHAUSTED` (`quota.py`, persisted in
`.state/worker/quota.json`).

- Codex: read from its own local telemetry (`~/.codex/sessions/**/rollout-*.jsonl`
  `rate_limits`): EXHAUSTED if a live window is >=97% used, CONSTRAINED if weekly >=70% or the
  5h window >=85%, else NORMAL; stale/absent telemetry -> UNKNOWN.
- Claude Code exposes no local quota telemetry -> **UNKNOWN** (never silently NORMAL) unless the
  owner sets it or a call reveals a usage-limit error.
- Routing under UNKNOWN reduces no capability. CONSTRAINED conserves only routine
  *implementers*; it never downgrades review, hard/critical work or security work.
- EXHAUSTED (from telemetry, an observed usage-limit error, or the owner): every task needs both
  providers (implementer + independent reviewer), so work is held/`deferred` with its state
  preserved. **The other provider is never used as a substitute reviewer.** An exhaustion flag
  expires to UNKNOWN after 6h; an owner-set level is never overwritten automatically.

```
python autonomous_worker.py quota show | refresh
python autonomous_worker.py quota set codex exhausted --reason "weekly limit"
python autonomous_worker.py quota set codex emergency --reason "owner: ~1% weekly"   # POLICY.md band
python autonomous_worker.py quota clear codex
```

`quota set PROVIDER LEVEL` accepts either an availability level (`unknown|normal|constrained|
exhausted`) or, for the POLICY.md conservation bands directly, `conserve|reserve|emergency`
(stored alongside the level; `quota show`/`status` report both `level` and `band`).

### 3b. Deferred independent review (`waiting_review`)

When a task's independent reviewer provider is in `EMERGENCY`, the cycle still implements and
runs the targeted tests, then stops at `waiting_review` — **never a PASS, never committed,
never integrated**, worktree preserved. Nothing pretends to be independent review; the owner's
"Claude never pretends to be Codex" rule (`POLICY.md` sec. 10) is enforced in code.

```
python autonomous_worker.py status                       # "waiting_review": [(item, reviewer, difficulty), ...]
python autonomous_worker.py resume-reviews                # runs every deferred review whose reviewer recovered
python autonomous_worker.py resume-reviews --allow-emergency --max 1   # owner override: spend the reserve anyway
python supervisor.py program run PROGRAM_ID --allow-emergency-review   # same override for a program
```

A scheduled `run` and a program `run` both try `resume-reviews`/deferred reviews first,
automatically, whenever the reviewer's band is no longer `EMERGENCY` — no separate step needed
once the provider recovers. `resume-reviews` re-opens the task's *existing* worktree (never
creates one), fails closed if it changed while waiting, re-runs the targeted tests, then
reviews/fixes/verifies exactly like a normal cycle, hardest-difficulty items first. An
`EXHAUSTED` provider is never spent even with `--allow-emergency`.

## 4. Manual queue (scheduled maintenance)

Commands (run from the repo root, prefix `python tools/vector_dev_orchestrator/`):

```
autonomous_worker.py add --title "Short" --description "..." --test tests/x/test_y.py [--test ...] \
                         --difficulty routine --max-retries 1
autonomous_worker.py status                 # the daily check-in
autonomous_worker.py run --integrate --max-tasks 2 --daily-cap 3
autonomous_worker.py integrate              # merge passed branches into vector-integration only
autonomous_worker.py stop | resume          # STOP file: kill switch / undo
autonomous_worker.py requeue ITEM_ID        # blocked / needs_human / crashed only
```

Good items: explicit pytest targets, one small bounded change naming exact files, what must
stay unchanged, retries 0-3 (each can cost a Codex call - quota is scarce). Add
`--run-ci-gate` only if repo-wide `tools/ci_gate.py` is known green.

The Windows **Task Scheduler** job "VECTOR Dev Orchestrator Worker" runs
`run --integrate --max-tasks 2 --daily-cap 3` every 4 hours. It uses an *Interactive* logon:
**it runs only while the owner is logged in** (not when logged out, and not while the PC is
asleep/off). Missed runs are not made up. Two runs never overlap (worker lock; new instances
are ignored). Disable: `Disable-ScheduledTask "VECTOR Dev Orchestrator Worker"`.

## 5. Autonomous programs (owner-started, supervised)

```
supervisor.py program start --goal "Harden the queue subsystem" [--planner claude|codex] \
              [--max-packages 6 --max-provider-calls 40 --max-corrections 4 --max-hours 6] [--run]
supervisor.py program run    PROGRAM_ID [--max-packages-this-run N]
supervisor.py program status PROGRAM_ID          # packages, ledger, blockers, budget used/remaining
supervisor.py program list
supervisor.py program pause | resume | stop  PROGRAM_ID
supervisor.py program extend PROGRAM_ID --max-packages 8      # budgets can only be raised
supervisor.py program skip | retry  PROGRAM_ID PACKAGE_ID    # owner resolves a needs_human package
```

1. **Plan (read-only).** The planner receives the goal, repo state, existing reports under
   `VECTOR_TECHNICAL_KNOWLEDGE/`, the accepted-evidence ledger and known blockers, and proposes
   <= `max_packages` small packages: objective, scope, allowed mutation paths, forbidden scope,
   acceptance criteria, relevant tests, behavioral evidence, dependencies, risk/difficulty,
   preferred owner (only if justified), independent-reviewer policy, stop conditions. Code
   (not the model) validates each: sane paths (no root/absolute/`..`/protected/bridge files),
   required fields, dependency DAG, difficulty floors, approval-gate screening, and drops
   anything already accepted (never reopens completed work) or matching a known blocker. Each `test_targets` entry must be ONE plain pytest path or node id (`tests/test_x.py`,
   `tests/test_x.py::test_y`); embedded pytest arguments (`-k ...`, several paths, quotes) are
   rejected here, in `backlog.add`, in `run_task` and in the runner. A malformed proposal gets exactly
   ONE repair round (the model is shown the validator's complaint); still malformed -> the plan fails
   closed and nothing runs. The
   planner cannot write: a changed working tree during planning aborts the plan.
2. **Execute** one dependency-ready package at a time through the worker/bridge.
3. **Continue**: accepted -> its branch is merged onto `vector-integration` (targeted tests
   re-run on the merged tree; a conflict/test failure stops the program as `needs_human`) ->
   ledger updated -> the next package is cut from `vector-integration`, so it builds on the
   accepted work (never on stale live HEAD). Blocked -> **one** bounded
   correction (a fresh attempt shown what blocked the last one) -> retest -> re-review. If the
   same blocker survives the correction -> **one** re-plan (planner sees the blocker) -> else
   the program stops as `needs_human`. There are no infinite repair loops.

**Failure evidence.** Every non-pass records bounded (head+tail, ~1.2 KB), secret-redacted
evidence on the backlog item: `category`, `kind`, command, exit code, output tail, top review
findings. `kind` = `implementation` (a correction can help), `test_spec` (pytest usage error such as
exit 4 for a bad target: re-running the same package cannot help, so it goes straight to the single
re-plan) or `infrastructure`. The correction prompt and the re-planner both receive this evidence.
Provider calls are counted as they actually happen (a package stopped at failing tests before the
reviewer counts 1, not 2; a crash is counted conservatively as 2); the pre-start worst-case budget
check is unchanged.

Program statuses: `active`, `paused`, `completed`, `stopped`, `needs_human`,
`budget_exhausted`, `waiting_review` (every runnable package is done or blocked behind a
deferred independent review; never `completed` while this is true). Package states: `planned`,
`running`, `accepted`, `failed`, `needs_human`, `skipped`, `waiting_review`. A package's
dependents stay `planned` (never run) until it is actually `accepted`; independent packages
with no dependency on it continue normally.

### Budgets - two separate systems

| | Scheduled maintenance | Owner-started program |
|---|---|---|
| Scope | manual backlog items only | that program's packages only |
| Limit | daily cap (3/day in the scheduled command) + max-tasks per run | `RunBudget`: max_packages, max_provider_calls, max_correction_cycles, max_elapsed_seconds |
| Cross effects | never advances a program | never consumes the daily cap |

Before starting a package the supervisor checks the worst-case provider calls it could use
(`2 + 2*max_retries`) against the remaining budget, so a package is never half-run because the
budget ran out. Budget exhaustion is resumable after `extend`.

## 6. Task states and what to do

| Backlog status | Meaning | Action |
|---|---|---|
| pending | waiting | none |
| running | worker is on it | none |
| passed | tests + independent review passed; committed on `vector-dev/<task_id>` | integration picks it up |
| blocked | tests failed / review rejected past retries / provider failed | read `result_note` and `.state/tasks/<id>.json`; fix spec; `requeue` |
| needs_human | approval gate, risky files, HEAD moved, scope violation, or interrupted | owner decides; never auto-replayed |
| crashed | exception; worker stopped (fail closed) | inspect, then `requeue` |
| deferred | a provider is EXHAUSTED, or both providers are in quota EMERGENCY; waiting, state preserved | nothing; reactivates when the provider is usable |
| waiting_review | implemented, tests passed; independent review deferred (reviewer provider in EMERGENCY) | nothing until the reviewer recovers, or `resume-reviews`/`--allow-emergency` |
| superseded | terminal and inert: another accepted item delivered the same work (`autonomous_worker.py supersede ID --by ...`) | none |
| passed, no commit | PASS but worktree had unexpected files | inspect the worktree |

`status` also lists `integration_flags` (`conflict` / `tests_failed`) and per-provider quota.

## 7. What requires owner approval (autonomy stops)

Ordinary code, tests, review and retries never need approval. The approval gate
(`approval.py`, negation-aware: "Do not deploy" is fine) stops a package/task as `needs_human`
**before any model runs** for: destructive owner-data operations (rm -rf, delete
backups/vector_memory), credential/API-key changes, spending or purchases, public
deployment/publishing, any push/PR/merge to a shared branch, irreversible external actions
(email, posts, payments), major product-scope decisions, unresolved high-impact security
trade-offs (weakening permission gateway/authentication), architecture replacement,
dependency changes, migrations. Do not reword a genuinely risky task to slip past the gate.
A program with such a package pauses as `needs_human`; `skip` it (dependents are skipped) and
`resume`, or do it yourself.

## 8. Restart recovery, pause and stop

- All program/backlog/quota state is written atomically under `.state/`.
- After a crash or restart nothing is replayed blindly: a package interrupted mid-run becomes
  `needs_human`; a package whose backlog item already finished is reconciled from that item
  (never re-executed); `completed` programs and `accepted` packages never rerun; `paused` and
  `stopped` programs stay so; an unfinished queued item is reused, never duplicated.
- `program pause|stop` is honoured between packages (the in-flight package finishes).
  `autonomous_worker.py stop` writes the global `STOP` file: nothing new starts until `resume`.
- Stale worker lock (>4h, refreshed by a live run) is reclaimed automatically.

## 9. Where things live (logs and evidence)

- `.state/worker/`: `backlog.json`, `notifications.jsonl` (`attention` = a human is needed),
  `quota.json`, `last_run.json`, `STOP`, `worker.lock`
- `.state/supervisor/programs/<id>.json`: goal, packages, ledger, blockers, budget/usage
- `.state/tasks/<task_id>.json`: routing, difficulty provenance, notes, tests, reviewer verdicts
- `../.vector_dev_worktrees/`: one worktree per task + `_integration`. **Evidence: never delete.**
- Branches: `vector-dev/<task_id>`, `vector-integration`. `.state/` is git-ignored.

## 10. Safety rules enforced in code (do not weaken)

- Commits only to `vector-dev/*`, only the task's reported files, only if the worktree holds
  exactly those files. Never pushes, resets, cleans, merges into the live branch, or deletes
  worktrees/branches. Promotion: `git merge --no-ff vector-integration` by the owner.
- Implementer edits outside `allowed_paths` -> blocked (`SCOPE VIOLATION`), worktree kept.
- Unexpected git HEAD movement -> stop, `needs_human`. Risky changed files -> `needs_human`.
- Review output must be the strict JSON verdict; missing/malformed/conflicting ->
  `CHANGES_REQUIRED`. Positive prose is never PASS.
- Stops on a crash, 2 consecutive failures, the daily cap, provider exhaustion or a STOP file.

## 11. Known limits

- The scheduled worker runs only while the owner is logged in (see section 4).
- Claude quota is UNKNOWN by nature; Codex telemetry lags the true state slightly.
- A program's plan is bounded by `max_packages` and does not re-plan on success; extend the
  goal with a new program. Review-only packages are not executable through the worker.
- **Codex cannot safely create NEW files on this Windows setup** (elevated sandbox): files it
  creates are owned by the sandbox account and unreadable to the owner, which crashes the
  bridge (`PermissionError`, fail closed). Modifying existing files is fine. The supervisor
  therefore has Claude implement any package whose concrete allowed file paths do not exist
  yet (Codex still reviews), and gives a `PermissionError` crash one fallback retry with Claude
  as implementer. Manual backlog items that make Codex create new files will crash: prefer
  `--difficulty` choices that Claude implements, or make the target file exist first.
- Codex's default sandbox blocks network, so a *Codex session* cannot start the bridge unless
  the owner approves the command with network + write access to the worktree folder.
- The bridge dir must be committed for task worktrees to contain it; the worker itself always
  runs from the main checkout.
- The machine has hit memory exhaustion from stale processes; a killed run leaves the item
  `needs_human` and the worktree intact.

## 12. Tests

Every module ends with a self-test: `python <module>.py` (no provider calls). Supervisor
scenarios A-S: `python supervisor.py` (or `python supervisor_scenarios.py A F G`); R covers the
canonical routing policy (ladders, floors, quota bands, Claude-first ownership flip), S covers
`waiting_review` end to end (deferred, resumed, budget-respecting, restart-safe). Run everything
after any change, plus `python -m py_compile *.py`. Modules: text_signals, models, state_store,
approval, difficulty_inference, quota, claude_adapter, codex_adapter, git_guard, runner, router,
postflight_guard, orchestrator, task_queue, worktree_manager, execution_cycle, worktree_session,
dev_driver, backlog, integration, autonomous_worker, planner, supervisor.
`PLAN.md` is the original V0 plan. `POLICY.md` is the authoritative owner routing policy.
