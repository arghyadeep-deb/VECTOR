# SELF_DEV_P9_LEGAL_COMPLIANCE — advisory legal and healthcare evidence checks

Date: 2026-09-29  
District: `legal_compliance` (new and deliberately separate)  
Review status: every new tier decision is flagged for pending independent review.

## Source findings and scope

The five requested persona files were absent from `.claude/agents/` in this worktree. In accordance with the task, scope was inferred conservatively from the names and from the existing ingested source copies under `core/prompts/shared/specialized/`:

- `healthcare-customer-service.md`
- `healthcare-marketing-compliance.md`
- `legal-billing-time-tracking.md`
- `legal-client-intake.md`
- `legal-document-review.md`

There was no pre-existing `districts/legal_compliance/` directory, so the district was created once rather than duplicated. All five personas had a bounded, VECTOR-verifiable evidence source and were implemented. No fake LLM-only stub was added. No persona was omitted.

The district is advisory-only, permission-gated through normal Governor dispatch, and never a direct executor. It makes no external calls, writes no owner data, and performs no legal, medical, or compliance action. Every response—including unsupported-task and error responses—carries `advisory_only: true` and states plainly that it is not legal, medical, or compliance advice or certification and requires qualified-professional review.

## Real agents and deterministic evidence

All five classes in `districts/legal_compliance/legal_specialists.py` subclass `core.city.agent_base.AgentBase`, start with real HP, support ghost inheritance, and are registered in `config/agent_manifest.yaml` under the new `legal_compliance` top-level district key.

| Agent | Brief capability | Check capability | What VECTOR actually verifies |
|---|---|---|---|
| `HealthcareCustomerServiceSpecialist` | `healthcare_service_brief` | `healthcare_service_check` | Required interaction fields; emergency and clinical language against supplied escalation flags; identity verification before account discussion; prohibited minimizing phrases; documented next step. |
| `HealthcareMarketingComplianceSpecialist` | `healthcare_marketing_brief` | `healthcare_marketing_check` | Caller-supplied required/prohibited phrases; public prescription-drug promotion flag; patient consent and de-identification metadata; claims against caller-supplied approved scope; citation presence. It explicitly reports that current law was not verified. |
| `LegalBillingTimeTrackingSpecialist` | `legal_billing_brief` | `legal_billing_check` | Non-negative numeric fields; hours × rate per billable entry; zero amount for caller-marked non-billable entries; narratives; invoice subtotal recomputation with decimal arithmetic. |
| `LegalClientIntakeSpecialist` | `legal_intake_brief` | `legal_intake_check` | Required intake fields; opposing-party data; conflict clearance before scheduling; recording and escalation of a known deadline. |
| `LegalDocumentReviewSpecialist` | `legal_document_brief` | `legal_document_check` | Case-insensitive presence of caller-supplied required clause terms and absence of caller-supplied prohibited clause terms in supplied document text. Findings are flagged for attorney review. |

These checks verify only the supplied record. They do not establish that the caller's evidence is authentic, that a clause is enforceable, that marketing complies with current law, that billing is ethical under a particular bar rule, or that a healthcare response is clinically correct. Those determinations require the relevant qualified professional and current jurisdiction-specific sources.

## Permission-tier decisions — all NEW, all pending independent review

The owner required YELLOW by default for every capability in this regulated-advice-adjacent district. That rule was applied without exception. There are **no GREEN entries** and no existing tier was touched, moved, or loosened.

| New action type | Tier | Explicit reason |
|---|---|---|
| `healthcare_service_brief` | YELLOW | Read-only completeness output can still influence patient-support handling. |
| `healthcare_service_check` | YELLOW | Escalation and identity flags are healthcare-adjacent and require staff review. |
| `healthcare_marketing_brief` | YELLOW | Completeness output may shape regulated healthcare communications. |
| `healthcare_marketing_check` | YELLOW | Phrase/scope/consent flags are not a compliance certification and require jurisdiction-specific review. |
| `legal_billing_brief` | YELLOW | Billing-record completeness can affect legal invoices even though the handler does not issue or modify them. |
| `legal_billing_check` | YELLOW | Arithmetic is deterministic, but the result can affect a legal billing decision. |
| `legal_intake_brief` | YELLOW | Intake completeness can influence handling of confidential, deadline-sensitive matters. |
| `legal_intake_check` | YELLOW | Conflict/deadline flags require responsible-attorney or supervisor review. |
| `legal_document_brief` | YELLOW | Document-review completeness is legal-workflow-adjacent. |
| `legal_document_check` | YELLOW | Text matching can surface terms but cannot decide meaning, enforceability, or legal risk. |

