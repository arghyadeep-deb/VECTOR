# SELF-DEV P6 — Agency district report

## Scope and result

This bounded repair strengthens existing Agency agents; it does not certify a
new persona or create a new agent. The Agency placement is explicit in
`SELF_DEV_AGENT_SPEC.md`. The repair makes two existing, data-backed read
paths safely reachable from a governor-shaped unmatched chat task, and fixes
Rule 1 hydration omissions in all five direct Agency LLM call sites.

No selected persona is newly labelled **Real** by this package. The existing
agents remain ordinary `AgentBase` citizens and manifest entries; adjacent
legacy capabilities are not treated as a persona match merely because they
share a noun such as “client” or “sales”.

## Implemented, evidence-backed repair

- `districts/agency/client_manager.py:answer_client_question()` accepts only
  explicit client read questions: a question shape, the word `client`/`clients`,
  and a constrained summary or churn-risk phrase are all required. Mutation
  verbs return `None`, so `run()` retains the standard unhandled-type error.
  Chat-routed at-risk results contain only name, status, and engagement score;
  contact and notes remain off this free-text path.
- `districts/agency/performance_tracker.py:answer_performance_question()` has
  the same question/read/mutation gate. A trend requires a named persisted
  metric. `_metrics_named_in_query()` uses token boundaries and returns every
  match; an abbreviated name matching more than one metric returns the explicit
  `ambiguous metric reference` error instead of using insertion order.
- `districts/agency/sales_strategist.py`,
  `districts/agency/proposal_strategist.py`, and
  `districts/agency/content_strategist.py` now call
  `ContextEngine.session_hydration_prompt()` before each direct
  `vectorcode_llm.chat` / `ProviderClient.chat` invocation and make it the
  leading system message. Provider/model routing is unchanged.

The affected agents were already manifest registered under `agency`:
`config/agent_manifest.yaml` entries `content_strategist`,
`proposal_strategist`, `sales_strategist`, `client_manager`, and
`performance_tracker_agency` (around lines 790–821). No manifest entry was
added. The existing read action types are already GREEN in
`core/config.py:PermissionConfig.green` (around lines 318–333):
`client_summary`, `get_at_risk_clients`, `get_metric_summary`, `get_trend`,
and `active_alerts`. `alert_anomaly`, `track_metric`, and `remove_metric` are
already YELLOW (around lines 388–400). This package adds no tier entry and
does not loosen an existing tier.

## Selected-persona disposition

| Selected persona | Disposition and specific evidence/gap |
| --- | --- |
| government-digital-presales-consultant | Not real. No Agency procurement source, government compliance checklist, or verifiable RFP workflow exists. |
| hospitality-guest-services | Not real. No guest, reservation, property, or service-request evidence source exists in Agency. |
| loan-officer-assistant | Not real. No loan facts, eligibility rules, or regulated advisory flow exists; a future design needs `legal_compliance` advisory input. |
| real-estate-buyer-seller | Not real. No listing, buyer, seller, or property-match source exists. |
| recruitment-specialist | Not real. No employer-side candidate/requisition workflow exists in Agency. |
| retail-customer-returns | Not real. No order evidence, return-policy evaluator, or return-authorisation workflow exists. |
| sales-account-strategist | Partial only. `ClientManager` is a CRM/engagement record (`client_manager.py`), not an account-plan or account-strategy persona. This repair only exposes two narrow reads safely. |
| sales-coach | Not real. There is no supplied-call transcript schema, scoring rubric, or independently checkable coaching result. |
| sales-data-extraction-agent | Not real. There is no configured sales-data input contract, source connector, extraction validator, or error-reporting workflow. |
| sales-deal-strategist | Partial only. `SalesStrategist.analyze_pipeline()` calculates supplied-deal stage and staleness summaries (`sales_strategist.py:analyze_pipeline`), but does not produce a verified deal-strategy workflow. |
| sales-discovery-coach | Not real. No discovery-call capture, rubric, or evidence-based review is implemented. |
| sales-engineer | Partial only. `ProposalStrategist` builds generic proposal structure and ROI (`proposal_strategist.py:build_proposal_structure` / `calculate_roi`); it does not validate requirements, integrations, or demos. |
| sales-outbound-strategist | Partial only. `SalesStrategist.write_outreach()` drafts copy and is now hydrated, but it has no prospect-data source, sequence management, or independently verifiable outreach outcome. |
| sales-outreach | Partial only. The same hydrated draft-copy method exists; no sending or outcome evidence is implemented. |
| sales-pipeline-analyst | Partial only. The deterministic pipeline calculation operates on caller-supplied deals, not a validated pipeline source, and this package does not add a distinct persona/test contract for it. |
| sales-proposal-strategist | Partial only. Proposal/ROI helpers are present and LLM calls are now hydrated, but no verifiable client requirements or proposal-evaluation source makes the full persona real. |
| customer-service | Not real. CRM engagement storage is not an evidence-based customer-support response workflow. |

Sales-coach, discovery-coach, and data-extraction are plausible future bounded
designs, but they require a defined input schema, deterministic validation or
rubric evidence, `AgentBase`/manifest capability registration, tier review,
and real tests. They did not exist in the repair’s scope; adding prompt-only
copies would violate the no-fabricated-capability guardrail.

## Verification

Executed in this worktree:

```text
python -m compileall -q districts/agency/client_manager.py \
  districts/agency/performance_tracker.py \
  districts/agency/sales_strategist.py \
  districts/agency/proposal_strategist.py \
  districts/agency/content_strategist.py
pytest -q tests/test_agency_run_wiring.py
22 passed
git diff --check
```

