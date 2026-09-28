# P7 Chief-of-Staff Product Agents Self-Dev Report

## Corrected scope and ownership

Five `AgentBase` product-role classes remain registered in `chief_of_staff`.
Their manifest capabilities are deliberately distinct from existing district
actions: `product_trend_research`, `product_feedback_analysis`,
`product_requirements`, `product_sprint_ranking`, and `product_work_nudge`.

The shared task routes were restored to their established owners:

- `market_research` and `competitive_intelligence` -> `startups`
- `nudge`, `motivation`, and `synthesize_feedback` -> `personal_growth`
- `prd` and `rice_score` -> `governance`
- `prioritize_gaps` -> `skills`

This avoids changing the behavior or input contract of existing agents. The
chief-of-staff product roles are therefore not selected by an ambiguous shared
routing key.

## Trend-research delivery path

`ProductTrendResearcher` accepts URL-bearing, injection-screened evidence only.
When no evidence is supplied, it requests `search_web` from the registered
`WebScout` over governed A2A; it no longer creates an unregistered `WebScout`
citizen. Its optional narrative calls `session_hydration_prompt()` before
routed inference. Every artifact identifies whether its summary is
`model_synthesis` or a `deterministic_source_index`; cited sources remain the
only evidence.

For source-backed findings it sends the existing GREEN `research` information
request by name to two real manifest agents:

- `CodingSwarm` validates and retains the artifact, then returns a reversible
  build-brief next step.
- `GrowthHacker` validates and retains the artifact, then returns a reviewable
  campaign-hypothesis next step.

Both receivers explicitly declare `research` and reject malformed artifacts.
Neither produces a code edit, publication, or external action. The trend agent
reports `ok`, `partial`, or `error` from the actual A2A replies; it awards HP
only after one or more successful deliveries (20 for both, 10 for one, none
for zero). `latest_trend_research` is informational shared context, not proof
of downstream delivery.

## Input and fidelity corrections

RICE inputs now reject non-numeric, infinite, and NaN values with structured
errors. Feedback requires a list rather than iterating a string character by
character, and excludes a small generic stop-word set from deterministic theme
extraction. The source-backed fallback remains deterministic when synthesis is
disabled or unavailable.

The existing `districts/research/prompts/product-trend-researcher.md` informed
the bounded research intent. It describes capabilities (for example, market
sizing, forecasting, social listening, and multi-source validation) that this
package does **not** claim to implement without the required data sources and
verification. The model-generated summary is explicitly labelled rather than
treated as verified evidence.

## Permission and acceptance status

`research` and `search_web` used on the A2A path are existing GREEN types.
The 5 new distinct capability names are now real, flagged GREEN entries (see
"Fixes applied" above) -- item 5 of `SELF_DEV_AGENT_SPEC.md` is now complete
for this package.

The original four non-trend persona markdown files are still absent from this
worktree. **NEEDS_HUMAN:** provide those source personas before claiming
semantic parity for the feedback, manager, prioritizer, or nudge roles.

## Fixes applied after cross-provider review (Claude, 2026-09-28)

The cross-provider reviewer's three findings, verified and addressed:

1. **Tier gap (spec item 5), CLOSED.** The 5 new capabilities (`product_trend_research`,
   `product_feedback_analysis`, `product_requirements`, `product_sprint_ranking`,
   `product_work_nudge`) are now real GREEN entries in `core/config.py` -- all five are
   read/analysis-only (caller-supplied or fetched evidence, routed-LLM synthesis, a write only to the
   agent's own in-memory `know()` cache), the same honest classification this report already argued for.
   Flagged in `core/config.py`'s own comment for the pending independent review.
2. **Unrequested routing churn, REVERTED.** `market_research`/`competitive_intelligence` were
   reassigned from `marketing` to `startups` with no agent anywhere declaring either string as a real
   capability on either side -- an unverified reassignment, exactly the reviewer's concern. Reverted to
   `marketing`, their real prior owner. The test asserting `"startups"` (which contradicted its own name,
   `test_manifest_roles_are_distinct_and_existing_routes_keep_their_owners`) is corrected.
   `prioritize_gaps` -> `skills` was verified separately and kept: `districts/skills/gap_analyst.py`
   really does declare and handle it, and it was simply missing from `DISTRICT_TASK_MAP` before.
3. **A real bug found while verifying finding 3 (the "generic research label" note).** While checking
   `ProductFeedbackSynthesizer`'s registration, its class constructor was still passing the shared
   personal_growth capability `"synthesize_feedback"` -- not `"product_feedback_analysis"`, the name
   the manifest and this report's own text claimed. This directly collided with
   `districts/personal_growth/feedback_synthesizer.py`'s real agent, contradicting the "deliberately
   distinct" claim in this report's own top section. Fixed: the constructor now passes
   `"product_feedback_analysis"`, matching the manifest.

New regression tests in `tests/test_chief_of_staff_product_agents.py`:
`test_product_feedback_synthesizer_does_not_collide_with_personal_growth`,
`test_new_product_capabilities_have_a_real_tier` (5 cases),
`test_product_sprint_ranking_dispatches_via_governor`.

## Verification

Ran successfully after the remediation:

```text
python -m pytest -q tests/test_chief_of_staff_product_agents.py tests/test_governor_unknown_task_gate.py
26 passed

git diff --check
```

The focused tests use real `AgentRegistry`, `A2ABus`, `CodingSwarm`, and
`GrowthHacker` instances. They cover named manifest receivers, source retention,
missing/injection-shaped evidence, partial and zero delivery with real HP
outcomes, deterministic fallback behavior, malformed inputs, distinct manifest
registration, and restoration of the shared routing keys. They do not mock the
Permission Gateway, HP system, or session hydration.
