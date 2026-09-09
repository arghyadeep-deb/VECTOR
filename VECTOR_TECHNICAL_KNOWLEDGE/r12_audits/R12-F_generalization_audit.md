# R12-F — Generalization Audit

**Objective:** determine whether any existing mechanism causes learning in one situation to
influence a different situation, and classify each such channel as safe-intentional,
safe-accidental-but-harmless, or dangerous.

**Method:** direct source read of `core/memory/policy.py`, `core/loop/decision_engine.py`,
`core/memory/counterfactual.py`, `core/memory/correction_learner.py`, `core/brain/epistemic_tracker.py`,
grep for similarity/clustering/prefix logic across the decision/policy/epistemic stack, and trace of
every real caller of each mechanism. Read-only — no file was modified, no DB was touched.

## Findings

### Channel 1 — `PolicyMemory.make_situation_hash()` (`core/memory/policy.py:23-62`)
Full-fidelity `json.dumps({"action_type": ..., "params": ...}, sort_keys=True)` → SHA-256, truncated
to 12 hex chars, prefixed `"v2:"`. Every key in `params` — including display-only fields like
`"title"` and `"goal_id"` — is part of the hash identity (confirmed by the function's own docstring,
line 45-47: "params are NOT filtered/allowlisted"). **This channel provides ZERO cross-situation
generalization.** Two candidates with the same `action_type` but different `goal_id` hash to
completely different rows. No collision risk, no transfer risk — if anything this is the opposite
finding of what was hypothesized: PolicyMemory learning is currently *maximally* situation-specific,
which is why R11's own learning-integration proof needed the exact same goal/params replayed after
restart to observe the flip.

### Channel 2 — Epistemic domain-prefix bucketing (`core/loop/decision_engine.py:395-469`)
**Confirmed live and real**, exactly as flagged by this session's own E6 report. `_epistemic_penalty()`
(line 414) and `record_epistemic_belief()` (line 453) both compute
`domain = action_type.split("_")[0]` and key a SHARED belief on `f"action_domain:{domain}"` —
NOT on goal_id, NOT on params, NOT on the full action_type. Consequence: `code_task`, `code_review_vc`,
`code_generate`, `code_fix`, `code_debug` all share domain `"code"`; `check_attendance` and
`check_fatigue` (semantically unrelated) both share domain `"check"`; `daily_digest` and
`daily_review` share `"daily"`. A poor outcome on one action_type genuinely dampens the epistemic
confidence factor for every other action_type sharing its first token, across ANY goal.

This is intentional (JARVIS Gap 3, docstring cites it explicitly) and **bounded**: the effect is a
multiplicative post-score factor clamped to `[0.70, 1.0]` (line 398) — it can only ever soften a
score, never invert a ranking on its own, never change RED/YELLOW/GREEN classification, never force
or block execution. It is a real generalization channel, but a soft, low-blast-radius one.

Coarseness risk (correctness, not safety): single-token prefix splitting has no semantic validation
— `"check_attendance"` and `"check_fatigue"` sharing a bucket is almost certainly unintended
coupling, since nothing about attendance-checking predicts fatigue-checking reliability.

### Channel 3 — `CorrectionLearner.get_correction_penalty()` (`core/memory/correction_learner.py:700-724`)
Deliberately **exact-match only** on the literal `action_type` string — the docstring (lines 708-715)
explicitly states this design choice was made *to avoid* the leakage this audit was asked to check
for: "a correction about `send_email` can never accidentally penalize `send_email_bulk`... no
substring/keyword/semantic interpretation." Bounded `[0.0, 0.12]`. This channel generalizes only
across goals that happen to reuse the exact same action_type (by design, not accident) — the
narrowest and most conservative of the four channels found.

