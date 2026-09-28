# Chief-of-Staff Product Agents Self-Dev Plan

## Goal

Make the five owner-selected product personas real `chief_of_staff` citizens without
loosening permission policy.  The trend researcher is the primary deliverable: it
must turn source-backed market research into a bounded handoff for `coding` and
`marketing` over the existing governed A2A bus.

## Brainstorming Findings

- No requested product persona is currently registered in `chief_of_staff`.
- Existing implementations already own the shared routes: `startups` owns
  market/competitive research, `personal_growth` owns feedback/nudges,
  `governance` owns PRD/RICE, and `skills` owns gap prioritization. The product
  roles therefore need distinct capabilities and must not retarget those routes.
- `districts/research/prompts/product-trend-researcher.md` is an existing
  ingested prompt asset.  The new agent will reuse its research intent, but will
  ground its output in actual `WebScout` results rather than treating an LLM
  claim as evidence.
- `research` and `search_web` are existing GREEN action types for the bounded
  A2A information path. New distinct chief-of-staff capability names require
  an owner-approved tier decision before Governor exposure.

## Implementation Steps

- [x] Add a shared, `AgentBase`-based product-agent implementation and five
  thin role classes in `districts/chief_of_staff/`.
- [x] Make `ProductTrendResearcher` collect normalized, URL-bearing evidence
  through a registered `WebScout`, call routed inference only after
  `session_hydration_prompt()`, retain a deterministic source-backed fallback,
  and send a structured `research` handoff to named real receivers.
- [x] Register distinct product roles without changing shared Governor routes;
  record the unclassified-new-capability acceptance gate for owner review.
- [x] Give `CodingSwarm` and `GrowthHacker` a real, existing-GREEN `research`
  capability that validates and retains the artifact before proposing a bounded
  build/campaign next step.
- [x] Add real-A2A tests for named manifest receivers, no evidence, injection
  screening, partial/failed delivery and HP outcomes, malformed input, and
  preserved routing. Do not mock the Permission Gateway, HP, or session hydration.
- [x] Run the required unknown-task gate test and report exact outcomes and
  acceptance flags in `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P7_COS.md`.

## Guardrails

- No action tier changes; the report explicitly records that fact.
- A2A delivers only the already-GREEN `research` information request.  It never
  asks `coding` to edit code or `marketing` to publish anything.
- Trend claims remain tied to the returned source list.  If no source evidence
  is available, the agent reports that absence instead of inventing a trend.
