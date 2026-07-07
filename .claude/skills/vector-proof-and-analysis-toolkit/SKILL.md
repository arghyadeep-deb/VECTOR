---
name: vector-proof-and-analysis-toolkit
description: Load when you must PROVE a change works rather than assume it — a routing change, a quality gate, a bug fix, a performance claim. First-principles analysis recipes with worked examples from VECTOR's own history. Triggers: "prove it works", "measure the improvement", "did the fix actually hold", "is this better", "quality gate", "how do I show", "validate the change".
---

# VECTOR Proof & Analysis Toolkit

"Prove it, don't just install it." Recipes for turning a claim into evidence, each
with a real VECTOR example. Ground truth 2026-07-07. This is the discipline that
separates "I changed something" from "I made it better."

## When NOT to use this skill
For the standard test gate use `vector-validation-and-qa`; for the frontier
research process use `vector-research-methodology`.

## Recipe 1 — Prove an artifact's quality (don't eyeball it)
CLAIM: "the model/output is good enough."
METHOD: define a measurable acceptance metric BEFORE producing; stage the artifact;
measure the fraction that passes; install only if it clears the bar.
WORKED EXAMPLE (wake word, 2026-07): the gate first used `max(peaks)` — one lucky
clip (0.93) passed a model that recognized only 1/15 real clips. FIX: measure
RECALL FRACTION (>=50% of real clips must fire) + silence false-positive (<0.30).
Result: the honest gate correctly REJECTED the synthetic-only models (0-2/15). The
lesson generalizes: a max/any over samples hides a bad artifact; measure the fraction.

## Recipe 2 — Prove a fix addressed the ROOT cause (not a symptom)
CLAIM: "fixed the DB bloat / the crash."
METHOD: state the mechanism; show the measurement before AND after; confirm the
mechanism explains ALL observations, including ones you didn't set out to explain.
WORKED EXAMPLE (DB 2.3GB->131MB, 2026-06-29): the tempting fix was "tighten
retention." The REAL mechanism was `context_budget.py` dumping 56KB prompt offloads
into FTS-indexed episodic (write-only dead weight), AND that FTS DELETE only
tombstones so space needs DROP+CREATE. Both had to be true to explain the size.
Measured before/after: 2.3GB -> 131MB. Retention alone would not have done it.

## Recipe 3 — Prove a routing/model change is an improvement (not just a change)
CLAIM: "domain routing / provider X is better."
METHOD: hold the task fixed; compare the OLD path vs NEW path on the same inputs;
report the metric that matters (correctness/latency/quota), not vibes. Confirm the
chain still terminates on ollama (never-crash invariant).
EXAMPLE: switching investment agents to `domain:finance.analysis` — prove the chain
resolves (`chain_for_domain('finance.analysis')` returns gpt-5 -> zai-glm-4.7 ->
DeepSeek-R1 -> ... -> ollama, verified 2026-07-07) and that a live call is served
by the first available backend — not that "it feels smarter."

## Recipe 4 — Prove a guardrail actually holds (adversarial)
CLAIM: "the paid-model whitelist / sensitivity gate works."
METHOD: try to BREAK it, then show it held. WORKED EXAMPLE (2026-07-02): forcing
`model=claude-opus-4-8` on the opencode_zen provider -> request was CLAMPED and
served by `deepseek-v4-flash-free` with a warning (verified live). A guardrail
unproven-against-attack is a hope, not a guardrail.

## The universal shape
1. State the claim as a falsifiable prediction with a NUMBER.
2. Define the metric + acceptance threshold BEFORE running.
3. Measure old vs new (or attack vs hold) on the same inputs.
4. One mechanism must explain ALL observations, including negatives.
5. Record the numbers in the plan/memory; never promote by eye.

## Provenance and maintenance
2026-07-07. Examples verified against `scripts/train_wake_word_synthetic.py`
(recall gate), memory `project_full_audit_2026_06_29.md` (DB bloat), and the
live whitelist clamp test (2026-07-02). Re-verify a chain:
`python -c "from core.inference.model_catalog import chain_for_domain; print(chain_for_domain('finance.analysis'))"`.
