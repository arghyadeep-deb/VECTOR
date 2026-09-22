# VECTOR DEV ORCHESTRATOR - CANONICAL MODEL / TASK ROUTING POLICY

Authoritative policy for autonomous VECTOR development (owner-issued 2026-09-22).
Code must follow this file; if code and this file disagree, fix the code (or ask the
owner to amend this file). `README.md` explains how to operate the bridge;
this file says what the bridge must do. Section 17 maps every rule to its code and test.

## 1. Codex / OpenAI model ladder

| Level | Model | Typical work |
|---|---|---|
| SCOUT | GPT-5.6 Luna | repo scouting, small file inspection, tiny deterministic edits, simple tests, simple docs/config, cheap SCOUT-level review |
| ROUTINE | GPT-5.6 Terra | ordinary implementation, normal bug fixes, localized refactors, moderate test repair, routine review |
| SERIOUS | GPT-5.6 Sol | difficult debugging, substantial implementation, cross-module reasoning, non-trivial integration, state/recovery problems, serious review |
| HARD | GPT-6 Astra (effort low) | architecture-sensitive engineering, difficult integration, concurrency/recovery, difficult security reasoning, high-risk review |
| CRITICAL | GPT-6 Astra (effort medium) | highest-complexity engineering, critical architecture/security, highest-value Codex review |

Do not waste Sol/Astra on trivial work.

## 2. Claude model ladder

| Level | Model | Typical work |
|---|---|---|
| SCOUT | Haiku | exploration, tiny edits, deterministic tests, simple docs/config, cheap SCOUT-level implementation/review |
| ROUTINE | Sonnet | normal implementation, ordinary debugging, features, test repair, localized integration, routine review |
| SERIOUS | Sonnet (high) | difficult debugging, cross-module integration, recovery/state, substantial implementation/reasoning/review |
| HARD | Sonnet (high) | hard engineering, difficult integration, architecture-sensitive work/review, recovery/concurrency reasoning |
| CRITICAL | Opus | critical architecture/security, highest-complexity engineering, strongest Claude-side review |

Do not use Opus as the default coding model.

## 3. Task categories (deterministic classification)

EXPLORATION, DOCUMENTATION, TRIVIAL_EDIT -> normally SCOUT (Luna / Haiku).
IMPLEMENTATION -> normally ROUTINE (Terra / Sonnet).
DEBUGGING -> ROUTINE normally, SERIOUS when genuinely difficult.
TEST_REPAIR -> ROUTINE normally; escalate only on evidence of greater difficulty.
INTEGRATION -> normally SERIOUS (Sol / Sonnet-high).
ARCHITECTURE -> minimum SERIOUS.
SECURITY_SENSITIVE -> minimum HARD.

## 4. Difficulty floors

A category may raise the minimum difficulty; it must never lower genuine difficulty.
ARCHITECTURE >= SERIOUS; SECURITY_SENSITIVE >= HARD. SCOUT+ARCHITECTURE -> SERIOUS,
ROUTINE+SECURITY_SENSITIVE -> HARD, CRITICAL stays CRITICAL.

## 5. Implementer vs reviewer

Implementer and reviewer need not be equally strong. Use the cheapest implementer that is
still appropriate. The independent reviewer is chosen for the UNCONSERVED effective
difficulty/risk and is never weakened because the implementer was cost-conserved.
Pairs: Haiku<->Luna, Sonnet<->Terra, Sonnet-high<->Sol, Sonnet-high<->Astra-low,
Opus<->Astra-medium (either provider may implement; the other reviews).

## 6. Normal 50/50 ownership (healthy quotas)

Task A: Claude implements -> deterministic targeted tests -> Codex reviews -> Claude gets structured
findings, fixes -> tests rerun -> Codex bounded re-review -> verification -> PASS/BLOCKED/NEEDS_HUMAN.
Task B: the same with the providers swapped. Alternate through the existing 50/50 scheduler;
never make one provider permanently the coder and the other the reviewer.

## 7. Bounded model escalation

Codex: Luna -> Terra -> Sol -> Astra low -> Astra medium.
Claude: Haiku -> Sonnet -> Sonnet high -> Opus.
Escalation is controller-owned, deterministic, evidence-triggered, persisted, observable,
quota-aware and bounded (default `max_escalations = 1`). A genuine BLOCKER-level reviewer finding
may justify it. Do NOT escalate for: malformed JSON, missing verdict, CLI bugs, prompt transport,
sandbox configuration, missing temp dir, tooling bugs, Git HEAD movement, approval requirements,
temporary infrastructure failures - fix those at their own layer. No infinite escalation/retry loops.

