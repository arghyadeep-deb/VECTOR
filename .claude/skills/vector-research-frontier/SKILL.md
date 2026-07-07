---
name: vector-research-frontier
description: Load when looking for where VECTOR could genuinely advance the state of the art — open problems, why current SOTA falls short, VECTOR's specific asset, the first concrete steps in-repo, and a falsifiable success milestone. Triggers: "research direction", "novel", "advance the state of the art", "what's the frontier", "open problem", "could we publish", "what's genuinely new here".
---

# VECTOR Research Frontier

Open problems where VECTOR's specific design could produce a real result, not just
a demo. Each entry: why current SOTA falls short, VECTOR's asset, the first three
in-repo steps, and a falsifiable "you have a result when…" milestone. Ground truth
2026-07-07. Everything here is a CANDIDATE — labelled open, not proven.

## When NOT to use this skill
For the discipline of turning a hunch into an accepted result use
`vector-research-methodology`. For running the hardest live engineering problem use
`vector-campaign-ship-to-running`. This skill is about NOVEL directions.

## Frontier 1 — Darwinian agent selection as a real optimizer
WHY SOTA FALLS SHORT: most "multi-agent" systems use static agents or hand-tuned
routing; selection pressure is cosmetic. VECTOR's ASSET: HP is earned/lost on real
outcomes, death→ghost→successor is implemented (`core/city/*`, `evolution_engine`).
FIRST 3 STEPS: (1) log per-agent HP trajectories + successor lineage over a burn-in;
(2) define a population-level fitness metric (task success rate per generation);
(3) A/B a generation WITH vs WITHOUT ghost inheritance. MILESTONE: you have a result
when generation-N-with-inheritance beats generation-N-without on the same task
distribution, by a margin that survives adversarial refutation.

## Frontier 2 — Learned free-tier multi-provider routing
WHY SOTA FALLS SHORT: routing across 13 free providers with per-provider quotas is
usually static YAML ranks (VECTOR's included). ASSET: `policy_memory` (RL reward) +
`quota_ledger` already capture outcomes and saturation. FIRST 3 STEPS: (1) record
(task, provider, success, latency, quota-cost) tuples in policy_memory; (2) train a
tiny policy to adjust catalog ranks from these; (3) shadow-compare learned vs static
ranks. MILESTONE: learned routing achieves equal-or-better task success at lower
quota saturation than the hand-ranked catalog, measured over a week.

## Frontier 3 — Local-first privacy-preserving autonomy
WHY SOTA FALLS SHORT: capable agent systems lean cloud; privacy is bolted on.
ASSET: VECTOR's sensitivity gate forces local-only for secret/security/RED content,
provably (see proof-toolkit recipe 4). FIRST 3 STEPS: (1) instrument what fraction
of real workload stays local; (2) measure the capability gap local-vs-cloud on that
fraction; (3) close it with better local models / distillation. MILESTONE: a stated
% of sensitive workload handled locally at a measured quality within X% of cloud.

## Frontier 4 — Compounding memory (does the system get smarter or just accumulate?)
WHY SOTA FALLS SHORT: most agent memory accumulates; it rarely demonstrably
compounds. ASSET: VECTOR has episodic/semantic/policy/reasoning substrates +
consolidation. FIRST 3 STEPS: (1) define a "did past memory improve this decision"
metric; (2) ablate memory on repeated task types; (3) measure decision quality vs
memory age/size. MILESTONE: decisions on recurring tasks measurably improve with
memory and degrade without it — compounding, not hoarding. (See
`plans/harness/04-memory-compounding.md`.)

## Discipline reminder
None of these is proven. Before claiming any as a result, route through
`vector-research-methodology` (evidence bar + adversarial refutation) and VECTOR's
change control. External claims must meet the reproducibility bar.

## Provenance and maintenance
2026-07-07. Grounded in existing machinery (`core/city/*`, `core/memory/policy.py`,
`quota_ledger.py`, sensitivity gate). These are directions, not commitments;
re-scope against what a burn-in (`vector-campaign-ship-to-running`) actually reveals.
