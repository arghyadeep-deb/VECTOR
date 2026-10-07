# Reasoning-Ceiling Policy Review — Input for an Owner Decision

**This document does not recommend a policy change. It is the owner-decision
input gap 1 of the post-audit improvement plan calls for — a cost/quality
review of the free-tier-only runtime policy, so the choice to keep it is a
reviewed decision, not an unexamined default. Closure type for this gap is
"accepted" either way (see `docs/design/gap-register.md`, row G1); nothing
here is self-executing.**

## What can and cannot be measured right now

A real empirical comparison (same VECTOR decision run through both a local/
free-tier model and a paid frontier model, scored side by side) was the
original ask. **It cannot be done**: confirmed via `get_secret()` that no
`ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is configured anywhere on this
machine (checked 2026-10-07) — consistent with the standing "no paid keys
at runtime" policy. Producing a live comparison would require either asking
the owner to supply a paid key specifically for this one-time test (an
explicit, scoped ask, not something to do unprompted), or relying on
published third-party benchmark numbers instead of VECTOR's own decisions.
This document uses the latter, and says so plainly rather than presenting
published-benchmark numbers as if they were VECTOR-specific measurements.

## The hidden collision this analysis must not cross

Codex's round-3 review of the original plan caught this correctly: VECTOR's
existing rule (`.claude/rules/models.md`) is that **security/privacy/
RED-tier/secret-bearing work stays on local Ollama only** — a data-locality
and secret-handling boundary, not a cost boundary. Any proposal to add paid
cloud models for "better reasoning" must NOT include RED-tier, security, or
financial-analysis categories, because doing so would silently reopen that
boundary under cover of a cost conversation. **This analysis is scoped to
general/medium-complexity reasoning only** (`core/inference/route_policy.py`'s
"simple"/"medium" tiers) — not RED-tier, not anything the sensitivity gate
already routes to local-only.

## What the published numbers suggest (not VECTOR-specific measurement)

For general reasoning tasks (goal evaluation, candidate scoring, routine
decision explanation — NOT security/financial/RED-tier), published
benchmark comparisons (MMLU, GPQA, and similar third-party evals, as of
their respective publication dates) consistently show a meaningful quality
gap between the locally-run models VECTOR uses (qwen3:14b, gemma4:e4b class)
and frontier cloud models. The gap is real and well-documented across many
independent evaluations, not a VECTOR-specific artifact — but exact
magnitude varies a lot by task type and benchmark, so no single number
should be treated as "the" quality delta. The architecture around VECTOR's
decisions (goal alignment, policy scoring, context hydration) is independent
of this gap; it bounds how good any single LLM call's output is, not how
well VECTOR uses that output once it has it.

## The real question for the owner, broken into the right pieces

Per Codex's refinement, this isn't one yes/no question — it's at least four
separate axes that shouldn't be collapsed into one:

1. **Is the current reasoning quality actually a problem in practice?**
   This document has no VECTOR-specific evidence either way — nobody has
   measured whether the free-tier ceiling has caused a real, named bad
   outcome, vs. being a theoretical concern. That's worth establishing
   first, separately from any cost question.
2. **If it is a problem, which specific categories need better reasoning?**
   (Explicitly NOT security/RED-tier/secret-bearing — those stay local by
   an existing, separate rule this document does not propose touching.)
3. **What would a narrow, capped paid carve-out actually cost?** Free-tier
   cloud providers already in `core/inference/model_catalog.yaml` cover a
   lot of ground; a bounded "escalate to a paid model only for category X,
   capped at $Y/month, logged and reviewable" carve-out is a much smaller
   ask than "allow paid models generally." No real $ estimate is possible
   without the owner specifying which category and what volume, since
   VECTOR's own call volume for that category isn't instrumented separately
   yet.
4. **Is "stay free-tier-only" itself fine as a permanent answer?** It's a
   legitimate, defensible choice — plenty of real products run entirely on
   free/local tiers by design. This document does not treat "no change" as
   the wrong answer; it treats "never examined" as the thing worth fixing.

## Recommended next step (for the owner, not an action this document takes)

If this is worth pursuing further: pick ONE non-sensitive category where
reasoning quality is suspected to matter most (a reasonable first guess,
not yet verified: multi-step goal/candidate evaluation in
`core/loop/decision_engine.py`, which already explicitly scores five
weighted factors and would make quality differences easy to compare
side-by-side), supply a temporary paid key scoped to testing only, and run
a real side-by-side comparison on a sample of actual recent VECTOR decisions
— not a synthetic benchmark. That would replace this document's published-
numbers reasoning with VECTOR's own evidence. Until that happens, the
honest status is "policy reviewed on paper, not empirically tested" —
accepted, not eliminated, per the gap register.
