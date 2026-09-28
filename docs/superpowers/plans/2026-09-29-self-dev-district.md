# Self-Development District Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build seven deterministic, evidence-checked `self_dev` agents behind a test-enforced capability boundary that prevents direct product-code access.

**Architecture:** A shared `SelfDevSpecialist` base owns evidence readiness, task dispatch, and HP rules while seven pure analyzer functions validate caller-supplied agent, plugin, skill, comparison, grading, and hook artifacts. Registration, permissions, and routing remain explicit and isolated to the new district.

**Tech Stack:** Python 3.12+, stdlib `ast`/`json`/`re`/`difflib`, `AgentBase`, PyYAML manifest loading, pytest.

---

### Task 1: Lock the contract with focused tests

**Files:**
- Create: `tests/test_self_dev_specialists.py`

- [x] Define all seven expected class paths and fourteen capabilities.
- [x] Add complete caller-supplied evidence fixtures for every analyzer.
- [x] Assert missing evidence yields `needs_human`, unverified checks, and no HP.
- [x] Assert complete evidence yields ready/verified output and HP only on passing outcomes.
- [x] Assert one structurally invalid artifact fails and earns no HP.
- [x] Assert manifest registration, GREEN-only tiers, and exact `self_dev` routes.
- [x] Parse the implementation source with `ast` and reject direct `districts.coding` or `core.city.governor` imports and every filesystem-write primitive.
- [x] Run `python -m pytest tests/test_self_dev_specialists.py -v`; expect collection failure before the district exists.

### Task 2: Implement the isolated deterministic specialists

**Files:**
- Create: `districts/self_dev/__init__.py`
- Create: `districts/self_dev/self_dev_specialists.py`

- [x] Add immutable specialist profiles and a shared `SelfDevSpecialist` base.
- [x] Implement pure deterministic analyzers for agent AST, plugin JSON, skill review, skill analysis, skill comparison, weighted grading, and hook/conversation coverage.
- [x] Add seven concrete `AgentBase` subclasses with two exact capabilities each.
- [x] Award HP only for a ready brief or a verified passing check.
- [x] Add a real `__main__` smoke check covering all seven agents with missing and complete evidence.
- [x] Run the focused pytest file and fix only failures caused by this package.

### Task 3: Wire registration, routing, and permissions

**Files:**
- Modify: `config/agent_manifest.yaml`
- Modify: `core/city/governor.py`
- Modify: `core/config.py`

- [x] Register exactly seven agents under the new `self_dev` district.
- [x] Add exactly fourteen `DISTRICT_TASK_MAP` routes to `self_dev` and no other district.
- [x] Add exactly fourteen GREEN actions with an explicit pending-independent-review comment; do not change any existing tier.
- [x] Run the focused pytest file and real manifest instantiation assertions.

### Task 4: Document and verify the package

**Files:**
- Create: `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P10_SELF_DEV.md`
- Modify: `docs/superpowers/plans/2026-09-29-self-dev-district.md`

- [x] Record absent source personas, inferred scope, deterministic behavior, all new tier entries, boundary enforcement, risks, verification evidence, and `NEEDS_HUMAN` disclosures.
- [x] Run `python -m pytest tests/test_self_dev_specialists.py -v`.
- [x] Run `python districts/self_dev/self_dev_specialists.py`.
- [x] Run `python tests/test_self_dev_specialists.py`.
- [x] Run targeted routing/permission regression tests, `py_compile`, forbidden-import/write scans, and `git diff --check`.
- [x] Inspect the complete diff for security, unnecessary code, unrelated changes, and boundary violations.
- [ ] Stage only scoped files and commit locally with every new tier action named in the commit body; blocked because the managed shell cannot create the worktree `index.lock` in the read-only parent `.git` directory. No staging, push, merge, or branch change occurred.
