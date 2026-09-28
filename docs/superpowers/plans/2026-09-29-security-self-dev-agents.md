# Security Self-Development Agents Implementation Plan

**Goal:** Add the non-duplicative, verifiable Security personas while keeping
patch work proposal-only and disclosing unsupported blockchain auditing.

**Architecture:** Preserve the existing scan/detection/redaction pipeline. Add
eight focused `AgentBase` subclasses in one shared module. Each class exposes a
brief and deterministic check over caller-supplied evidence. Register exact
capabilities in the manifest, Governor, and proposed GREEN vocabulary.

## Task 1: Pin behavior with tests

- [x] Add `tests/test_security_specialists.py`.
- [x] Cover complete and missing evidence for every specialist.
- [x] Prove patch proposal and verification cannot write, execute, apply,
  commit, or merge anything.
- [x] Verify manifest registration, `AgentBase` inheritance, exact Security
  routing, and proposed GREEN tiers.
- [x] Run the focused test and confirm it fails before implementation.

## Task 2: Implement deterministic specialists

- [x] Add `districts/security/security_specialists.py`.
- [x] Generate patch proposals with `difflib.unified_diff` in memory only.
- [x] Parse and verify proposals without running their validation commands.
- [x] Implement inventory hashing, JSON scan loading, research provenance,
  scan coverage, identity/scope/expiry, and automation-control checks.
- [x] Return `needs_human` whenever required independent evidence is absent.
- [x] Include a real `__main__` smoke check.

## Task 3: Register and classify exact actions

- [x] Add eight manifest entries under `security`.
- [x] Add all sixteen exact action routes to `DISTRICT_TASK_MAP`.
- [x] Add all sixteen new actions to GREEN with the required independent-review
  comment; do not modify any existing tier.

## Task 4: Verify and report

- [x] Run the focused pytest suite.
- [x] Run the specialist module and test file `__main__` checks.
- [x] Run compile and whitespace checks plus relevant manifest/routing tests.
- [x] Record matches, new agents, every tier proposal, verification evidence,
  risks, and every `NEEDS_HUMAN` item in
  `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P3_SECURITY.md`.
- [ ] Review the final diff, then commit locally without pushing or merging.
  Diff review completed; local commit is `NEEDS_HUMAN` because this session
  cannot create the parent repository's `.git/worktrees/.../index.lock`.
