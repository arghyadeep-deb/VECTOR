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

## Addendum — second follow-up pass, 2026-09-30

Owner approval was given in chat the same day (asked why the remaining 10 not-built personas
couldn't be solved by Claude or Codex; the honest answer required actually re-examining each one
individually rather than repeating the "no evidence source" summary). This pass re-read every one
of the 10 against the same caller-supplied-evidence model the P6 follow-up agents above already
use — none of them need a live external connector, so "no evidence source" only ever meant "no
caller-supplied schema was defined that VECTOR could deterministically check."

Disposition, one by one:

| Persona | Disposition |
| --- | --- |
| government-digital-presales-consultant | Stays not-built. Too regulatory/domain-specific (RFP compliance checklists, government security classification) for a generic deterministic check, and no plausible use case for a personal-owner system. |
| hospitality-guest-services | Stays not-built. No plausible use case — VECTOR's owner does not operate a hospitality business. A double-booking/SLA checker is technically buildable but would be built for a use case that doesn't exist. |
| loan-officer-assistant | **Built** 2026-09-30 (third pass) as `LoanOfficerAssistant`. The "no plausible use case" call above was wrong — the owner's own Blueprint (`(C) Industries — Four Waves.md`) names loan-ops as a Wave 3 vertical candidate, and the plan's own sequencing law explicitly permits building ahead of a wave. The advisory/regulated-compliance gap from the original disclosure stays real and is deliberately not attempted — this agent only checks caller-supplied numbers against caller-supplied criteria (DTI/LTV/credit score/down payment), never approves, denies, or advises. |
| real-estate-buyer-seller | **Built** 2026-09-30 (third pass) as `PropertyMatchAnalyst`. Same correction — named alongside loan-ops as a Wave 3 candidate. Deterministic buyer-requirement-vs-listing match over caller-supplied data, no live MLS/listing-service dependency. |
| recruitment-specialist | **Built** 2026-09-30 (third pass) as `RecruitmentSpecialist`. Fits Wave 2's agentic-back-office-for-SMBs plan (screening/requisition-checking is exactly that shape of service) even though not named explicitly. Deterministic candidate-vs-requisition skills/experience/certification coverage check. |
| retail-customer-returns | Stays not-built. No plausible use case. |
| customer-service | Stays not-built — **genuine duplicate**, not a gap. A drafted-response-vs-required-sections check is exactly `SupportResponder` in `districts/ops/ops_specialists.py` (`support_response_brief`/`support_response_check`, built in P8). Building it again under `agency` would violate the same no-duplication guardrail already applied to `ClientManager`/`SalesStrategist` above. |
| sales-coach | **Built**, collapsed with sales-discovery-coach below. |
| sales-discovery-coach | **Built** as one agent with sales-coach — both need the identical deterministic capability (does a supplied call transcript address each item in a supplied rubric?), differing only in which rubric the caller supplies. Building two agents for one check would be the same count-padding the original P6 follow-up already declined for outbound-strategist/outreach. |
| sales-data-extraction-agent | **Built.** Real MTD/YTD sum arithmetic and per-rep breakdown over caller-supplied raw records, with malformed rows flagged rather than silently dropped. Deliberately does not forecast or project — that would need a real prediction capability this agent does not have. |

Built in `districts/agency/agency_specialists.py`: `SalesCoach` (`sales_coaching_brief`/
`sales_coaching_check`) and `SalesDataExtractionAgent` (`sales_data_extraction_brief`/
`sales_data_extraction_check`). Both follow the established `<x>_brief`/`<x>_check` pattern: brief
reports evidence presence honestly, check performs deterministic verification, zero LLM calls, zero
external side effects.

Verification: 6 new unit tests (20 total in `tests/test_agency_sales_specialists.py`, all pass),
hand-verified the MTD/YTD/malformed-row arithmetic against a worked example before writing the test
(1000+2000=3000 MTD; 1000+2000+500=3500 YTD, excluding a prior-year record; Alice=1500/Bob=2000
per-rep; 2 malformed rows correctly flagged, not silently dropped). Dangerous-primitive grep clean,
manifest integrity clean (41 districts, 270 agents, zero duplicate keys), the `status_check_report`
word-overlap collision fixture still resolves `None`, `compileall` clean, `__main__` smoke check
passes. 2 new GREEN permission-tier entries added, flagged for the pending independent review; no
existing tier touched.

