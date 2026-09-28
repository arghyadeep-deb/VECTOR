# SELF_DEV_P8_MEMORY_FINANCE_OPS — memory_curator + finance + ops personas

Spec followed: `SELF_DEV_AGENT_SPEC.md`. Branch: `vector-dev/c74ecf3829b444c1b81c2b1146c24b20`.

Scope: `identity-graph-operator.md`, `lsp-index-engineer.md`, `zk-steward.md` (district=memory_curator);
`finance-bookkeeper-controller.md`, `finance-fpa-analyst.md` (district=finance); `hr-onboarding.md`,
`project-management-experiment-tracker.md`, `project-management-jira-workflow-steward.md`,
`project-management-project-shepherd.md`, `project-management-studio-operations.md`,
`project-management-studio-producer.md`, `support-analytics-reporter.md`,
`support-executive-summary-generator.md`, `support-finance-tracker.md`,
`support-infrastructure-maintainer.md`, `support-legal-compliance-checker.md`,
`support-support-responder.md`, `accounts-payable-agent.md`, `data-consolidation-agent.md`,
`report-distribution-agent.md`, `corporate-training-designer.md`, `language-translator.md`
(district=ops, with the legal_compliance/finance placement check for two of them).

**Persona `.md` files were not found in this worktree's `.claude/agents/`** (spot-checked
`identity-graph-operator.md`, `lsp-index-engineer.md`, `zk-steward.md` — all "does not exist"),
same disclosed limitation as `SELF_DEV_P5_MARKETING`. Every persona's scope below is inferred from
its name and its district's domain, not from the persona's own text.

## Review-fix pass (after independent review, CHANGES_REQUIRED)

1. **Governor routing** — 20 exact `DISTRICT_TASK_MAP` entries added in `core/city/governor.py`
   (memory_curator 4, ops 14, legal_compliance 2); `tests/test_ops_specialists.py` asserts every
   specialist capability has its exact route.
2. **AccountsPayableAgent removed** (class, `three_way_match` analyzer, manifest entry, 2 GREEN tier
   entries, tests). It duplicated `finance-bookkeeper-controller`'s stated AP/three-way-match scope in
   `finance`; that persona is now listed as already-real, not rebuilt. The ops section below that still
   describes it and the "8 new agents / 22 tier entries" counts are superseded: ops now has **7** new
   agents, and the package adds **20** GREEN tier entries.
3. **Failed checks no longer earn HP** — in all three specialist bases, an audit action earns HP only
   when `verification.verified` is true and `verification.passed` is not `False`; a brief still earns
   on `ready`. `LSPIndexEngineer.passed` is now also `False` on parse errors. Tests added for both.
4. **`FPAAnalyst.generate_monthly_narrative`** now calls `ContextEngine().session_hydration_prompt()`
   before `chat()` (RULE 1); on any failure it uses the existing deterministic fallback text.

Not run at the time this was written: no shell was available in this pass. Claude ran everything
for real afterward -- see "Verification status" below.

## Verification status (updated by Claude 2026-09-29)

Actually run: `python -m compileall` on all 3 new specialist files (OK); `pytest
tests/test_memory_curator.py tests/test_ops_specialists.py tests/test_legal_compliance_specialists.py`
(62 passed, including a new regression test for the IdentityGraphOperator fix below); each file's own
`__main__` smoke check (all 3 passed); the manifest YAML parse (226 agents, 40 districts, OK).

## memory_curator — disposition

