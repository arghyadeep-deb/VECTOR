# Task 89 — Agent E Independent Red Team Review

## OVERALL VERDICT: BLOCKED

**Not because the described changes are unsafe. Because none of them exist in this source
tree.** The task briefing describes R1 (governor async routing), R2 (event-fanout cooldown),
R3 (goal-progress double-increment fix), and R4/R5 (policy hash unification + suppression
channel) as "already manually integrated" by a lead agent into "the current source tree,"
verified by 268 passing tests. I read every file named in the brief directly, plus git
history and the sibling worktree ancestry. **All five remediations are absent.** Nothing in
this tree matches the diffs described. This is not a subtle regression to triage — it's an
empty integration. I cannot pass or partially-pass a safety review of code that was never
written, so this is a hard BLOCK on the claim "R1–R5 are integrated and safe," reported
factually rather than patched (per my instructions as reviewer, not implementer).

This finding supersedes items 1–15 below in importance. Each item is still answered against
the **actual current source**, with an explicit note on whether the relevant tonight's-change
exists.

---

## Primary finding: the integration does not exist (evidence)

Checked directly, by string/definition search across the whole worktree unless noted:

| Claimed artifact | Expected location | Found? |
|---|---|---|
| `route_task_async`, `asyncio.to_thread(self._llm_classify, ...)` | `core/city/governor.py` | **No** — zero matches repo-wide. `Governor.dispatch()` (line 1877) still calls `self.route_task(task_type)` synchronously (line 1884), unchanged from before any claimed R1 work. |
| `_FANOUT_EDGE_COOLDOWN_SEC`, `_fanout_edge_last_fired`, `_fanout_edge_should_fire` | `core/loop/autonomous_loop.py` | **No** — zero matches repo-wide. |
| `FANOUT_EDGE_COOLDOWN_SEC` config field | `core/config.py` | **No** — zero matches. |
| `strategy::review_analytics_insights` removed from `EVENT_TRIGGER_MAP[ANALYTICS_READY]` | `core/event_bus/wiring.py` | **No** — still present at line 151: `("strategy", "review_analytics_insights", {...})`, and `"strategy": {EventType.ANALYTICS_READY, ...}` still in `DISTRICT_SUBSCRIPTIONS`-equivalent at lines 71–74. Independently confirmed `strategy` is not a district in `config/agent_manifest.yaml` (zero hits) — so this dangling fan-out target is real, but it's a **pre-existing** condition R2 was supposed to fix, not something tonight introduced. |
| Goal-feedback-loop `update_goal_progress()` call replaced with `logger.debug()` | `core/loop/autonomous_loop.py` | **No** — `update_goal_progress` still called live at line 1132, the only call site in the file. |
| A second "Goal progress on completion" site inside plan-step execution (`if completed and plan.goal_id: ...`) | `core/loop/autonomous_loop.py` | **No** — does not exist. Only one `update_goal_progress` call site exists in this file, period. The brief's claim that the lead found and fixed a *second* site is false; there is no second site to have found. |
| `make_situation_hash()` `(action_type, params)` `"v2:"` overload | `core/memory/policy.py` | **No** — only the original single-argument `(context: dict \| str)` form exists (line 24). |
| `record_suppression()` method | `core/memory/policy.py` | **No** — zero matches. |
| `_ensure_policy_columns()`, `policy_memory.veto_count` | `core/memory/episodic.py`, `deploy/sqlite_schema.sql`, `deploy/supabase_schema.sql` | **No** — zero matches in any of the three files. |
| `decision_engine._make_situation_hash()` delegating to `PolicyMemory.make_situation_hash()` | `core/loop/decision_engine.py` | **No** — line 267–269 still computes its own inline hash: `f"{action_type}:{sorted(candidate.params.items())}"`. |
| `hands/runner.py` comment marking its writer unreachable/deprecated | `hands/runner.py` | **No** — line 143–147 is live, uncommented code: `PolicyMemory().update_from_outcome(hand.name, hashlib.sha256(f"hand:{hand.name}"...))`. |
| `VECTOR_TECHNICAL_KNOWLEDGE/` directory (where 89A–89D reports would live) | repo root | **Did not exist** before I created it to write this file. |

