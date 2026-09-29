# SELF-DEV P6 follow-up -- Agency sales specialists

## Scope and result

Owner approval was supplied in chat on 2026-09-29. This follow-up revisited the seven Agency personas that the earlier P6 package correctly left as partial-only. The rule for this pass stayed strict: a persona became real only if VECTOR can verify caller-supplied evidence deterministically, without asking an LLM to certify its own output.

Six new `AgentBase` citizens were built in `districts/agency/agency_specialists.py`. The apparent seven-persona list produces six real agents because `sales-outbound-strategist` and `sales-outreach` collapse to the same independently checkable capability: outreach sequence cadence/channel validation. Building two agents for the same check would be count-padding, not a real distinction.

## Built agents

| Persona | Built agent | Evidence-gated capability |
| --- | --- | --- |
| sales-account-strategist | `AccountStrategist` | Computes account health and expansion-risk from caller-supplied engagement history, contract value, renewal date, expansion signals, and stakeholder map. |
| sales-deal-strategist | `DealStrategist` | Checks one deal's MEDDPICC fields and flags missing/weak fields. |
| sales-engineer | `SalesEngineer` | Compares supplied technical requirements against a supplied solution/integration design and flags uncovered capabilities. |
| sales-outbound-strategist / sales-outreach | `OutboundSequenceStrategist` | Validates touches, channel diversity, max touches per week, and duplicate same-day touches. |
| sales-pipeline-analyst | `PipelineVelocityAnalyst` | Computes stage conversion and average stage velocity from supplied transition data, distinct from `SalesStrategist.analyze_pipeline()` stage/staleness summaries. |
| sales-proposal-strategist | `ProposalCoverageStrategist` | Checks required client capabilities against proposal-addressed capabilities and flags omissions. |

Every agent follows the same pattern:

- `<x>_brief` reports required, present, and missing evidence only.
- `<x>_check` performs deterministic verification over supplied data.
- No LLM call is used.
- No external send, CRM write, proposal generation, file write, or network action is performed.
- HP is awarded only on `ready` brief or `passed` check outcomes.

## Wiring

Manifest registrations were added under `agency` in `config/agent_manifest.yaml`:

- `account_strategist`
- `deal_strategist`
- `sales_engineer`
- `outbound_sequence_strategist`
- `pipeline_velocity_analyst`
- `proposal_coverage_strategist`

Exact governor routes were added in `core/city/governor.py`:

- `acct_health_brief`, `acct_health_check`
- `deal_meddpicc_brief`, `deal_meddpicc_check`
- `tech_fit_brief`, `tech_fit_check`
- `out_seq_brief`, `out_seq_check`
- `pipe_velocity_brief`, `pipe_velocity_check`
- `prop_coverage_brief`, `prop_coverage_check`

The action names were chosen as exact keys and checked against the known ambiguous owner-routing fixture class (`status_check_report`, `report_distribution_validate`) so they do not depend on `_canonical_district_from_task_type()` word-overlap fallback behavior.

## Permission tiers

The 12 new action types were added to `core/config.py` as GREEN, with an inline comment flagging them for the pending independent review per `SELF_DEV_AGENT_SPEC.md`. This does not loosen any existing tier entry. The GREEN classification is based on the handlers being read-only, in-memory checks over caller-supplied evidence, apart from standard AgentBase HP accounting.

## Not built / merged disclosure

No persona was left unbuilt for lack of a distinguishing evidence source after this pass.

`sales-outbound-strategist` and `sales-outreach` were intentionally not built as two separate agents. The existing `SalesStrategist.write_outreach()` already covers LLM-based copy drafting for both names. The only distinct deterministic capability available here is sequence validation, and that evidence contract is the same for both personas. The single `OutboundSequenceStrategist` is therefore the honest real implementation.

## Verification

Planned verification:

```text
pytest -q tests/test_agency_sales_specialists.py
python districts/agency/agency_specialists.py
python tests/test_agency_sales_specialists.py
git diff --check
```