| Persona | Disposition |
| --- | --- |
| `identity-graph-operator` | **New, real.** `IdentityGraphOperator` (`districts/memory_curator/memory_curator_specialists.py`) — deduplicate-candidate detection over caller-supplied entity records: groups records by the normalized value of every caller-named `match_fields`, reports clusters with more than one record. Pure dict/set computation over exactly the rows supplied — no LLM, no invented data. |
| `lsp-index-engineer` | **New, real.** `LSPIndexEngineer` — parses caller-supplied Python source with the stdlib `ast` module (real static parsing, not a model guess), lists top-level `def`/`class` names per file, and diffs against an optional `expected_symbols` list. Syntax errors are reported as `parse_errors`, not silently swallowed. |
| `zk-steward` | **Already real — NOT rebuilt, NEEDS_HUMAN on district placement.** `ZKSteward` (`districts/personal_growth/zk_steward.py`) already subclasses `AgentBase`, is manifest-registered, and is A2A-reachable — but under `district="personal_growth"`, not `memory_curator` as this spec's district map (`SELF_DEV_AGENT_SPEC.md` line 30) names it. Per the spec's own guardrail ("check whether the persona already has a real match... don't duplicate what exists under a different name" / "ambiguous district placement -> stop and mark NEEDS_HUMAN, don't guess"), this package does **not** move, rename, or duplicate `ZKSteward` — moving a live, tested, already-registered agent's `district` attribute and manifest section is a real behavioral change (`get_by_district()` filters on it) outside this bounded task's scope. Flagging for an explicit owner decision: either update the spec's district map to say `personal_growth`, or approve a follow-up task to move the agent. |

New tier entries (GREEN, `core/config.py`): `identity_graph_brief`, `identity_dedup_check`,
`lsp_index_brief`, `lsp_symbol_check`. Manifest: 2 new entries under `memory_curator:`.

## finance — disposition

Both personas already have real matches; **no new code was written for finance.**