Git corroboration: `git log --oneline` on this worktree (`HEAD=6b5fcf204`) shows no commit
referencing governor async routing, fanout cooldown, goal-progress dedup, or policy hash
unification anywhere in reachable history. `git worktree list` shows the shared checkout
(branch `production-hardening-complete`) is 7 commits ahead of this worktree's base
(`5964a3316` vs `6b5fcf204`); I diffed that range (`git log 6b5fcf204..5964a3316`) and none
of those 7 commits touch this either — they're UI-sound and safety-prompt changes unrelated
to Task 89. The four sibling worktrees (`agent-a6e29c2...`, `agent-aa7984d...`,
`agent-ad9301d...`, `agent-aeaac40...`, presumably A–D's and/or other reviewers') are *all*
branched from the same `6b5fcf204` base as mine — I did not open them (out of scope, and I
was told to review the integrated result, not each agent's isolated claim), but nothing in
the shared branch history shows a merge/integration commit from any of them either.

**Conclusion:** either the integration happened somewhere this repository has no record of
(wrong repo, wrong branch, never actually run, or lost), or the task briefing's description
of tonight's work is inaccurate. I'm not able to distinguish those from the source tree alone.
What I can say with confidence: **the worktree handed to me for review contains none of the
five remediations it describes.**

---

## Items 1–15 (assessed against actual current/baseline source)

**1. PermissionGateway bypass — clean.** Nothing in the (nonexistent) diffs could bypass it
since nothing changed. `AutonomousLoop._act_on()` (`core/loop/autonomous_loop.py:847`) still
routes through `self._gateway` (`PermissionGateway()`, instantiated line 201) as the sole
real-world-action path; this is untouched.

**2. RED action creation — clean.** `core/config.py`'s `red` list (line 125) is unchanged:
`send_email, delete_files, execute_code, financial_transaction, push_github,
deploy_production, overwrite_note_personal`, plus Hand entries. No new action_type appears
anywhere I searched.

**3. YELLOW promotion changes — clean/not applicable.** Unrelated to this work, and nothing
touched `core/config.py`'s `yellow` list (line 109) or `TrustLadder` promotion logic.

**4. TrustLadder interaction — see dedicated section below. Not a live risk tonight, because
R4/R5 doesn't exist.**

**5. Candidate expansion — clean.** `DecisionEngine.evaluate()` (`core/loop/decision_engine.py:324`)
and candidate generation are byte-for-byte what they'd be with none of tonight's claimed work
applied, since none of it is applied. R6 (candidate diversity) was out of scope and remains
untouched.

**6. Event fanout amplification — concern, but pre-existing, not introduced tonight.** The
`strategy::review_analytics_insights` dangling dispatch (see table above) means every
`ANALYTICS_READY` event still fans out to a `strategy` "district" that doesn't exist in
`config/agent_manifest.yaml`. Whatever `Governor.dispatch()` does with an unregistered
district (likely: no agents found, dispatch no-ops or logs a miss) happens on **every**
qualifying event, uncooled, exactly as it did before tonight. This is real and worth the
lead's attention, but it is not something R2 introduced or worsened — R2 never landed.

**7. Reward contamination — concern, pre-existing.** With no `record_suppression()` channel,
the counterfactual-veto penalty writer (`core/loop/autonomous_loop.py:980-983`,
`update_from_outcome(..., reward=0.05)`) **does** currently write into `avg_reward` alongside
real outcomes — there is no separation. This is the pre-remediation baseline the brief says
R4/R5 was meant to fix; it's simply still true.

**8. Historical data corruption — clean.** No migration/backfill/rewrite code exists anywhere
for `policy_memory`, goal `progress`/`status`, or `counterfactual` rows, because no such code
was added. Nothing to corrupt.

**9. Hidden DB/schema changes — clean (none exist).** No `_ensure_policy_columns()`, no new
column, no schema-mirror changes in either `deploy/sqlite_schema.sql` or
`deploy/supabase_schema.sql`. Nothing runs additively or otherwise.

**10. Subprocess/network side effects — clean.** No new code, no new side effects.

**11. Unintended autonomous execution — clean, moot.** The composite chain the brief asks me
to trace (R4/R5 makes reward visible → differently-scored winner → still gated identically
by `_act_on()`) can't fire because R4/R5 never shipped. Separately confirmed as a genuine,
interesting pre-existing fact: **the reward channel is currently self-defeating anyway**
(see finding below) — two of the three reward writers in `autonomous_loop.py` use
`json.dumps(params, sort_keys=True, default=str)` for their hash key while
`decision_engine._make_situation_hash()` (the sole reader) and the veto-penalty writer use
`sorted(params.items())`. These produce different strings for the same params, hence
different SHA-256 hashes. **Concretely: the main 5-factor reward writer (line 1110-1113) and
the VectorCode reward writer (line 913-916) write to keys `get_score()` will never look up**,
so real outcome rewards for ordinary actions are *currently* invisible to future scoring —
this is the exact "unreadable key" bug the brief describes R4/R5 as fixing. It is real, it is
live in production right now, and it means today's YELLOW-tier scoring (including
`commit_code`) is *not* actually reward-driven despite `policy.get_score()` being called
before every decision (RULE 7) — it's silently defaulting. Worth flagging to the lead even
though it's out of tonight's claimed scope, since it directly bears on item 4's premise.

**12. Race conditions — not applicable.** `_fanout_edge_last_fired` doesn't exist.

**13. Async blocking — concern, and this is the sharpest real finding.** Since R1 never
shipped, `Governor.dispatch()` still calls `self.route_task(task_type)` synchronously
(`governor.py:1884`), which on a miss falls through to `self._llm_classify()`
(`governor.py:1560`) — a **fully synchronous** method that, outside pytest, calls
`self._cloud_classify()` (itself wrapping a sync `complete_sync()` in a `ThreadPoolExecutor`
when a loop is already running — so at least that path avoids blocking the loop) but on
`_cloud_classify` returning `None` falls through to a **direct, unguarded, blocking**
`chat(model=..., messages=..., timeout=12.0, ...)` Ollama call at line 1600-1606, called
straight from `dispatch()`'s coroutine with no `to_thread` wrapper. This blocks the event
loop for up to 12s on any request whose `task_type` doesn't keyword-match
`DISTRICT_TASK_MAP` and whose cloud classification fails. This is exactly the bug class R1
claims to fix, and it is **currently unfixed** in this tree.

