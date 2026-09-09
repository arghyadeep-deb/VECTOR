# R12-B — Learning / Outcome Audit

**HEAD audited:** `81b53b1175aede4ed05d1b9d086af91dda64c8a6` (read-only; no production code or DB touched)

## Objective

Trace decision → candidate → winner → execution → outcome → reward → `PolicyMemory.update_from_outcome()` → future decision in the CURRENT source, and determine whether a real production outcome-capture path exists (superseding stale historical docs) or whether outcome attribution is the actual remaining L5 bottleneck.

## Method

`grep -rn "update_from_outcome("` repo-wide, then read every non-test, non-`learning_lab` call site in full context. Cross-checked `decision_engine.py`'s read side (`get_score()`/`make_situation_hash()`) for identity consistency with each writer.

## Findings

### The read side (unchanged, canonical)

`core/loop/decision_engine.py:379-393` — `_make_situation_hash(candidate)` delegates to `PolicyMemory.make_situation_hash(candidate.action_type, candidate.params)`. `core/loop/decision_engine.py:500-503` — `_score_candidate()` calls `self._get_policy().get_score(candidate.action_type, situation_hash)` **before** every score, using that same canonical hash. This is RULE 7's read side, confirmed live and unchanged from R11.

### Real production writers (three, all canonical-identity, all reward-carrying)

| # | File:line | Trigger | Reward formula | Identity |
|---|---|---|---|---|
| 1 | `core/loop/autonomous_loop.py:1097-1103` | VectorCode bridge task completes (`_VC_ACTION_TYPES`) | `0.8` if `vc_result.status == "ok"` else `0.3` | `pm.make_situation_hash(winner.action_type, winner.params)` — canonical |
| 2 | `core/loop/autonomous_loop.py:1319-1343` | The general `governor.dispatch()` path (any winner not proactive/plan/VC/skill-matched) | Real 5-factor blend: `user_feedback*0.40 + goal_progress*0.25 + not_overridden*0.15 + not_corrected*0.15 + completed*0.05`, where `user_feedback` comes from `_get_recent_feedback()` (real episodic-memory lookup) when present, else estimated `0.7/0.3` from `completed` | same canonical hash |
| 3 | `core/loop/autonomous_loop.py:1577-1605` | `_act_on_plan_step()` — PlanRunner step completes | `0.7` if `status=="completed"` else `0.3` | same canonical hash — **note:** this was fixed by a prior task (E2 audit, comment at line 1582-1603) from a plan-local, non-canonical hash to the canonical one; historical docs describing plan-step rewards as unreadable are now stale |