## 8. Quota policy

| Band | Remaining |
|---|---|
| NORMAL | >= 60% |
| CONSERVE | 30% - 60% |
| RESERVE | 15% - 30% |
| EMERGENCY | < 15% |
| UNKNOWN | no reliable information -> normal deterministic routing unless the owner says otherwise |

NORMAL: normal routing. CONSERVE: prefer cheaper suitable implementers; never weaken required
independent review. RESERVE: keep expensive models for genuinely serious/hard/critical work.
EMERGENCY: do not spend scarce quota on trivial/routine work when another capable provider or
deterministic tooling can do it. Quota changes COST selection, never task complexity or safety;
never downgrade below the capability the task's risk requires; SECURITY_SENSITIVE / HARD / CRITICAL
work is not irresponsibly downgraded to save quota.

## 9. Temporary provider state (owner-declared 2026-09-22; see section 11 for how to lift it)

Codex ~1% weekly quota -> **CODEX = EMERGENCY RESERVE**. Claude refreshed/normal -> **CLAUDE-FIRST**.
Claude handles exploration, reconciliation, implementation, debugging, test repair, ordinary
integration, iterative fixes, documentation for active work, routine reasoning. Deterministic local
tooling handles tests, Git/state checks, changed-file detection, schema validation, static checks.
Do NOT spend Codex on: scouting, documentation, trivial edits, routine implementation, ordinary
debugging, redundant second opinions, smoke tests, repeated reviewer attempts, or anything
deterministic tooling can settle. Reserve Codex for genuinely valuable independent cross-provider
reasoning.

## 10. Independent review during a Codex emergency

Claude never pretends to be Codex. Claude self-review is NOT independent cross-provider review.
If a task needs Codex review but Codex quota should not be spent:
Claude implementation -> targeted tests -> evidence persisted -> **WAITING_REVIEW** (a non-PASS
state); continue other independent eligible work. Never falsely mark PASS. Pending reviews resume
when Codex quota resets.

## 11. When Codex quota resets

When trustworthy information shows Codex has reset, remove the temporary EMERGENCY constraint and
restore task-aware routing + quota-aware routing + normal 50/50 ownership + independent
cross-provider review. Do not remove or rewrite the 50/50 architecture during the Claude-first period.

## 12. Review contract

Independent, structured: `{"verdict": "PASS"|"CHANGES_REQUIRED", "findings": [...]}`, findings keep
severity/file/line/summary. The reviewer gets bounded relevant evidence: task objective,
implementer/model, intended file scope, actual changed files, relevant diff, targeted test command
and result, previous structured findings when applicable. Never infer PASS from prose ("looks good",
"review complete", "no actionable defects"). Malformed/missing structured review -> FAIL CLOSED.
ERROR/BLOCKER findings are never ignored. Reviewer evidence stays bounded, redacted and persisted.

## 13. Development flow (per bounded task)

inspect -> classify category -> effective difficulty -> category floor -> approval gate -> provider
quota state -> choose implementer -> choose independent reviewer -> isolated worktree -> implement ->
detect actual changed files -> targeted tests -> review -> structured findings back to the
implementer -> bounded fix -> retest -> bounded re-review -> final verification -> persist
evidence/state -> PASS / BLOCKED / WAITING_REVIEW / NEEDS_HUMAN. Ordinary engineering failure means
diagnose -> root cause -> fix -> test -> continue; it does not mean stop and ask the owner.

## 14. Human approval gates

Model strength never overrides human authority. Owner approval where policy requires: gated
architecture decisions, security-sensitive authorization, dependency changes needing approval,
database migrations, destructive cleanup, production deployment, credentials/secrets, additional
spending, protected merges, irreversible/destructive operations. No model (Astra, Opus, ...) may
self-authorize a human-gated action.

## 15. Safety

Never automatically: push, merge into a protected/live branch, destructive reset, git clean, delete
evidence-bearing worktrees, bypass permissions or human approval, deploy to production.
Unexpected HEAD movement -> fail closed, preserve evidence, NEEDS_HUMAN where appropriate. Retries and
escalation always bounded; no infinite autonomous loop.

*Interpretation recorded 2026-09-22:* the owner's earlier, explicit design decision (bridge worker)
allows the worker to commit ONLY to isolated `vector-dev/<task_id>` task branches and to merge those
into `vector-integration`; it never commits to, merges into, or pushes the live branch. "Never
automatically commit/stage/merge" is read as applying to the owner's live/protected branch.

