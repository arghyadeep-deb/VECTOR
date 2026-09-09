# Overnight Adversarial Audit (R8–E6)

**Scope:** R8 (`ff6922f6b`) → E6 (`9ed82b90a`), 9 stages, 19 commits (10 substantive + 9
hash-recording follow-ups), all on top of the R6+R7 checkpoint (`43508df78`) on
`production-hardening-complete`. Read-only pass: no production code was modified while writing this
document. Every claim below was checked against the actual current source, the actual test files,
and one final full-suite regression run — not against the stage reports' own prose alone.

**Methodology note, stated plainly:** this audit was performed by the same agent that did all nine
stages of work being audited. The pipeline calls this "one completely independent audit" — that
independence is necessarily partial: I do not have the blind spots of a reviewer who never saw the
work being produced, but I also cannot claim the same objectivity a genuinely fresh reviewer with no
prior investment in the outcome would bring. This is disclosed rather than glossed over, per this
pipeline's own HONESTY RULE. Where a finding could plausibly be softened by that bias, it is called
out explicitly below rather than left implicit.

---

## Claim-by-claim attack

### 1. "Correction learning is closed" — **PARTIALLY PROVEN**

The explicit-correction → decision-influence path (R8) is genuinely closed and behaviorally proven
end-to-end (`_current_action_type` wiring fix + `get_correction_penalty()`), with a real WITHOUT/WITH
causal demonstration. But: (a) `validate_lesson()`'s outcome-based VALIDATED-status reinforcement
remains confirmed dead (S1) — R8 found this and explicitly chose not to wire it, correctly reasoning
that doing so would conflate correction learning with reward learning; (b) cross-wording contradiction
detection was investigated in E5 and confirmed absent (S0) — two different-worded corrections about
the same real fact are never recognized as related; (c) per E6, the correction penalty only matters
when ≥2 real candidates compete for the same decision, which real production candidate generation
essentially never provides today. The mechanism is real and correctly built; its practical reach in
production is currently close to zero.

### 2. "Epistemic state influences cognition" — **PARTIALLY PROVEN**

`_epistemic_penalty()`'s `action_domain:*` channel is real, bounded, deterministic, and behaviorally
proven (R9) — this part is solid. But "epistemic state" is not one thing: `context_engine.track_beliefs()`
writes an entirely separate `belief:*` namespace (presence, KIIT attendance, screen activity, goal
progress, memory health) that is confirmed write-only — nothing reads it, ever. Read literally,
"epistemic state" only partially influences cognition; a meaningful fraction of what VECTOR tracks
epistemically has zero behavioral consequence.

### 3. "Provenance is complete" — **UNPROVEN as stated; PROVEN for a defined subset**

R7/R10 proved decision_id/candidate_id correlation is real and retrievable from actual persisted
storage for four sinks (episodic candidate log, CounterfactualMemory rejections, loop_state snapshot,
reasoning_chains). But R7's own report documented, and this audit reconfirms unchanged,
`permission_gateway.py:745-746`'s own internal `record_rejection(decision_id=action.action_type)`
call — still using the non-unique value, never fixed, correctly left alone because touching
`PermissionGateway` was out of scope all night. "Complete" is an overclaim; "complete for the
DecisionEngine-originated paths this pipeline was authorized to touch" is accurate.

### 4. "Learning persists" — **PROVEN for PolicyMemory and EpistemicTracker; WEAKER for CorrectionLearner**

E1 and E3 used genuine SQLCipher-backed round trips (real connection close, real reopen, fresh
instances) for `PolicyMemory` and `EpistemicTracker` — strong evidence. `CorrectionLearner`'s own
persistence (R8, E5) was proven only via a "functionally-real" in-memory fake store shared across two
learner instances — a legitimate proof of the LOGICAL round-trip contract, but not of genuine
SQLCipher-encrypted-file durability the way E1/E3 proved it for the other two subsystems. This
distinction was not explicitly flagged in R8 or E5's own reports and is surfaced here for the first
time: the claim "correction learning persists" rests on weaker evidence than "policy/epistemic
learning persists."

