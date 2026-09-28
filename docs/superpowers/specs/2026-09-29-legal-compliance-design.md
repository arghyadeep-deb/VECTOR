# Legal Compliance District Design

## Scope

Create a deliberately isolated `legal_compliance` district for five selected personas. Each persona is a real `AgentBase` subclass with two advisory-only capabilities: an evidence-completeness brief and a deterministic check over caller-supplied data. The district never executes an external action and never represents an output as legal, medical, or compliance advice or certification.

The source persona files are absent from `.claude/agents/`. Their ingested prompt copies under `core/prompts/shared/specialized/` establish the narrow scopes used here. No persona is implemented beyond evidence VECTOR can recompute.

## Components and capability contracts

`districts/legal_compliance/legal_specialists.py` contains five focused agents:

1. `HealthcareCustomerServiceSpecialist`
   - `healthcare_service_brief`: reports whether an interaction record supplies its text, inquiry type, identity-verification status, escalation target, and documented next step.
   - `healthcare_service_check`: deterministically flags emergency language without an emergency escalation, clinical requests without licensed-clinician escalation, account discussion without identity verification, prohibited minimizing phrases, and missing documented next steps.
2. `HealthcareMarketingComplianceSpecialist`
   - `healthcare_marketing_brief`: reports completeness for content text, audience, product category, approval scope, citations, and patient-content metadata.
   - `healthcare_marketing_check`: deterministically checks caller-supplied required/prohibited phrases, public prescription-drug promotion, patient-content consent/de-identification, citation presence, and approval-scope matching. It does not claim current-law certification.
3. `LegalBillingTimeTrackingSpecialist`
   - `legal_billing_brief`: reports completeness for time entries and invoice totals.
   - `legal_billing_check`: recomputes per-entry amounts and invoice subtotal, checks non-negative numeric inputs, flags caller-marked non-billable entries, and compares supplied totals with a small decimal tolerance.
4. `LegalClientIntakeSpecialist`
   - `legal_intake_brief`: reports completeness for prospect identity/contact, matter type, opposing parties, key facts, urgency/deadline information, conflict status, and next step.
   - `legal_intake_check`: checks required fields, refuses to treat non-cleared conflicts as schedulable, and flags deadlines without escalation.
5. `LegalDocumentReviewSpecialist`
   - `legal_document_brief`: reports completeness for document text/type, parties, represented party, jurisdiction, and caller-supplied clause rules.
   - `legal_document_check`: case-insensitively checks required and prohibited clause terms in supplied text and reports exact missing/matched terms for attorney review.

Every success and error response carries `advisory_only: true` plus a plain disclaimer that the output is not legal, medical, or compliance advice or certification. Missing evidence produces `needs_human`; checks never infer absent facts.

## Wiring and permission posture

The five agents are registered beneath a new top-level `districts.legal_compliance` key in `config/agent_manifest.yaml`. All ten capability names receive exact `DISTRICT_TASK_MAP` routes to `legal_compliance`.

All ten new permission names are YELLOW. Although the handlers are read-only, their outputs can influence regulated decisions. The package therefore applies the owner-mandated YELLOW default and makes no GREEN exception. No existing permission entry is changed or loosened. These additions are explicitly flagged for pending independent review in code and in the package report.

## Error handling and tests

The agents accept only dictionaries/lists of dictionaries, return structured errors rather than throwing through the Governor, and use `loguru` for failures. They do not call an LLM, so session hydration is not applicable.

`tests/test_legal_compliance_specialists.py` verifies manifest registration, unique capabilities, YELLOW-only tiering, exact Governor routes, `AgentBase` inheritance, advisory disclaimers on every path, ready/missing briefs, passing/failing deterministic checks, and explicit disclosure that source personas were inferred from the ingested prompt copies. The new district files and test file include real `__main__` smoke checks.