Of the original 17 selected Agency sales personas: 8 real, evidence-gated agents existed after the
two follow-ups above (6 built from the 7 "partial" personas, `sales-outbound-strategist`/
`sales-outreach` collapsed into one; 2 built from 3 of the original "not real" personas,
`sales-coach`/`sales-discovery-coach` collapsed into one). See the third addendum below for the
final 3.

## Addendum — third follow-up pass, 2026-09-30

Owner correction, not a new request: pointed out that 3 of the "no plausible use case" calls in the
second addendum's table above were wrong, because they were reasoned from VECTOR's *current* state
rather than the owner's own already-locked-in 12-year plan (`(C) Industries — Four Waves.md` in the
Brain vault). Two corrections from that document, checked directly rather than from memory:

1. The plan's sequencing law explicitly states **"VECTOR may research and build ahead"** of a wave
   — building a capability before the business operates in that space is not premature by the
   plan's own terms.
2. **Wave 3 (2030-2033) names "real-estate & loan-ops" directly** as a leading vertical candidate.
   The "Explicitly rejected industries" list defers *lending as a licensed business* "until Wave 3
   scale pays for compliance" — but that is about operating a regulated lending business, not about
   VECTOR having a deterministic eligibility-criteria checker ready.

Built 3 more real agents in `districts/agency/agency_specialists.py`:

- **`LoanOfficerAssistant`** (`loan_eligibility_brief`/`loan_eligibility_check`) — DTI, LTV, and
  down-payment-percentage arithmetic against caller-supplied eligibility rules. Deliberately does
  **not** attempt the advisory/regulated side the original disclosure flagged — it never approves,
  denies, or gives lending advice, only reports which caller-defined criteria the supplied numbers
  meet, with an explicit disclaimer field saying so on every response.
- **`PropertyMatchAnalyst`** (`property_match_brief`/`property_match_check`) — resolves
  `real-estate-buyer-seller`. Deterministic buyer-requirement-vs-listing filter/match (budget,
  bedrooms, required features, preferred location) over caller-supplied listings; no live MLS or
  valuation API.
- **`RecruitmentSpecialist`** (`recruitment_fit_brief`/`recruitment_fit_check`) — deterministic
  candidate-vs-requisition coverage check (required skills, minimum experience, required
  certifications) over caller-supplied data.

`customer-service`, `government-digital-presales-consultant`, `hospitality-guest-services`, and
`retail-customer-returns` were **not** reconsidered — they still have no support anywhere in the
Four Waves document (government and hospitality) or are a confirmed duplicate (`customer-service`),
so the second addendum's disposition for those 4 stands.

A real word-overlap collision was caught before finalizing action names, exactly the discipline this
whole program established: `candidate_fit_check` (the first name tried for `RecruitmentSpecialist`)
resolved through `_canonical_district_from_task_type()`'s fallback matcher to the existing self_dev
action `hook_candidate_check` (2 of 3 words overlap: `candidate`, `check`) before it was added to
`DISTRICT_TASK_MAP` as an exact key. Renamed to `recruitment_fit_check`, re-verified clean, and
confirmed the existing `tests/test_self_dev_specialists.py` suite (28 tests) still passes untouched.

Verification: all three agents' arithmetic and matching logic hand-verified against worked examples
before any test was written (loan DTI/LTV percentages, property match/reject reasons per listing,
candidate missing-skills/missing-certifications lists — each checked by hand and confirmed to match
the code's actual output). 10 new unit tests (29 total in `tests/test_agency_sales_specialists.py`,
all pass). Dangerous-primitive grep clean. Manifest integrity clean: 41 districts, 273 agents, zero
duplicate keys. `status_check_report` fixture still resolves `None` (fail-closed intact).
`compileall` clean, `__main__` smoke check passes. 6 new GREEN permission-tier entries added,
flagged for the pending independent review; no existing tier touched. Broader regression: 100 tests
pass across `test_agency_sales_specialists.py`, `test_agency_run_wiring.py`, `test_governor.py`,
`test_owner_routing_closure_f1.py`, `test_v1_trust_t2_action_identity.py`, and
`test_self_dev_specialists.py`.

Of the original 17 selected Agency sales personas: **11 real, evidence-gated agents now exist**
across three follow-ups, covering 13 of the 17 persona names (several collapsed into one agent
where the underlying capability was identical). The remaining 4 stay honestly not-built:
`government-digital-presales-consultant` and `hospitality-guest-services` (no support anywhere in
the owner's own 12-year plan), `retail-customer-returns` (same — not named in any of the four
waves), and `customer-service` (a confirmed duplicate of `ops.SupportResponder`, not a gap).