**14. Test mocks — not applicable.** No new tests exist for any of R1–R5 (nothing to spot-check;
confirmed no fanout-cooldown, policy-v2-hash, or goal-progress-dedup test files anywhere in
`tests/`). The claimed "268 tests, 0 failures across the touched areas" cannot be verified
because there is no touched area.

**15. Modifications outside intended scope — the loudest finding of the whole review.** Diffing
this tree against every specific claim in the brief: **zero of the claimed diffs are present,
and the claimed "lead's one extra fix" (the second goal-progress site) refers to a code
location that does not exist.** There is no third deviation to report because there's no first
or second one either — this isn't a scope-creep problem, it's an integration-didn't-happen
problem.

---

## Item 4 — TrustLadder interaction (dedicated analysis)

**Mechanism, verified from `core/loop/trust_ladder.py`:** `TrustLadder.record_approval(action_type)`
increments a per-action-type `streak` **only on an explicit owner approval delivered through
the gateway** (Pushover phone-tap flow, presumably called from `permission_gateway.py` on a
YELLOW approval — I did not need to trace that call site since the mechanism itself is
unambiguous from `trust_ladder.py`'s docstring and schema). Default threshold is
`CONFIG["permission"]["trust_promotion_streak"]`, defaulting to **20** consecutive approvals
with zero `bad_outcomes`, read live via `_threshold()` (line 82-87). RED/FORBIDDEN never
participate. A rejection or failed execution resets the streak to 0 immediately. Confirmed
`commit_code` is YELLOW-tier (`core/config.py:115`), explicitly and deliberately kept there
per an inline comment, and is the action_type most structurally exposed to this mechanism
(frequent, low-friction, owner already habituated to approving it).

**Does R4/R5 (if it existed) create a live risk here?** The theoretical chain the brief
worries about is real in shape: (a) real reward becomes visible to `get_score()` → (b) a
YELLOW candidate scores higher on the `policy_score` factor (20% weight) → (c) it wins
`evaluate()` more often → (d) it's proposed to the owner more often → (e) if the owner keeps
approving it (which they would, for something already trustworthy enough to be scoring well),
`record_approval()` fires more often in wall-clock time → (f) the 20-streak fills faster →
(g) auto-execution starts sooner than it otherwise would have.

**But this chain cannot currently execute**, for two independent reasons, both verified above:

1. **R4/R5 was never integrated.** `decision_engine._make_situation_hash()` still computes
   its own inline hash — there is no unification for it to have introduced.
2. **Even judged as "what would happen if R4/R5 *were* applied exactly as described,"** the
   fix wouldn't have changed today's behavior anyway, because the *main* reward writer
   already writes to a hash `get_score()` can't reach (see item 11) — unifying the hash
   format is precisely what would flip this from "invisible" to "visible," which is the
   brief's whole point. So the risk described in item 4 is **real in principle and would
   become live the moment someone actually lands R4/R5 correctly** — but it is *not* a
   defect of tonight's integration, because tonight's integration doesn't exist. It is a
   forward-looking design consideration for whoever does eventually ship R4/R5: unifying the
   hash format is exactly the kind of change that could accelerate `commit_code`'s trust-ladder
   streak, and the promotion mechanism has no independent brake on *how fast* wall-clock
   approvals accumulate — only on whether they're explicit and unbroken. **Recommendation for
   that future work, not for tonight:** when R4/R5 actually ships, pair it with either (a) a
   minimum-interval floor between counted approvals, or (b) an explicit note in
   `trust_ladder.py`'s docstring acknowledging that upstream scoring changes can change
   promotion cadence, so it isn't rediscovered as a surprise later.

**Verdict for tonight specifically: not a live risk, because there is no R4/R5 to have
introduced it.**

---

## What I did not find

- No newly-introduced critical safety regression anywhere in the actual diffable state of
  this tree (there is no diff).
- No evidence of the 268 tests, the four agents' individual worktree work products, or any
  `VECTOR_TECHNICAL_KNOWLEDGE/89A/B/C/D` reports.

## Recommendation to the lead

Before requesting another red-team pass: confirm which commit/branch the actual R1–R5
integration landed on, verify it's reachable from wherever agent worktrees are cut, and
re-cut this reviewer's worktree from that point. If the integration genuinely never happened
(rather than being lost in a branching mixup), R1–R5 need to be implemented (or
re-implemented) before any safety sign-off is meaningful. Separately — and independent of
tonight's task — the reward-hash-format mismatch documented in items 7/11 above is a real,
currently-live bug worth its own fix regardless of what happens with R4/R5.
