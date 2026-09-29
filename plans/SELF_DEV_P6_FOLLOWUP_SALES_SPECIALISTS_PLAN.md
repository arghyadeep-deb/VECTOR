# SELF_DEV_P6 follow-up sales specialists plan

## Scope

Build only Agency sales personas with deterministic, caller-evidence checks that are distinct from existing `SalesStrategist`, `ProposalStrategist`, `ClientManager`, and `PerformanceTracker` behavior.

## Decisions

- Build `AccountStrategist`: account health and expansion-risk scoring from supplied account facts.
- Build `DealStrategist`: MEDDPICC completeness and risk check for one supplied deal.
- Build `SalesEngineer`: requirements-to-solution technical fit coverage check.
- Build one `OutboundSequenceStrategist` for both `sales-outbound-strategist` and `sales-outreach`: both reduce to the same real sequence/cadence validation; do not duplicate agents by name.
- Build `PipelineVelocityAnalyst`: stage conversion and velocity math across supplied pipeline transitions, distinct from existing staleness summaries.
- Build `ProposalCoverageStrategist`: required client capability coverage in a supplied proposal, distinct from generic proposal/ROI generation.

## Implementation

- Add `districts/agency/agency_specialists.py` using the `<x>_brief` / `<x>_check` evidence-gated pattern.
- Register new agents in `config/agent_manifest.yaml` under `agency`.
- Add exact routes in `core/city/governor.py`.
- Add GREEN permission-tier entries in `core/config.py`, flagged for independent review.
- Add focused tests in `tests/test_agency_sales_specialists.py`.
- Update `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P6_FOLLOWUP_SALES_SPECIALISTS.md`.

## Verification

- Run the new pytest file.
- Run `python districts/agency/agency_specialists.py`.
- Run `python tests/test_agency_sales_specialists.py`.
- Run `git diff --check`.
- Commit locally, without pushing.
