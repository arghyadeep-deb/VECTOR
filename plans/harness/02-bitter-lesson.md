# Harness Analysis 02 — Bitter Lesson Engineering
> 2026-07-07, Fable 5. Where the harness over-engineers hand-coded logic that
> should be left to general model capability + search/learning.

## Sutton's Bitter Lesson (applied here)
General methods that leverage computation (search + learning) beat hand-crafted,
human-knowledge-encoded methods as compute/model-capability grows. For a coding
harness: don't hard-code what a stronger model will just do; build flexible
scaffolds that improve automatically as models improve.

## Where VECTOR/harness VIOLATES Bitter Lesson (findings)
1. **Regex/keyword routing where a model should decide.** `governor.route_task`
   uses a hardcoded `DISTRICT_TASK_MAP` keyword table first, LLM only as
   fallback; the voice intent gate started as 17 regexes. As models improve,
   the hand-tables become the bottleneck and the ceiling. LESSON: prefer the
   model classifier with the keyword table as a cheap cache, not the primary.
   (Partly done — LLM fallback exists; make it primary where latency allows.)
2. **Hand-tuned model→tier→provider tables (`TIER_ROUTING`, `model_catalog.yaml`
   ranks).** Necessary today (free-tier limits are real constraints), but the
   *ranking* is hand-curated. FUTURE-FLEX: let a small learned policy
   (policy_memory already exists — RL reward) adjust provider ranks from
   observed success/latency/quota, rather than static YAML ranks. Keep YAML as
   the prior; learn the deltas.
3. **Modelfile-encoded behavior (vector-ambient JSON-only) that FOUGHT the
   system** — a hand-constrained model that couldn't do plain classification.
   LESSON: over-specifying a model's behavior in a modelfile is exactly the
   brittle human-knowledge encoding the Bitter Lesson warns against. Prefer
   general models + prompt-time instructions.
4. **Static thresholds** (wake-word 0.5, trust-ladder streak=20, quota 90%).
   Reasonable defaults, but hand-set. FUTURE-FLEX: make them learnable/adaptive
   where the signal exists.
5. **Deep hand-coded fallback chains everywhere.** These are GOOD for reliability
   (Bitter Lesson doesn't say "no engineering") — but audit that they degrade to
   the *most capable* option, not a fixed one.

## What is CORRECTLY general (keep)
- Cloud-primary routing that automatically uses better models as owner's free
  tiers gain them — this IS Bitter-Lesson-aligned.
- Domain chains ending on ollama (graceful, model-agnostic).
- policy_memory / reasoning_memory (learning substrate — underused, see #2).

## Upgrade plan for model-flexibility
1. Make LLM classification PRIMARY where latency budget allows; keyword tables =
   cache/prior only. (governor, voice intent — partly there.)
2. Wire `policy_memory` (RL reward) to adjust provider/model ranks from outcomes
   — turn the static catalog ranks into learned priors.
3. Remove behavior-constraining modelfiles; move constraints to prompt-time.
4. Parameterize hand-set thresholds; where an outcome signal exists, learn them.
5. Principle to add to `.claude/rules`: "prefer general model capability +
   the learning substrate (policy/reasoning memory) over new hand-coded logic;
   hand-code only the reliability scaffold, not the intelligence."

## Provenance
2026-07-07. Sources: `core/city/governor.py`, `core/inference/model_catalog.yaml`,
`core/memory/policy.py`, `.claude/rules/models.md`, wake/trust/quota thresholds.
