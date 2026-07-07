---
name: vector-research-methodology
description: Load when turning a hunch into an ACCEPTED result on VECTOR — the evidence bar, hypothesis-predicts-numbers-before-running, the idea lifecycle from experiment flag to adopted change or documented retirement, and adversarial refutation. Triggers: "is this real", "how do I validate a hypothesis", "experiment", "should we adopt this", "prove the mechanism", "research discipline", "retire the idea".
---

# VECTOR Research Methodology

The discipline that turns "I think X" into "X is true and adopted here" — or into
"X was tested and retired, don't retry it." Ground truth 2026-07-07.

## When NOT to use this skill
For which directions to pursue use `vector-research-frontier`; for proving a
specific engineering change use `vector-proof-and-analysis-toolkit`; for the settled
record use `vector-failure-archaeology`.

## The evidence bar (what "accepted" requires here)
1. **One mechanism explains ALL observations — including the negatives.** A theory
   that explains the wins but ignores the cases where it failed is not accepted.
   (The DB-bloat root cause had to explain the size AND why DELETE didn't shrink it.)
2. **The hypothesis predicts NUMBERS before you run.** State the expected metric and
   threshold first; then measure. Post-hoc "looks good" is not evidence.
3. **It survives assigned adversarial refutation.** Someone (or you, deliberately)
   tries to break it. The whitelist guardrail was accepted only after a live attack
   was clamped. Wake-word "passing" was REJECTED once real recall was measured.
4. **It's reproducible.** The command/measurement is recorded and re-runnable
   (evidence-marker discipline: run it, quote real output, or tag `[UNVERIFIED-CMD]`).

## The idea lifecycle
```
hunch → experiment (behind a VECTOR_* flag, OFF by default)
      → measure vs the pre-stated numbers
      → adopted (flag on by default, recorded in change control + memory)
         OR retired (documented in failure-archaeology so no one re-fights it)
```
- Experiments live behind env flags (`VECTOR_*`) so they never affect default runs
  or tests — see `vector-config-and-flags`. This is how a risky idea is tried safely.
- Adoption routes through change control (`vector-change-control`) + the evidence
  gate (`vector-validation-and-qa`). Never adopt by eye.
- Retirement is a FIRST-CLASS outcome: write it into `vector-failure-archaeology`
  (symptom → what was tried → why rejected → status) so the dead end stays dead.

## Where good ideas have historically come from (this repo)
- Measuring instead of trusting: the wake-word recall gate, the DB size trend.
- Reading the FULL traceback to the deepest frame (speechbrain, pydantic bugs).
- Adversarial self-testing: the whitelist clamp, the sensitivity gate.
- Honest negative results: "synthetic voices don't transfer to the owner's voice"
  is a real, valuable finding that stopped wasted effort.

## Anti-patterns (these have cost time)
- Fixing the symptom you can see instead of the mechanism (retention vs the FTS dump).
- Declaring success from a lucky single sample (max over clips).
- Deleting "dead" code without proving it's dead (it was often unwired-but-useful).
- Adopting a change without a before/after number.

## Provenance and maintenance
2026-07-07. Grounded in VECTOR's actual investigation history (memory index +
`vector-failure-archaeology`). The evidence-marker discipline is inherited from the
skill-library-builder methodology (github.com/MeeshaBear1/skill-library-builder):
nothing unexecuted gets published.