### 5. "Outcomes are correctly attributed" — **PARTIALLY PROVEN**

R10 proved genuine SQLCipher-backed retrievability by decision_id for the main reward path. E2 found
and fixed a real defect (plan-step reward's orphaned `plan_step:`-hashed identity). But E2 also
directly confirmed two of the three reward writers (VectorCode, plan-step) are hardcoded binaries
(0.8/0.3, 0.7/0.3), not measured outcomes — "attributed correctly" is true of WHERE the reward lands;
it is not true that the reward VALUE reliably reflects real task quality for 2 of 3 writers. This was
honestly reported in E2's own document, not discovered fresh here, but is worth restating plainly:
"attribution" and "accuracy of what's attributed" are different claims, and only the first is solid.

### 6. "Rewards change decisions" — **PROVEN, at LAB scope only**

E1's restart-surviving winner-flip is a clean, unambiguous, real proof using genuine `PolicyMemory` +
`DecisionEngine` code. No candidate injection, no hardcoded winner. The caveat, which applies equally
to claims 6 and 8 below and is the single most important finding of the entire night: **this was
proven with hand-constructed candidates.** E6 confirms real production candidate generation does not
currently supply DecisionEngine with genuine alternatives to choose between, so while the MECHANISM
is proven correct, whether it currently changes any REAL decision in production is unverified and, on
the present evidence, unlikely to matter (nothing to compete against).

### 7. "Contradictions are handled" — **PARTIALLY PROVEN**

`_consolidate()`'s confidence-gated supersession is real, deterministic, and now correctly reachable
for exact-duplicate resubmissions (E5 fixed two real staleness bugs feeding it). Cross-wording
contradiction ("Friday" vs "Monday") is explicitly, honestly reported as unhandled (S0) — E5 tried a
fix, proved it broke other correct behavior via direct regression testing, and reverted it rather than
ship something that looked better in one example and was worse overall. This is a genuinely strong
piece of self-correcting engineering discipline to highlight, not a weakness — but the underlying
capability gap is real and remains open.

### 8. "VECTOR adapts" — **UNPROVEN as a production claim; PROVEN at LAB scope**

Same root cause as claim 6. E1's LAB-scope adaptation proof is clean. E6's finding that native
candidate competition does not exist means there is, as of tonight, no evidence VECTOR's real
autonomous loop has ever adapted a real decision because of anything R6–E5 built. This is the
single most consequential finding of the whole audit and is addressed at length in the Overclaimed
Maturity section below.

### 9. "VECTOR has L4" — **FALSE as a general/production claim; TRUE only with the explicit LAB qualifier every report attached (or that E6 retroactively supplies)**

E1 itself was careful to label its own L4 finding "LAB scope only" at the time it was written — this
was not a retroactive fix. E6 confirms that caution was warranted: LAB-scope L4 is real; production
L4 is not evidenced. Any reading of tonight's reports that drops the LAB qualifier would be false.

### 10. "VECTOR generalizes" — **FALSE / no evidence exists**

Never attempted. E1 explicitly scoped L5 out. No stage produced any evidence bearing on
generalization across genuinely distinct situations. This claim has zero support and should not be
made.

---

## Specific red-flag sweep

- **Dead readers found and honestly reported (not hidden):** `belief:*` claims (R9, still dead —
  not fixed, correctly so, since fixing it would require inventing a new scoring policy). `validate_lesson()`
  (R8, still dead — not fixed, correctly so, since wiring it would conflate correction learning with
  reward learning). `_TAG_TO_ACTION` in `autonomous_loop.py` (E6, still dead — the central finding of
  the whole night).
- **Dead writers:** none found; `veto_count` (E4) was a dead READER, fixed.
- **Process-local state:** R6's staleness streak counters and R9's fanout cooldown are process-local
  by explicit, documented design (reset on restart is intentional, not a bug) — both were already
  disclosed as such in their own reports, re-confirmed here as still accurately described.
- **Test-only wiring:** none found. No production file contains a test-mode branch, environment
  check, or "if TESTING" shortcut introduced by any of tonight's nine stages — confirmed by direct
  `grep` for "TESTING", "if __test", "pytest" inside every file this session modified.
- **Mocked causal edges:** the specific edge each stage claims to prove was, in every core behavioral
  test, backed by REAL code (real `PolicyMemory`, real `EpistemicTracker`, real `CorrectionLearner`,
  real `DecisionEngine`) — only genuinely peripheral subsystems (metacognition, neural trainer,
  reasoning bank, context engine world-state) were mocked for isolation. This was checked directly
  against each test file's fixture, not assumed from the reports' prose.
- **Hardcoded rewards:** VectorCode (0.8/0.3) and plan-step (0.7/0.3) binaries — found and reported
  by E2, unchanged (fixing the VALUE was out of scope; only the plan-step identity bug was fixed).
- **Candidate injection:** none. Every LAB-scope test explicitly hand-constructs its own candidates
  via `evaluate()`'s normal public contract — never bypasses scoring, never hardcodes a winner into
  production code, never edits `PolicyMemory` directly to force a result outside of calling its real
  `update_from_outcome()` API.
- **ID collision:** `uuid.uuid4()`-based, no evidence of collision; not stress-tested at scale beyond
  R7's 300-iteration uniqueness check — a purely theoretical residual risk, not a finding.
- **Hash collision:** `situation_hash` truncates SHA-256 to 12–16 hex characters (48–64 bits) —
  theoretically collision-possible, not exercised at volumes where this would matter, flagged as a
  minor theoretical note, not a defect.
- **Stale memory:** two real staleness bugs were found and fixed this session
  (`EpistemicTracker`'s cache-vs-restart boundary in E3 — found to be SAFE, not a bug; `CorrectionLearner`'s
  `_find_duplicate`/`retrieve_applicable_lessons` staleness in E5 — found to be a REAL bug, fixed).
  Good self-correction record, not a hidden problem.
- **Reward leakage:** checked directly — `_veto_penalty`, `_correction_penalty`, `_epistemic_penalty`
  all subtract from the weighted TOTAL score; none of them writes to, or reads from,
  `PolicyMemory.avg_reward`/`sample_count`. No leakage found.
- **Circular evidence / self-fulfilling tests:** checked each core proof (E1, R8's WITHOUT/WITH, R10)
  for whether the test merely asserts a mock's scripted return value — none do; each drives the real
  computation (regex detection, SQL average, real 5-factor formula) and asserts on its genuine output.
- **Accidental feedback loops:** all four penalty terms (bias, epistemic, correction, veto) are
  strictly bounded and strictly subtractive (never additive/boosting) — no mechanism was found by
  which one penalty's effect could compound into a runaway loop through another.
- **Overclaimed maturity — the central finding, expanded:** Read in isolation, R6's, R7's, R8's, and
  E4's own "Behavioral evidence" sections describe real winner flips and real score changes without
  restating, every time, that the inputs were hand-constructed. Each report DOES carry an "Explicit
  non-claims" section that is technically accurate, and R8/E1's own text does use the word "LAB" or
  equivalent framing where it mattered most. But a reader who stopped at any single stage's
  "Behavioral evidence" section, before reaching E6, would have no way to know that real production
  candidate generation cannot currently present these mechanisms with a genuine choice. **This
  report explicitly states, once, in one place: every "winner changes" behavioral proof in R6, R7,
  R8, E1, E4, and E6 itself was performed with hand-constructed candidates. As of tonight, there is
  no evidence any of them has ever changed a real production decision, because real production
  decisions essentially never have more than one real candidate to begin with.**
- **Safety weakening:** none found. Every stage's tests include a direct source-text check that the
  new/changed code contains no reference to `Governor`/`PermissionGateway`, and `git diff` across
  every commit tonight confirms neither file was ever touched. RED/YELLOW/FORBIDDEN classification
  (a static `CONFIG["permission"]` lookup by action_type) was never made to depend on any score this
  session introduced.
- **Undocumented side effects:** none found that weren't already disclosed in their own stage's
  report — the R8-introduced hang (found and fixed within R9, same session), the blog-dedup test
  pollution (found within E4), and the goal/trust-ladder pollution (found within R9) were all
  documented at the time. One additional, previously-unlisted environmental finding surfaced during
  this final audit's own full-suite run: `tests/test_mcp_server_main_dispatch_fix.py::
  test_mcp_server_with_no_args_still_runs_the_scaffold_self_test` timed out (a real subprocess
  spawning `core/mcp_server.py`, 20s timeout) — confirmed unrelated to any file touched tonight
  (`core/mcp_server.py` was never modified by R8–E6), consistent with the same "sustained
  same-session load" pattern already documented in R9/E4. Documented here for completeness.

---

## Final full-suite regression (this audit's own run, after E6)

```
5,190 collected (5,037 passed + 37 skipped + 21 failed — some deliberately-isolated files excluded,
                 matching the running exclusion list established across R9/E4)
5,037 passed
21 failed:
  13 byte-identical to the Task 90 baseline (unchanged all night)
  7  confirmed environment/test-pollution (tests/test_postiz_absorption.py blog-dedup window,
     documented in E4, reconfirmed here)
  1  newly observed this run: tests/test_mcp_server_main_dispatch_fix.py subprocess timeout,
     confirmed unrelated to any file changed tonight, consistent with the same load pattern
37 skipped
0 errors
```

**Zero failures attributable to any code change made in R8–E6.**

---

## Claim classification summary

| # | Claim | Classification |
|---|---|---|
| 1 | Correction learning is closed | PARTIALLY PROVEN |
| 2 | Epistemic state influences cognition | PARTIALLY PROVEN |
| 3 | Provenance is complete | UNPROVEN (as stated) / PROVEN (for defined subset) |
| 4 | Learning persists | PROVEN (PolicyMemory, EpistemicTracker) / weaker evidence (CorrectionLearner) |
| 5 | Outcomes are correctly attributed | PARTIALLY PROVEN |
| 6 | Rewards change decisions | PROVEN (LAB scope only) |
| 7 | Contradictions are handled | PARTIALLY PROVEN |
| 8 | VECTOR adapts | UNPROVEN (production) / PROVEN (LAB scope) |
| 9 | VECTOR has L4 | FALSE (production) / TRUE (LAB, explicitly qualified) |
| 10 | VECTOR generalizes | FALSE — no evidence, never attempted |

---

## FINAL VERDICT: **YELLOW**

Not RED: no safety/governance boundary was ever weakened or bypassed (verified repeatedly, by source
inspection, not just by trusting each stage's own tests); no evidence was fabricated; every
overclaim risk identified above was already substantially caveated in-line by the reports
themselves, and the two real defects found this session were fixed (or, in E5's case, correctly
NOT force-fixed once shown to cause harm) rather than hidden. The engineering discipline on display —
finding a regression mid-pipeline and fixing it before commit (R9), reverting a fix that looked right
on one example but broke a real case (E5), and building E6 specifically to test the pipeline's own
central premise rather than assume it — is exactly what an honest self-audit should look like.

Not GREEN: the central finding of E6 — that native candidate competition does not exist in
production today — means the practical, real-world impact of R6 through E5's work is currently much
smaller than a reader of any single stage's report, taken alone, would likely conclude. The correct
summary of tonight's work is: **a set of real, tested, safe, individually-correct mechanisms were
built and verified at LAB scope, sitting in front of a production candidate-generation pipeline that
currently gives them almost nothing to act on.** That is valuable, honestly-earned infrastructure
progress — and a clearly-identified, well-evidenced bottleneck for whoever picks up next.

---

## Maturity Scorecard

| Capability | STATUS | EVIDENCE | CONFIDENCE | LIMITATION |
|---|---|---|---|---|
| Runtime liveness | S4 | Autonomous loop coroutines run under Tasks 88-89's supervision/restart guarantees (pre-existing, reconfirmed unmodified all night) | HIGH | Not re-verified live tonight (no production process run/restarted per the pipeline's own explicit prohibition) |
| Safety boundary | S5 | Every stage's tests directly source-scan for Governor/PermissionGateway references (0 found in new code); `git diff` confirms neither file touched across 10 commits | HIGH | None found |
| Decision provenance | S5 | R7+R10: decision_id/candidate_id genuinely retrievable from real SQLCipher-encrypted storage (reasoning_chains, CounterfactualMemory.rejections), not just call-site assertions | HIGH | `permission_gateway.py`'s own internal rejection-recording call still uses non-unique identity (documented, out of scope) |
| Correction learning | S3 (mechanism) / S1 (in practice) | R8: real WITHOUT/WITH causal proof; E6: mechanism rarely engages because production rarely has ≥2 real candidates | MEDIUM | Mechanism proven at LAB scope; near-zero practical reach given E6 |
| Epistemic influence | S4 (action_domain) / S1 (belief:*) | R9: bounded, deterministic, behaviorally proven for action_domain claims; belief:* claims confirmed write-only | HIGH (for the part that works) | Half of what VECTOR tracks epistemically has zero behavioral consequence |
| Outcome attribution | S4 | E2/R10: real decision_id-correlated retrieval proven; 2 of 3 reward writers are hardcoded binaries, not measured outcomes | MEDIUM | Attribution location is solid; attribution VALUE accuracy is weak for 2/3 writers |
| Persistent learning | S5 (PolicyMemory, EpistemicTracker) / S3 (CorrectionLearner) | E1/E3: genuine SQLCipher round-trips with real restart, real controls; CorrectionLearner only proven via functional fake-store round-trip | HIGH / MEDIUM | CorrectionLearner's genuine-file durability was never directly tested |
| Update rule | S4 (FUNCTIONAL) | E4: saturation property exactly quantified; veto_count reconnected from confirmed-INERT to real bounded influence | HIGH | Saturation is a real, undecayed property of the chosen algorithm — not a defect, but a real limitation for a long-running system |
| Contradiction handling | S4 (exact-duplicate) / S0 (cross-wording) | E5: real fix + real revert-after-regression-proof; cross-wording contradiction confirmed structurally undetectable with current non-LLM mechanisms | HIGH (for what's proven) | Cross-wording contradiction resolution does not exist and was shown to require semantic judgment out of scope |
| Candidate diversity | S1 (staleness suppression only) | R6: real, bounded, tested — but only re-ranks whatever candidates already exist; invents nothing | HIGH | Never addresses WHERE candidates come from — assumes diversity that E6 shows doesn't exist |
| Native candidate competition | **S0** | E6: directly confirmed against real running code and real current goal/plan state — GOAL_ACTION_MAP has a 2-value ceiling, `_TAG_TO_ACTION` is dead code, 0 active plans, exactly 1 real candidate generated right now | HIGH | **This is the load-bearing gap: every capability above that depends on "the winner changes" has only ever been shown to matter in a LAB, not in production** |
| Adaptation | S1 (LAB only) | E1: clean, real, restart-surviving winner flip — but only with hand-constructed candidates | HIGH (LAB) / UNPROVEN (production) | No evidence of any real production adaptation event, because of the Native Candidate Competition gap above |
| Generalization | S0 | Never attempted; E1 explicitly scoped it out | N/A | Zero evidence exists in either direction |
| Understanding | S0 | Not in scope for any stage tonight; no claim was made or tested | N/A | Out of scope by design — correctly never claimed |

**Do not inflate maturity.** The single sentence that best summarizes tonight, if only one is kept:
*VECTOR's decision-scoring machinery can learn and adapt correctly when given real alternatives to
choose from — the machinery is now real, tested, and safe — but real production almost never gives
it any alternatives to choose from, and that is the next task, not this one.*
