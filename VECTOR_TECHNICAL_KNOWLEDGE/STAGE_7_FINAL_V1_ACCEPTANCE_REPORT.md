# VECTOR V1 — Stage 7: Fresh Integrated Acceptance

Date: 2026-09-22. This is the final stage of the owner-directed V1
completion program (Stages 1-7). It synthesizes real evidence across all
six prior stages — it does not re-summarize old claims, and it does not
let any stage's own self-report stand in for fresh verification here.

**OVERALL V1 VERDICT: PARTIAL COMPLETION.** Five of six technical stages
are genuinely closed (PASS); one (long-horizon autonomy) is honestly
PARTIAL with real, diagnosed evidence gaps, not a failure; and the codebase
implementing all of this is currently split across two unmerged branches —
a real, unresolved integration gap that the owner, not this program, must
resolve before any of this reaches production.

## 1. Stage-by-stage verdicts (fresh-checked, not just relayed)

| Stage | Verdict | Where the code lives |
|---|---|---|
| 1 — IntentMatcher prewarm reliability | PASS | `vector-integration` (bridge, cross-provider reviewed) |
| 2 — RG-D2a policy adaptation | PASS | `vector-integration` (bridge) + live-verified directly |
| 3 — Organic goal progress | PASS | `vector-integration` (bridge) + live-verified directly |
| 4 — Long-horizon autonomy | PARTIAL | No production code (verification-only); 5 real findings documented |
| 5 — Restart/persistence/coherence | PASS | No production code needed; live-verified directly |
| 6 — JWT/authorization closure | PASS | `production-hardening-complete`, **uncommitted**, 3-round adversarial review |

I re-ran the regression suites for every stage just now, on the actual
current state of each branch, not from memory:

- `production-hardening-complete` (working tree, Stage 6's uncommitted
  changes applied): 208/208 passing across
  `test_collections.py`, `test_jwt_auth.py`,
  `test_webauthn_auth.py`, `test_webauthn_middleware_integration.py`,
  `test_owner_routing_closure_f1/f2/f3.py`, `test_v1_trust_t1/t2/t3.py`,
  `test_pre_rgd2_a/c.py`.
- `vector-integration` (HEAD `e175152df5`): 46/46 passing across
  `test_task89c_goal_progress.py`, `test_rr2_meaningful_utility.py`,
  `test_stage3_goal_progress.py`, `test_owner_routing_closure_f1/f2/f3.py`.

Zero regressions found in either branch, this session, right now.

## 2. The real integration gap (do not gloss over this)

**`production-hardening-complete`** (current live branch, HEAD `4ba5ce0e3`)
and **`vector-integration`** (HEAD `e175152df5`, 23 commits ahead of a
common ancestor) currently contain *different, non-overlapping* pieces of
this V1 work:

- Stages 1, 2, 3, 5's bridge-implemented fixes (IntentMatcher, RG-D2a
  reward honesty and observability, goal-progress bridging) exist only on
  `vector-integration`.
- Stage 6's JWT closure exists only on `production-hardening-complete`, and
  is **not yet committed** there (working-tree changes).
- Neither branch has the other's work. Nothing has been merged, and this
  program has not merged them — that decision belongs to the owner, per
  this project's own `POLICY.md` §15 ("never automatically merge into a
  protected/live branch") and the standing rule that `vector-integration`
  promotion to the live branch is never automatic.