### Channel 4 — `CounterfactualMemory.should_avoid()` (`core/memory/counterfactual.py:19-27, 243-262`)
A genuine, deliberate (Gap 4) token-level Jaccard-similarity mechanism over the `proposal` string
(`f"{action_type} {json.dumps(params)}"`). Default `threshold=0.4`; production callers in
`autonomous_loop.py:512,1150` use the stricter `threshold=0.7`. Staleness-decayed with a 7-day
half-life (`_decay_factor()`, line 30-46) so an old/spurious rejection stops influencing new
proposals after ~3-4 half-lives. **This is the only channel of the four that can outright block
(skip) an action** — confirmed live at `autonomous_loop.py:512-523`, in the retry-queue
defense-in-depth pre-filter: if `should_avoid()` returns true with score > 0.7, the retried item is
dropped and requeued/DLQ'd, never reaching `gw.execute()`. Explicitly documented as
"defense-in-depth" (comment, line 501-505) — `PermissionGateway` remains the authoritative
RED/YELLOW/GREEN gate regardless; this mechanism narrows the retry-queue's own proposal set, it does
not and cannot grant authority or bypass the gateway.

No embedding/vector/ML similarity anywhere in this stack (confirmed: `_jaccard()`'s own docstring —
"no ML deps, runs anywhere" — token-set overlap only).

## Channel-by-channel classification

| Channel | Classification | Blast radius |
|---|---|---|
| PolicyMemory `make_situation_hash` | N/A — no generalization occurs | none |
| Epistemic domain-prefix bucketing | safe-intentional, but coarse (correctness risk) | soft multiplier [0.70,1.0], cross-goal within shared action_type prefix |
| CorrectionLearner exact-match penalty | safe-intentional, narrowest by design | soft penalty [0.0,0.12], cross-goal only within identical action_type |
| CounterfactualMemory Jaccard `should_avoid` | safe-intentional, bounded, defense-in-depth only | can skip one retry-queue item; PermissionGateway remains authoritative downstream regardless |

**No dangerous (accidental/unbounded) generalization channel was found.** No channel can escalate
authority, flip a permission tier, or force execution. No channel is unbounded.

## Current capability level

L6 (cross-situation / cross-strategy transfer, per the mission's definition: "Situation A → strategy
outcome → learned evidence → related Situation B → appropriate strategy preference") is **NOT
IMPLEMENTED**. None of the four channels performs this: PolicyMemory transfers nothing (Channel 1);
the epistemic channel (2) only dampens confidence uniformly within a domain bucket, it never causes
VECTOR to *prefer* a different, better candidate based on a related situation's learned outcome;
CorrectionLearner (3) is exact-match by design, explicitly not transfer; CounterfactualMemory (4)
only suppresses, it never promotes an alternative. This confirms and narrows R11/E6's own prior
finding — the generalization gap is real, and none of the existing bounded channels closes it,
by design.

## What's broken vs working

- **Working, as designed**: all four channels behave exactly as their own docstrings claim; none is
  dead code, none is orphaned, none silently no-ops.
- **Not broken, but coarse**: Channel 2's single-token domain split is a legitimate future
  improvement target (e.g., require domain+object agreement, or drop the "check_"/"daily_"-style
  generic prefixes from the bucketing key) — not a correctness bug today, since no test or production
  evidence shows it causing a wrong RED/YELLOW/GREEN outcome, only a soft score nudge.
- **Missing**: any mechanism that answers "should VECTOR prefer strategy X in situation B because
  strategy X worked well in analogous situation A" — this is L6 and does not exist anywhere in the
  current stack.

## Recommended next milestone

If R19 (Generalization) is pursued: design a bounded, explicit "related-situation" preference signal
— e.g., keyed on (action_type, goal tag overlap) rather than PolicyMemory's exact params hash — with
its own threshold/decay/cap discipline matching Channels 2-4's existing bounded-nudge pattern. Do NOT
repurpose the epistemic domain-prefix bucket for this — its coarseness (single-token split) makes it
unsuitable as a strategy-preference signal; it is a confidence dampener, not a similarity engine.

## Open questions

- Whether the epistemic domain-prefix coarseness (`"check_attendance"` == `"check_fatigue"` ==
  domain `"check"`) has ever, in practice, caused a materially wrong dampening — no production
  telemetry currently answers this; would require the observability layer discussed in a separate,
  unrelated planning artifact to measure.
- Whether CorrectionLearner's cross-goal-but-same-action_type reuse (Channel 3) is desired behavior
  or should also be goal-scoped — out of scope for this audit; flagging for R12 synthesis.
