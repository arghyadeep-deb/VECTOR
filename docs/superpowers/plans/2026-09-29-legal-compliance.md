# Legal Compliance District Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build five real, advisory-only legal/healthcare compliance agents backed by deterministic checks and fully wire them into VECTOR.

**Architecture:** A single focused district module provides shared evidence/disclaimer utilities and five concrete `AgentBase` subclasses. Each agent exposes one brief and one check capability; manifest, Governor, and permission configuration provide the normal VECTOR registration, routing, and gating paths.

**Tech Stack:** Python 3.12, `AgentBase`, dataclasses/type hints, YAML manifest, Pydantic-backed permission config, pytest.

---

### Task 1: Write the district contract tests

**Files:**
- Create: `tests/test_legal_compliance_specialists.py`

- [ ] Define the ten expected capability names and five expected class registrations.
- [ ] Test that the manifest has a distinct `legal_compliance` key and instantiates all five `AgentBase` subclasses.
- [ ] Test every capability is newly YELLOW, absent from GREEN/RED, and exactly routed to `legal_compliance`.
- [ ] Test each brief with complete and missing evidence, including `advisory_only` and the three-domain disclaimer.
- [ ] Test every deterministic checker with passing and failing caller-supplied evidence.
- [ ] Add a `__main__` smoke runner that invokes pytest on this file.
- [ ] Run `pytest tests/test_legal_compliance_specialists.py -v`; expect collection/import failure before implementation.

### Task 2: Implement the deterministic agents

**Files:**
- Create: `districts/legal_compliance/__init__.py`
- Create: `districts/legal_compliance/legal_specialists.py`

- [ ] Add shared constants for the disclaimer and the regulated advisory response envelope.
- [ ] Add a small immutable profile describing each agent's identity, capabilities, evidence fields, and deliverable.
- [ ] Implement a shared `LegalComplianceSpecialist` that initializes `AgentBase`, reports evidence completeness, dispatches only declared capabilities, and never calls a model.
- [ ] Implement healthcare-service checks for emergency/clinical escalation, identity verification, prohibited minimizing phrases, and next-step documentation.
- [ ] Implement healthcare-marketing checks for caller-provided phrase rules, public prescription-drug promotion, patient consent/de-identification, citations, and approval-scope matching.
- [ ] Implement legal-billing arithmetic recomputation and non-billable/invalid-entry checks with decimal-safe comparison.
- [ ] Implement legal-intake required-field, conflict-clearance, scheduling, deadline, and escalation checks.
- [ ] Implement legal-document required/prohibited clause checks over supplied text.
- [ ] Add real `__main__` smoke checks to both new Python files.
- [ ] Run the focused tests; expect behavior tests to pass while wiring tests still fail.

### Task 3: Wire registration, routing, and permissions

**Files:**
- Modify: `config/agent_manifest.yaml`
- Modify: `core/city/governor.py`
- Modify: `core/config.py`

- [ ] Add a new top-level `legal_compliance` manifest key with five class entries and their exact capabilities.
- [ ] Add exact `DISTRICT_TASK_MAP` entries for all ten capability names.
- [ ] Add all ten names to `PermissionConfig.yellow` under a dated comment that explains the YELLOW-default decision and flags independent review.
- [ ] Confirm no existing tier entry changed and no capability is GREEN.
- [ ] Run `pytest tests/test_legal_compliance_specialists.py -v`; expect all tests to pass.

### Task 4: Report and verify

**Files:**
- Create: `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P9_LEGAL_COMPLIANCE.md`

- [ ] Document source discovery, implemented scopes, evidence limitations, all ten YELLOW decisions, no-GREEN rationale, routes, tests, risks, and the absence of LLM calls.
- [ ] Run `python districts/legal_compliance/__init__.py`.
- [ ] Run `python districts/legal_compliance/legal_specialists.py`.
- [ ] Run `python tests/test_legal_compliance_specialists.py`.
- [ ] Run `pytest tests/test_legal_compliance_specialists.py -v` and relevant Governor/config regression tests.
- [ ] Inspect `git diff --check`, the final diff, and status; confirm only scoped files changed.
- [ ] Commit locally with a message naming the ten new YELLOW entries and stating that they require pending independent review. Do not push or merge.