All ten additions are marked in `core/config.py` with the same pending-independent-review warning. Exact `DISTRICT_TASK_MAP` entries route every capability to `legal_compliance`; none relies on fuzzy fallback.

## LLM and execution guardrails

There are no LLM call sites in this package. Therefore RULE 1's `ContextEngine().session_hydration_prompt()` prerequisite is not invoked or bypassed. Verification is deterministic and never trusts a model-rendered verdict. The agents do not publish, send, schedule, charge, modify a document, create a client, or perform any direct action.

## Testing and evaluation

Evaluation criteria were defined before implementation:

1. Complete evidence yields a ready brief and deterministic verification.
2. Missing evidence yields `needs_human`, never a fabricated pass.
3. Known unsafe/incomplete fixtures fail their specific safeguards or arithmetic checks.
4. Every response remains advisory-only with the full disclaimer.
5. Manifest registration, exact routing, and YELLOW-only tiering cover all ten capabilities.

`tests/test_legal_compliance_specialists.py` covers those criteria with real agent instances, real manifest/config parsing, and the real Governor map. It does not mock Permission Gateway, HP, or session hydration.

## Verification results

Commands actually run in this shell:

- TDD red run: `python -m pytest tests/test_legal_compliance_specialists.py -v` — failed during collection with `ModuleNotFoundError: districts.legal_compliance`, as expected before implementation.
- Focused green run: the same command — **15 passed** before the final unsupported-response regression was added; the final focused file contains **16 passing tests**.
- Per-file smoke checks:
  - `python districts/legal_compliance/__init__.py` — exit 0 after the smoke-path bootstrap fix.
  - `python districts/legal_compliance/legal_specialists.py` — exit 0; specialist smoke check logged as passed.
  - `python tests/test_legal_compliance_specialists.py` — exit 0; final run **16 passed** through the file's own `__main__`.
- Regression batch: `python -m pytest tests/test_legal_compliance_specialists.py tests/test_governor_unknown_task_gate.py tests/test_regression_governor_capability_routing.py tests/test_v1_trust_t3_permission_vocabulary.py tests/test_a2a_conformance_all_districts.py -v` — first run **70 passed, 1 failed** because the deliberate new YELLOW names were not yet in the frozen vocabulary baseline; after adding exactly those ten names to that guard, the first green run was **71 passed** and the final post-audit run was **72 passed**.
- `python -m py_compile districts/legal_compliance/__init__.py districts/legal_compliance/legal_specialists.py tests/test_legal_compliance_specialists.py` — exit 0.
- Real `ManifestLoader().load()` validation — loaded **221 agents across 40 districts**; asserted **5 legal_compliance agents and 10 capabilities**.
- Forbidden/LLM scan — no `requests`, `flask`, `threading`, `pickle`, production `print`, `vectorcode_llm`, `provider_client`, or `chat(` usage in the new district/test files.
- `git diff --check` — exit 0; only Git's existing LF-to-CRLF working-copy notices were emitted.

The observed pytest warning was the environment's existing `pynvml` deprecation warning from `torch`; no package test failed because of it.

Commit attempt: the scoped `git add`/`git commit` command was run on `vector-dev/p9-legal-manual`, but this managed session mounts the shared worktree `.git` metadata read-only. Git failed before staging with `Unable to create .../.git/worktrees/p9-legal-manual/index.lock: Permission denied`. No commit, push, merge, branch switch, or partial index update occurred. The implementation remains in the working tree for a write-enabled supervisor session to commit.

## Risks and independent-review focus

- Keyword matching is deliberately conservative and may produce false positives or miss synonyms. It is an issue-finding aid, not semantic legal analysis.
- Healthcare-marketing rules change and vary by jurisdiction/platform. The checker uses only caller-supplied rules and metadata; it does not claim live regulatory currency.
- Intake and healthcare-service evidence may contain sensitive data. This implementation keeps it in memory and does not persist or transmit it, but callers remain responsible for data minimization.
- Billing math validates arithmetic, not fee reasonableness, professional-responsibility compliance, or the truth of time entries.
- Clause presence does not establish meaning or enforceability. Independent review should confirm that YELLOW remains suitably conservative and that no capability should be RED in a future execution-coupled workflow.