## 16. Canonical summary

Codex: SCOUT Luna / ROUTINE Terra / SERIOUS Sol / HARD Astra low / CRITICAL Astra medium.
Claude: SCOUT Haiku / ROUTINE Sonnet / SERIOUS Sonnet high / HARD Sonnet high / CRITICAL Opus.
Floors: ARCHITECTURE >= SERIOUS, SECURITY_SENSITIVE >= HARD. Ownership 50/50, other provider reviews.
Quota: NORMAL >=60, CONSERVE 30-60, RESERVE 15-30, EMERGENCY <15. Now: Codex EMERGENCY, Claude primary.
Escalation bounded/controller-owned/evidence-triggered/quota-aware, max 1. Review independent,
structured, fail closed, strength by unconserved difficulty. Human gates stay human.
Primary principle: cheap models for cheap work, normal for normal, strong for difficult, strongest only
when complexity/risk justifies it; optimise for correctness + independent verification + safety +
bounded autonomy + quota efficiency + truthful completion, not for using every model equally.

## 17. Implementation map (what the code does about each rule)

| Section | Code | Test |
|---|---|---|
| 1-2 ladders | `router.py` `_codex_implementer/_reviewer`, `_claude_implementer/_reviewer` | scenario R part 1 |
| 3 categories, default difficulty | `router.py` `classify_task_category`, `_CATEGORY_DEFAULT_DIFFICULTY`, `default_difficulty_for_category` | scenario R part 2 |
| 4 floors | `router.py` `_CATEGORY_MIN_DIFFICULTY`, `apply_category_floor` | scenario R part 2, `router.py` self-test |
| 5 implementer vs reviewer strength | `ModelRouter.route`: `apply_quota_conservation` touches only the implementer; `choose_reviewer` always uses the unconserved `effective_difficulty` | scenario R part 5 |
| 6 50/50 ownership | `ModelRouter.choose_owner`/`reviewer_for`, persisted `.state/scheduler.json` (`_load_last_owner`/`_save_last_owner`); a forced quota owner does **not** update this state | `orchestrator.py` self-test, scenario R |
| 7 bounded escalation | `DevTask.max_escalations` (default 1), `ExecutionCycle._escalate_for_blocker` (BLOCKER-only trigger) | `execution_cycle.py` self-test |
| 8 quota bands | `router.quota_band_for_percent`, `models.QuotaBand`, `quota.QuotaBoard.band/bands/set_band` (owner-declared band persists, survives telemetry refresh) | `quota.py`, `router.py` self-tests; scenario R |
| 9 temporary Claude-first / Codex EMERGENCY | `ModelRouter.route`: an owner's EMERGENCY band on the scheduled owner (only) flips ownership to the other provider, `ownership_note` records why, scheduler state untouched | scenario R, `orchestrator.py` self-test |
| 10 deferred independent review | `models.TaskStatus.WAITING_REVIEW`/`DevTask.review_deferred`, `ExecutionCycle._defer_review`/`resume_review`, `orchestrator.mark_waiting_review`; worker `backlog.WAITING_REVIEW`, `resume_review_item`/`resume_reviews`; never a same-provider substitute | `execution_cycle.py`, `autonomous_worker.py` self-tests; scenario S |
| 11 lift the constraint | `quota.QuotaBoard.clear`/`set_band`; `AutonomousWorker.resume_reviews` (auto once the band clears) / `--allow-emergency` (owner override); `Supervisor.allow_emergency_review` | scenario S |
| 12 review contract | `ExecutionCycle.build_review_prompt` (`_implementer_line`, `_previous_findings_block`, bounded evidence), `parse_structured_review` (fail closed on malformed/missing), `_MAX_REVIEWER_EVIDENCE_CHARS` | `execution_cycle.py` self-test |
| 13 development flow | `ExecutionCycle.run_once`/`_review_until_pass`/`_finish_reviewed` | `execution_cycle.py` self-test |
| 14 human gates | `approval.py` `ApprovalPolicy` (fail-closed phrase rules) applied in `orchestrator.prepare_task` before any provider call | `approval.py` self-test |
| 15 safety | `autonomous_worker.commit_task_changes` (branch/file-set guard), `git_guard.py` (HEAD-movement fail-closed), `worktree_session.py` (`requires_preservation`) | respective self-tests |
| Quota telemetry (Codex) | `quota.codex_quota_reading`/`codex_quota_probe` (real `rate_limits`, remaining % -> band) | `quota.py` self-test |