| Persona | Disposition |
| --- | --- |
| `finance-bookkeeper-controller` | **Already real.** `districts/finance/finance-bookkeeper-controller.md` already exists and is self-loaded as a real `PromptAgent` (subclasses `AgentBase`) by `FinanceSwarm._load_agents()` (`districts/finance/agent.py`, `MD_FILES` list) the moment `FinanceSwarm` is instantiated — same mechanism already used for the other 4 finance `.md` personas and approved by the earlier `SELF_DEV_P6_AGENCY`/`P7` reviews for this exact pattern (`CodingSwarm`/`ResearchSwarm` self-load their sub-agents the same way). It is A2A-reachable once loaded, since any registered `AgentBase` is. |
| `finance-fpa-analyst` | **Already real.** `FPAAnalyst` (`districts/finance/fpa_analyst.py`) is a manifest-registered `AgentBase` with real deterministic methods (`variance_analysis`, `rolling_forecast`, `budget_vs_okr`) and an optional narrative LLM path (only place in this whole persona pair that calls a model, and it does not gate correctness on the model's opinion — the narrative is prose framing around numbers already computed deterministically). |

No manifest or tier change needed for finance; both were already correctly wired before this package.

## ops — disposition

17 personas, `district=ops` per this spec. Of these: **1 already has a real match in the same
district** (no new code), **5 have real matches in a different existing district** (not
duplicated — flagged below), **8 are new, real, evidence-checked agents** in
`districts/ops/ops_specialists.py`, **2 needed a placement decision** (both resolved per the
task's explicit instruction), and **1 has no honest deterministic check** (disclosed, not built).

### Already real — same district, no new work

| Persona | Match |
| --- | --- |
| `support-infrastructure-maintainer` | `DevOpsAutomator` (`districts/ops/devops_automator.py`), already manifest-registered under `ops:` via `OpsSwarm`'s self-load, already covers process restarts, log cleanup, DB backups, Fly.io/Cloudflare health. |

### Already real — different district, NOT duplicated (NEEDS_HUMAN: district-map vs. actual placement)

| Persona | Existing match | Actual district |
| --- | --- | --- |
| `project-management-experiment-tracker` | `ExperimentTracker` (`districts/projects/experiment_tracker.py`), manifest-registered | `projects` |
| `support-analytics-reporter` | `AnalyticsReporter` (`districts/data_analytics/analytics_reporter.py`), manifest-registered | `data_analytics` |
| `support-executive-summary-generator` | `ChiefOfStaff.morning_brief`/`evening_brief`/`executive_brief` (`districts/chief_of_staff/chief_of_staff.py`), manifest-registered | `chief_of_staff` |
| `accounts-payable-agent` | `finance-bookkeeper-controller.md`'s own deliverables list explicitly includes "Accounts Payable: Invoice processing, three-way matching, payment scheduling..." — the broader Bookkeeper/Controller persona already covers this scope in `finance` | `finance` |
| `support-finance-tracker` | see the explicit placement decision below | `finance` |

Same reasoning as `zk-steward` above: these personas are not rebuilt under `ops` because doing so
would be exactly the duplication the spec's guardrail forbids ("don't duplicate what exists under a
different name"). This is disclosed as a district-map-vs-reality mismatch for the owner to resolve
(update the map, or approve moving the existing agents), not guessed past.

### Placement decisions (explicitly requested by this task)

- **`support-finance-tracker`** -> **finance**, not `ops` or `legal_compliance`. `districts/finance/expense_tracker.py`
  (categorised expense tracking from UPI/SMS) and `districts/finance/budget_analyst.py` (budget/variance
  tracking) already cover this persona's scope inside the `finance` district that already exists and is
  already manifest-registered. There is nothing regulated or ops-specific about generic finance tracking
  that would justify a new/duplicate `ops` agent — this is a plain existing-match case, not an ambiguous one.
- **`support-legal-compliance-checker`** -> **new `legal_compliance` district**, not `ops` or `finance`.
  `SELF_DEV_AGENT_SPEC.md` explicitly names `legal_compliance/` as a **new** district "kept separate on
  purpose... because regulated advice needs its own tier discipline", and this persona's actual job
  (checking regulated documents for required/prohibited language) is exactly that discipline, not a
  general ops task or a numbers-tracking finance task. `districts/governance/compliance_auditor.py`
  (`ComplianceAuditor`, SOC2/GDPR) is a *related* but *not identical* existing agent — it is a
  `PromptAgent` whose `audit_data_handling()` asks a model to render `COMPLIANT`/`NON-COMPLIANT`/
  `NEEDS-REVIEW` and trusts that verdict, which is a pre-existing agent outside this package's scope,
  not rebuilt here. The new `LegalComplianceChecker` (below) is deliberately narrower and does not
  repeat that pattern: it never asks a model for a verdict, only searches supplied text for
  caller-named required/prohibited phrases (guardrail #7: verification must check something other
  than the model's own claim). Registered under a new `legal_compliance:` manifest section per the
  spec's own district map — this is the "NEW district" the spec pre-authorizes, not a guess.

### New, real, evidence-checked agents (`districts/ops/ops_specialists.py`)

Same `<x>_brief` / `<x>_check` contract as the approved `SELF_DEV_P5_MARKETING`/`P4_DESIGN` specialist
packages: `<x>_brief` reports which persona-specific evidence the caller supplied and what's missing;
`<x>_check` is the verification action and recomputes something from the supplied data — it never asks
a model whether the work is good. **None of these 8 agents calls an LLM at all** (simpler and safer than
the marketing package's optional free-text-suggestion path, and it means RULE 1 session hydration does
not apply to any of them — there is no LLM call site to hydrate).

| Persona | Agent | What `<x>_check` really verifies |
| --- | --- | --- |
| `hr-onboarding` | `HROnboardingSpecialist` | Every `required: true` checklist item has `done: true`; lists incomplete ones by name. |
| `project-management-jira-workflow-steward` | `JiraWorkflowSteward` | A supplied issue's `transition_history` only ever moves between states allowed by a supplied `allowed_transitions` graph; flags the exact invalid hop and its step index. |
| `project-management-project-shepherd` | `ProjectShepherd` | Which supplied, incomplete milestones have a `due_date` before `as_of_date` (real date arithmetic via `datetime.date`), with days-overdue. |
| `support-support-responder` | `SupportResponder` | A drafted reply's text contains every caller-named `required_sections` phrase (case-insensitive substring search); lists what's missing. |
| `accounts-payable-agent` | `AccountsPayableAgent` | Three-way match: invoice amount vs. purchase-order amount (within a caller-set tolerance %), invoice amount vs. goods-receipt amount, invoice quantity <= received quantity, received quantity <= ordered quantity. Real arithmetic on the three supplied documents, distinct from the broader Bookkeeper/Controller persona's scope in `finance`. |
| `data-consolidation-agent` | `DataConsolidationAgent` | Merges 2+ caller-supplied record lists by a caller-named `key_field`; for every key that appears in more than one source, flags any field whose value disagrees across sources. Distinct from `ConsolidationBot` (`districts/memory_curator/consolidation_bot.py`), which compresses VECTOR's own episodic memory into semantic summaries — a different capability (VECTOR's internal memory vs. caller-supplied external datasets) despite the shared word "consolidation". |
| `report-distribution-agent` | `ReportDistributionAgent` | Every supplied recipient string looks like a syntactically valid email address (contains `@` and a `.` after it); the supplied report format is one of the allowed formats. **Never sends or distributes anything** — validation only, exactly per the persona name's own scope. |
| `corporate-training-designer` | `CorporateTrainingDesigner` | Supplied curriculum `modules` are non-empty-named, unique, and each has a truthy `assessment` field; lists which modules are missing one. Same "structure check" pattern already approved for `BookCoAuthor`'s outline check in `SELF_DEV_P5_MARKETING`. |

### Not built — disclosed, not faked

| Persona | Why not built |
| --- | --- |
| `project-management-studio-operations` | No VECTOR-accessible studio-operations evidence source (staffing, budget-vs-schedule, pipeline data for a creative studio) exists to recompute from. Building a brief-only stub with no check would be the "evidence-completeness brief, no honest check" pattern already used for several `SELF_DEV_P5_MARKETING` personas (e.g. `china_ecommerce_operator`) — but even the brief here has no distinguishing evidence fields from `project-management-project-shepherd`'s generic milestone tracking, so it would just be a renamed duplicate. Not built; needs an owner decision on what "studio operations" means concretely for VECTOR before it can be given real, non-duplicate scope. |
| `project-management-studio-producer` | Same reasoning as `studio-operations` — no distinguishing, VECTOR-verifiable evidence source separate from `ProjectShepherd`. Not built. |
| `language-translator` | No deterministic translation-quality check exists without an actual bilingual reference/dictionary resource, and VECTOR has no such resource wired in (the 5 `districts/languages/*_coach.py` agents are one-way vocabulary/practice coaches, not translators, and don't provide one). A translation "check" without a real reference to compare against would be exactly the "faking behavior with an LLM-only stub" the guardrail forbids (there is no honest way to verify a translation's correctness by re-asking a model whether its own translation is right). Not built. |

New tier entries (GREEN, `core/config.py`): `hr_onboarding_brief`, `hr_onboarding_check`,
`jira_workflow_brief`, `jira_workflow_check`, `project_shepherd_brief`, `project_shepherd_check`,
`support_response_brief`, `support_response_check`, `accounts_payable_brief`,
`accounts_payable_match_check`, `data_consolidation_brief`, `data_consolidation_check`,
`report_distribution_brief`, `report_distribution_check`, `training_design_brief`,
`training_outline_check`. Manifest: 8 new entries under `ops:`.

## legal_compliance — new district

New `districts/legal_compliance/` (with `__init__.py` and `legal_compliance_specialists.py`),
registered as a new `legal_compliance:` top-level key in `config/agent_manifest.yaml` — this is the
district the spec itself pre-authorizes ("Two NEW districts: `legal_compliance/`... kept separate
on purpose... regulated advice needs its own tier discipline"). No changes were made to any district
enum/registry list beyond the manifest, because `core/city/declarative_manifest.py`'s `ManifestLoader`
treats district names as free-form YAML keys (confirmed by reading it) — a new key needs no other
wiring to be instantiated and registered.

`LegalComplianceChecker` (`legal_compliance_brief` / `legal_compliance_check`): checks that a supplied
document's text contains every caller-named `required_clauses` phrase and none of an optional
`prohibited_phrases` list — a real, deterministic string search, not a model verdict. Every response
carries `advisory_only: True` and the check's own `note` states plainly that it "does not constitute
legal advice or a compliance certification" — this keeps it inside the spec's cross-district rule
("`legal_compliance` <-> anyone touching regulated claims — advisory-only, gated, never a direct
executor").

New tier entries (GREEN, `core/config.py`): `legal_compliance_brief`, `legal_compliance_check`.
Manifest: 1 new entry under a new `legal_compliance:` section.

## Fixes applied after the second cross-provider review round (Claude, 2026-09-29)

Ran everything for the first time (compile check, all three test files, all three `__main__` smoke
checks, the manifest YAML parse): all green. Then fixed the review's 3 findings:

1. **`zk-steward` hydration gap, CLOSED.** `districts/personal_growth/zk_steward.py`'s two direct
   `chat()` call sites (`extract_concepts`, `find_connections`) were missing
   `ContextEngine().session_hydration_prompt()`. Fixed both.
2. **`finance-bookkeeper-controller` hydration gap, CLOSED -- and generalized.** The real call site
   is not `finance-bookkeeper-controller.md` itself but `core/city/prompt_agent.py`'s
   `PromptAgent.ask()` -- the *shared* LLM call path for every `.md`-driven district citizen that
   never overrides `run()`/`ask()` (12 agents across coding/research/finance/qa/governance/
   data_analytics, not just this one finance persona). It had no hydration call at all. Fixed once in
   the shared base class, closing the same gap for all 12 agents rather than one. New test:
   `tests/test_prompt_agent_hydration.py`.
3. **`IdentityGraphOperator` false-positive-duplicate bug, CLOSED.** `row.get(f, "")` only falls back
   to `""` when a key is *absent*; a field explicitly present with value `None` stayed `None`, and
   `_normalize(None)` (`str(None).strip().lower()`) produced the non-empty string `"none"` -- so two
   records each missing the same field via an explicit null (not absence) clustered together as a
   false-positive duplicate instead of being skipped as incomplete evidence. Fixed: an explicit
   `None` in any match field now skips the record, same as a missing one. New regression test:
   `test_identity_graph_operator_check_null_match_field_is_skipped_not_clustered`.

## What was NOT done (disclosed, follow-up needed)

- **`core/city/governor.py`'s `DISTRICT_TASK_MAP`** was not updated with exact routes for the 22 new
  capability names in this pass (`SELF_DEV_P5_MARKETING`'s own report shows this same gap was found
  and fixed only in a *second* independent-review pass for that package, not the first). Without an
  exact entry, `Governor.dispatch()`'s substring/word-overlap fallback may misroute some of these new
  task types to an unrelated district on first contact, the same class of bug that review found for
  marketing. Flagging this explicitly rather than silently shipping the same known gap twice.
- No agent in this package calls an LLM, so no new hydration call sites were added or needed to be
  checked for RULE 1 compliance — this was a deliberate scope-narrowing decision (see the ops section
  above), not an oversight.
- `zk-steward`'s district placement (`personal_growth` vs. this spec's `memory_curator`) and the four
  finance/data_analytics/chief_of_staff/finance cross-district matches under `ops` are left as explicit
  `NEEDS_HUMAN` flags per the guardrail, not resolved by moving code.

## Verification (to be run, see "Verification status" above)

```text
python -m compileall -q districts/memory_curator/memory_curator_specialists.py \
  districts/ops/ops_specialists.py districts/legal_compliance/legal_compliance_specialists.py
pytest -q tests/test_memory_curator.py tests/test_ops_specialists.py tests/test_legal_compliance_specialists.py
python districts/memory_curator/memory_curator_specialists.py
python districts/ops/ops_specialists.py
python districts/legal_compliance/legal_compliance_specialists.py
python -c "from core.city.declarative_manifest import ManifestLoader; ManifestLoader().load()"  # YAML still parses
```
