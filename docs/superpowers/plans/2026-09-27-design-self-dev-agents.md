# Design Self-Development Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the selected Design personas real, safely routed VECTOR agents without duplicating the existing design or QA implementations.

**Architecture:** Preserve the three existing design agents and the QA model-auditing specialist. Add twelve focused `AgentBase` subclasses in one shared module; their primary operations produce evidence-based, in-memory design briefs. Register their exact task types in the manifest, governor map, and GREEN policy vocabulary.

**Tech Stack:** Python 3.12, `AgentBase`, `ContextEngine`, `vectorcode_llm`, PyYAML, pytest.

---

### Task 1: Add evidence-based design specialists

**Files:**
- Create: `districts/design/design_specialists.py`
- Test: `tests/test_district_design_specialists.py`

- [x] **Step 1: Write a parametrized failing test for every new class**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("agent_cls", SPECIALIST_CLASSES)
async def test_specialist_builds_evidence_report(agent_cls):
    agent = agent_cls()
    result = await agent.run({"type": agent.capabilities[0], "evidence": {}})
    assert result["status"] == "ok"
    assert result["report"]["status"] == "needs_human"
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_district_design_specialists.py -v`

Expected: FAIL because `districts.design.design_specialists` does not exist.

- [x] **Step 3: Implement the twelve concrete `AgentBase` subclasses**

```python
class BrandGuardian(DesignSpecialist):
    profile = SpecialistProfile("BrandGuardian", "brand_guardian_001", "brand_identity", "brand_consistency", (...))
```

Each profile supplies the exact evidence fields for its read-only brief; the
base class constructs `missing_evidence` from submitted fields. Its optional
LLM path must prepend `ContextEngine().session_hydration_prompt()` and use
`vectorcode_llm.chat(..., district="design", domain="vision")`.

- [x] **Step 4: Run the unit test to verify it passes**

Run: `pytest tests/test_district_design_specialists.py -v`

Expected: all parametrized specialist cases PASS.

### Task 2: Register exact, read-only task routes

**Files:**
- Modify: `config/agent_manifest.yaml`
- Modify: `core/config.py`
- Modify: `core/city/governor.py`
- Test: `tests/test_district_design_specialists.py`

- [x] **Step 1: Extend the manifest's design district**

Add one entry for every new concrete class with the two exact profile task
types. Preserve the existing `ui_designer`, `ux_researcher`, and
`image_prompt_engineer` entries unchanged.

- [x] **Step 2: Add only the new read-only task types to GREEN**

Add `brand_identity`, `brand_consistency`, `inclusive_visual_review`,
`inclusive_prompt`, `ux_architecture`, `information_architecture`,
`visual_storyboard`, `visual_narrative`, `whimsy_design`,
`microinteraction_audit`, `level_design`, `level_flow`, `narrative_design`,
`narrative_arc`, `technical_art`, `asset_pipeline`, `spatial_design`,
`spatial_comfort`, `immersive_design`, `immersive_flow`, `xr_interface`,
`xr_interaction`, `cultural_review`, and `cultural_brief`. Do not alter any
existing tier assignment.

- [x] **Step 3: Add the same twenty-four exact routes to the design district**

```python
"brand_identity": "design",
"cultural_brief": "design",
```

- [x] **Step 4: Verify manifest load and route completeness**

Run: `pytest tests/test_district_design_specialists.py -v`

Expected: manifest loads every new class and each declared capability is
GREEN and maps to `design`.

### Task 3: Record the package evidence

**Files:**
- Create: `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P4_DESIGN.md`

- [x] **Step 1: Write the P4 report**

Record the existing-agent match decisions, QA placement decision, exact new
GREEN entries requiring independent review, tests run, and the absence of the
requested P1/QA report in this worktree.

- [x] **Step 2: Run focused and regression verification**

Run: `pytest tests/test_district_design_specialists.py -v; python -c "from core.city.declarative_manifest import ManifestLoader; print(len(ManifestLoader().load()))"`

Expected: tests pass and the manifest loads successfully.