This means: **as of this report, no single branch contains the complete,
integrated V1 work.** The owner has at least three real choices, none of
which this program will make unilaterally: (a) merge `vector-integration`
into `production-hardening-complete`, then commit Stage 6's changes on top;
(b) commit Stage 6 first, then merge `vector-integration` on top and
resolve any conflict; (c) review each independently before deciding. This
report recommends option (a) or (b) — both are low-risk (no file overlap
between the two branches' changes, confirmed by inspection) — but does not
perform either.

## 3. Evidence categories (do not collapse these — this is the discipline the whole program was built on)

| Claim | Category |
|---|---|
| Stages 1, 2, 3, 5, 6's code changes | SOURCE IMPLEMENTED. INTEGRATED only within their own branch (see §2 — not integrated *across* branches). TEST VERIFIED (254 total tests across both branches, this session, zero regressions). |
| Stage 2's policy-score adaptation, Stage 3's goal-progress bridge, Stage 5's restart/recovery, Stage 4's partial pursuit | BEHAVIORALLY VERIFIED — real, live, unmocked processes, this session, with printed evidence JSON in each stage's own report. |
| Stage 6's JWT closure | BEHAVIORALLY VERIFIED at the unit/integration level (real `JWTManager`, real middleware function, real token construction) — **not** verified against a live running HTTP server in this stage. Recommended before production promotion: one live `run_vector.py api` smoke test issuing a real collection JWT via `POST /api/collections/{name}/auth-with-password` and confirming a real 401 against a protected endpoint. |
| RUNTIME REACHABLE on the live, deployed system | **NO** for anything in this report — nothing here has been promoted to what the owner actually runs day to day. Every verification ran in an isolated worktree, isolated DB, or isolated PlanStore, explicitly to avoid touching real production data. |
| Full V1 behavioral contract (PRIMARY OBJECTIVE, all 15 sub-claims) | PARTIALLY DEMONSTRATED. Objective understanding/routing (pre-existing, closed by earlier missions), agent/tool invocation (Stages 1-3), action-identity preservation (pre-existing), permission boundaries (all stages, GREEN-only, zero unauthorized executions observed), honest retrieval (pre-existing + Stage 2/3's anti-fabrication work), multi-step execution (Stage 4, partial), failure recognition (Stages 2-5), learning/adaptation (Stages 2, 3, 4), genuine vs. fabricated progress (Stage 3's entire point), multi-step continuity (Stage 4, partial), restart coherence (Stage 5, clean pass), anti-fabrication (every stage's live evidence), owner-authority respect (Stage 6's entire point, plus the bridge's own approval-gate behavior in this program). |

## 4. What this program did NOT do (explicit, per the original directive's own bounds)

- No architecture redesign, no new orchestration framework, no new agent
  hierarchy.
- No public release, no deployment, no push to any remote.
- No promotion of `vector-integration` to the live branch.
- No commit of Stage 6's uncommitted changes (left for the owner to review
  and commit, per the same non-automatic-merge discipline).
- Stage 4's two open, real findings (an undiagnosed `_get_plan_candidates()`
  dependency on a populated `GoalSystem`; `_try_fallback_step()`'s
  unconditional verification-copy onto its replacement step) were
  documented, not fixed — correctly out of this stage's bounded scope.

## 5. Anti-fabrication self-check (required by the original directive)

- Every "PASS" or "PARTIAL" verdict in this program was backed by either a
  printed, real evidence JSON from an actual process run (Stages 2, 3, 4,
  5) or a real, currently-passing pytest count re-verified in this exact
  report (Stages 1, 6, and the cross-check in §1). No verdict rests on a
  model's own prose assertion alone.
- Every real problem found during this program — including problems in
  this program's own work (two escalation paths in the Stage 6 fix, found
  by independent review; five self-inflicted test-harness bugs in Stage
  4, found and corrected honestly; a genuine scheduling gap discovered and
  then found to be a test artifact, not a VECTOR bug) — is recorded, not
  smoothed over.
- No stage was marked PASS to avoid reporting a PARTIAL. Stage 4 stayed
  PARTIAL even after substantial additional effort specifically because
  the owner asked to "finish it completely" — the honest result of that
  effort was richer evidence, not full termination, and this report says
  so plainly rather than rounding up.

---

**V1 STAGES 1-7: COMPLETE, WITH ONE HONEST PARTIAL (STAGE 4) AND ONE REAL
INTEGRATION DECISION LEFT FOR THE OWNER (§2).** This program's work is
done. Merging `vector-integration`, committing Stage 6, and any decision
about production promotion are the owner's next steps, not this program's.