`tests/test_agency_run_wiring.py` now proves a returned summary/trend comes
from records it creates and removes in `finally` blocks. It covers mutation and
substring-like false positives, unknown/vague chat, ambiguous metric names,
and the original explicit unhandled-type contract. Its hydration tests use the
real `ContextEngine.session_hydration_prompt()` and replace only the external
LLM transport to capture emitted messages; session hydration itself is not
mocked.

## Fix applied after cross-provider review (Claude, 2026-09-28)

The cross-provider reviewer found a real crash bug in `answer_performance_question()`: the outer
guard (`not has_question_shape or not (asks_alerts or asks_summary or (asks_trend and
metric_matches))`) only requires ONE of `asks_alerts`/`asks_summary`/`asks_trend-with-a-named-metric`
to be true to proceed — so a query combining an alert or summary cue with a trend cue but no named
metric (e.g. "Are there any active alerts and how is the trend?") reached `if asks_trend:
metric_name = metric_matches[0]` with an empty `metric_matches`, raising `IndexError`. Fixed: the
trend branch now requires `asks_trend and metric_matches` (skips gracefully when no metric is
named). New regression test:
`test_performance_tracker_chat_alert_plus_trend_with_no_named_metric_does_not_crash` in
`tests/test_agency_run_wiring.py`.

The reviewer's other objection ("no selected persona is made real") is this package's own explicit,
disclosed scope decision, not an oversight: of the 17 selected personas, 10 have no real evidence
source or workflow in VECTOR at all (procurement data, guest/reservation records, loan facts,
property listings, candidate pipelines, order/return records, call transcripts, sales-data
connectors, discovery-call capture) and building them would mean an LLM-only stub asserting things
it cannot verify -- exactly what `SELF_DEV_AGENT_SPEC.md`'s "no fabricated capability" guardrail
forbids ("if a persona's description doesn't map to something VECTOR can actually verify, say so in
the report instead of faking behavior with an LLM-only stub"). The other 7 are correctly disclosed
as "partial" -- existing agents (`SalesStrategist`, `ProposalStrategist`) already cover a narrow,
real slice of them. This disposition is accepted; building fabricated personas to satisfy a literal
17-of-17 count would violate the spec this whole program exists to enforce.

## Risk and follow-up

The parsers intentionally prefer a visible unhandled-type error to a guessed
answer. Some informal but harmless wording may therefore be rejected until a
new deterministic read pattern is justified by a regression test. No external
action, database schema, dependency, production configuration, credential,
manifest, or permission-policy change was made. No new action type requires
independent tier review.

## Addendum — follow-up pass, 2026-09-29

Owner approval was given in chat the same day ("do it, u can use codex n urself for the task"),
directly acting on this report's own disclosed 7-persona "partial" list above. The disposition on
those 7 was correct at the time it was written (existing agents covered only a narrow slice), but
this follow-up asked, for each one, whether a genuinely distinct, deterministic, VECTOR-verifiable
capability existed beyond what the existing agents already did — and found one for 6 of the 7.

Built in `districts/agency/agency_specialists.py`: `AccountStrategist` (account health/expansion-risk
from caller-supplied engagement data, distinct from `ClientManager`'s engagement-record lookup),
`DealStrategist` (single-deal MEDDPICC completeness, distinct from `SalesStrategist.analyze_pipeline()`'s
list-level staleness math), `SalesEngineer` (technical-requirement-coverage check, distinct from
`ProposalStrategist`'s generic structure-building), `OutboundSequenceStrategist` (touch/channel/cadence
validation, distinct from `SalesStrategist.write_outreach()`'s LLM copy drafting),
`PipelineVelocityAnalyst` (stage conversion/velocity math, distinct from `analyze_pipeline()`'s
staleness summary), `ProposalCoverageStrategist` (required-vs-addressed capability coverage check).

`sales-outbound-strategist` and `sales-outreach` were confirmed to be the same underlying deterministic
capability under two names and deliberately collapsed into the one `OutboundSequenceStrategist` agent —
building two would have been count-padding, not a real distinction, and this report's own "no
fabricated capability" standard governed that call the same way it governed the original 10 not-built
personas below.

The other 10 personas disclosed as not-built above (procurement data, guest/reservation records, loan
facts, property listings, candidate pipelines, order/return records, call transcripts, sales-data
connectors, discovery-call capture) were **not** re-examined in this follow-up — this pass was scoped
to the 7 "partial" personas only. They remain honestly disclosed as not built pending a future pass
that specifically re-asks whether VECTOR has grown a verifiable evidence source for any of them since
this report was written.

Verification: 14/14 new unit tests pass (`tests/test_agency_sales_specialists.py`), 102 broader
regression tests pass, dangerous-primitive grep clean (no subprocess/eval/exec/os.system, no LLM
calls), manifest integrity clean, the `status_check_report` word-overlap collision fixture still
resolves `None` (fail-closed intact), `compileall` clean, both new files' own `__main__` smoke checks
pass. Built by Codex in worktree `p6-followup-sales-specialists`, independently verified and committed
by Claude, merged into `fix/external-review-2026-09` clean (no conflicts). 12 new GREEN permission-tier
entries added, flagged for the pending independent review; no existing tier touched. Full detail:
`SELF_DEV_P6_FOLLOWUP_SALES_SPECIALISTS.md`.