**All three writers are reachable from a real `_act_on()` call on a real winner**, gated by (in order) proactive-action short-circuit → plan-step routing → VC routing (writer #1) → swarm coordination (non-blocking) → CounterfactualMemory veto check (can return early via `record_suppression()`, see below) → ThreatDetector scan → RedTeamAgent review (RED only) → skill match (writer via governor path if unmatched) → governor.dispatch() → writer #2. None of these gates depend on LAB/test scaffolding — they run for any real winner in a real autonomous loop tick.

### The historical "reward=0.05 contamination" bug is FIXED, not current

Multiple pre-R6 docs (`83_CURRENT_SEGMENT2_CHECKPOINT.md:91`, `80_AUTONOMOUS_AGENTIC_LEARNING_TRACE.md:189`, `89D_POLICY_REWARD_IDENTITY.md`, `84_CURRENT_STATE_RECONSTRUCTION.md:1003` marking it "S1") describe the *only* reachable writer as a hardcoded `reward=0.05` fired on every CounterfactualMemory veto, permanently contaminating `avg_reward`. **Current source (`autonomous_loop.py:1145-1188`) confirms this was already remediated** by a prior Task 89 (D3): the veto path now calls `record_suppression(action_type, situation_hash)` — a separate `veto_count` column — and explicitly does **not** touch `avg_reward`/`sample_count` (comment at 1167-1180 documents the exact rationale and cites this being a deliberate fix). Do not re-open this as a new finding; treat all pre-89D docs describing it as the live bottleneck as **stale**.

### One newly-identified orphaned/false-learning writer (not previously flagged in this session's history)

`districts/reflection/daily_reviewer.py:130-148` — the daily reflection loop writes `PolicyMemory.update_from_outcome(action_type=f"behavioral_rule_{i}", situation_hash=sha256("daily_reflection:{date}:{rule[:60]}")[:12], reward=0.65)` for up to 10 extracted rules every day. **Neither the `action_type` nor the `situation_hash` is ever produced by real candidate generation** (`goal_system.py`'s action_types, or any `Candidate.action_type` DecisionEngine ever scores) — `behavioral_rule_0..9` is a synthetic label, and the hash is derived from the reflection date/rule text, not `(action_type, params)`. This is structurally identical in shape to the old 0.05 bug: a hardcoded reward (`0.65`) written to a key `get_score()` can never read back. Unlike `hands/runner.py`'s equivalent orphaned writer (see below), this one carries **no comment acknowledging it's unreachable** — it reads as a genuine, currently-live no-op that silently accumulates rows nobody scores against. Low severity (P3 — wastes a write, doesn't corrupt real learning, doesn't touch safety), but worth a dedicated milestone to either wire it to a real, existing action_type or remove it.

### One already-known, self-documented orphaned writer (confirmed still orphaned, not a new finding)

`hands/runner.py:141-159` (`_update_policy()`) writes `PolicyMemory.update_from_outcome(hand.name, sha256(f"hand:{hand.name}"), reward)`. The code's own comment (lines 142-151) already documents this is "DEPRECATED / DO-NOT-CONNECT" — no `Candidate` is ever constructed with a hand's name as `action_type`, so this is structurally unreachable by design and deliberately left that way rather than half-fixed. Confirmed still true at this HEAD; not a new defect, just re-verified.

### `core/api/crud.py:65-72` and `core/memory/router.py:183`

Both are thin, generic pass-through wrappers (`update_policy(action_type, situation_hash, reward)` / a router dispatch) that forward whatever an external caller supplies — not autonomous-loop-internal writers, and not evaluated further here (out of scope: they're API surface, not part of the autonomous decision→outcome loop).

## Causal chain diagram

```
real goal → native candidates (R11)         EXISTS, PRODUCTION-REACHABLE
        → DecisionEngine.evaluate()          EXISTS, PRODUCTION-REACHABLE (get_score() read, canonical hash)
        → winner → _act_on()                 EXISTS, PRODUCTION-REACHABLE
        → gates (threat/red-team/cf-veto)    EXISTS, PRODUCTION-REACHABLE (may short-circuit via record_suppression — correctly NOT a reward write)
        → governor.dispatch() / VC bridge /
          plan step execution                EXISTS, PRODUCTION-REACHABLE
        → real 5-factor / bridge / plan
          reward computed from real result    EXISTS, PRODUCTION-REACHABLE
        → PolicyMemory.update_from_outcome()
          (canonical identity)                EXISTS, PRODUCTION-REACHABLE
        → get_score() on next decision         EXISTS, PRODUCTION-REACHABLE (same canonical hash)
```

Every link in the causal chain now EXISTS and is PRODUCTION-REACHABLE in source. This is a stronger state than several pre-R6 historical docs describe — those describe an earlier, already-fixed version of this codebase.

## Current capability level

Source-level: **L3/L4 mechanically wired** (matches R11's own claim — R11's test suite already exercised writer #2's exact code shape, just via directly-constructed Candidates in an isolated DB rather than a live `_act_on()` call). **Not yet PRODUCTION_VERIFIED at L5** — no evidence in this audit (nor claimed by any file read) that a real, running autonomous loop has actually gone decision→execution→outcome→policy-update→different-later-decision end-to-end on the live system. That would require either real production telemetry/logs or a bounded owner-approved runtime observation — out of scope for a read-only source audit.

## What's broken vs working

**Working:** the full decision→outcome→reward→policy identity chain is real, consistent (single canonical hash used by every reader and all three live writers), and reachable without any LAB/test scaffolding. The one historically-cited contamination bug (reward=0.05 veto writer) is fixed.

**Broken (minor, non-blocking):** `daily_reviewer.py`'s reflection-rule writer is a silent no-op (writes to unreachable keys) — should be fixed or removed, but does not block L5 since it's a separate, additive writer, not on the critical decision-loop path.

**Not yet demonstrated:** whether this wiring actually produces observed adaptation over repeated real autonomous cycles (L5) — this audit found the mechanism is real and reachable, not that it has been observed operating.

## Recommended next milestone

Given this audit: **outcome attribution is NOT the current L5 bottleneck** — it was already fixed by prior work (Task 89D) and is confirmed intact at this HEAD. The likelier remaining gaps for L5 are (a) whether the runtime actually cycles through enough real decisions with real diverse candidates to accumulate a learning signal (a liveness/runtime question — see R12-G), and (b) the minor `daily_reviewer.py` orphaned-writer cleanup (P3, optional). Recommend R12 synthesis treat "outcome attribution repair" as **already done, not a new milestone** — redirect that engineering budget toward whatever R12-G/R12-D find blocking actual repeated production cycles.

## Open questions

- Does `_get_recent_feedback()` (used in writer #2's `user_feedback`) ever return a non-None real value in practice, or does the reward estimate always fall back to the synthetic `0.7/0.3` completed-based guess? Not traced in this audit — recommend a targeted follow-up if reward-quality (not just reward-existence) becomes the next question.
- Whether `record_epistemic_belief()` and `record_outcome()` (neural trainer) calls alongside each `update_from_outcome()` are themselves correctly wired is R12-C's and the runtime audit's concern, not re-verified here.
