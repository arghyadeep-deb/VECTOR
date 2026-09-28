# Coding Self-Development Agents Implementation Plan

**Goal:** Make the selected Coding personas real where VECTOR can verify their work, while reusing existing agents and refusing unverifiable platform/hardware stubs.

**Architecture:** Preserve nineteen existing VECTOR-native matches. Add fourteen focused `AgentBase` subclasses in one shared module. Each new agent exposes an in-memory `<x>_brief` and a deterministic `<x>_check` backed by Python AST parsing, JSON/config parsing, diffing, numeric comparison, or structural validation of caller-supplied evidence. Eight personas that require unavailable external hardware or services remain unbuilt and are disclosed in the package report.

**Tech Stack:** Python 3.12, stdlib `ast`, `difflib`, `json`, `re`, `AgentBase`, PyYAML, pytest.

---

### Task 1: Lock the evidence contracts with tests

**Files:**
- Create: `tests/test_coding_specialists.py`
- Create: `districts/coding/coding_specialists.py`

- [x] Add coverage for every specialist's missing-evidence brief/check behavior.
- [x] Add complete evidence fixtures and require a real deterministic check result.
- [x] Prove HP stays at 500 for incomplete/unverified work and increases only for ready or verified outcomes.
- [x] Add manifest, permission-tier, and exact Governor-route assertions for every declared capability.

### Task 2: Implement fourteen evidence-gated coding specialists

**Files:**
- Create: `districts/coding/coding_specialists.py`

- [x] Implement a shared `CodingSpecialist` base with no LLM dependency.
- [x] Add TypeScript agent-SDK structure, Python business-rule AST, legacy-code AST, scaffold-file, migration-diff, version-delta, data-remediation, optimization-metric, CMS structure, mobile-project, review-comment, type-design AST, MCP-manifest, and terminal-contract analyzers.
- [x] Ensure check results distinguish `verified`, `passed`, individual recomputed checks, and absent evidence.
- [x] Add a real `__main__` smoke check covering all classes.

### Task 3: Register and route every new capability

**Files:**
- Modify: `config/agent_manifest.yaml`
- Modify: `core/config.py`
- Modify: `core/city/governor.py`

- [x] Register all fourteen concrete classes under `coding` with exact class capabilities.
- [x] Add all twenty-eight read-only capabilities to GREEN without changing any existing tier.
- [x] Flag the additions in the config comment for pending independent review.
- [x] Add exact `DISTRICT_TASK_MAP` entries mapping every capability to `coding`.

### Task 4: Document decisions and verify

**Files:**
- Create: `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P2_CODING.md`

- [x] Record all 41 persona dispositions: existing match, newly built, or not built with the verification limitation.
- [x] Record every new GREEN action type and independent-review flag.
- [x] Run focused pytest and `python districts/coding/coding_specialists.py` in this shell.
- [ ] Review the diff, confirm only intended files changed, and commit locally without pushing.
