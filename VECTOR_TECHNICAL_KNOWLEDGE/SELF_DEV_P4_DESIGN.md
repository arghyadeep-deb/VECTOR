# SELF-DEV P4 — Design District

Date: 2026-09-27

## Scope and placement decisions

This package implements the owner-selected Design personas under
`SELF_DEV_AGENT_SPEC.md` without adding an executor, external service, or
permission-tier relaxation.

Existing real matches were retained rather than duplicated:

- `design-ui-designer.md` → `districts.design.ui_designer.UIDesigner`
- `design-ux-researcher.md` → `districts.design.ux_researcher.UXResearcher`
- `design-image-prompt-engineer.md` →
  `districts.design.image_prompt_engineer.ImagePromptEngineer`

`specialized-model-qa.md` belongs in `qa`, not Design. The existing
`districts.qa.model_qa_specialist.ModelQASpecialist` computes prediction
metrics, bias disparity, and distribution drift; `districts.qa.agent.QASwarm`
loads it for the `model_qa` role. It was therefore retained rather than
duplicated. The requested P1/QA report was not present anywhere in this
worktree (`rg --files | rg 'SELF_DEV|self_dev|P1.*QA|QA.*P1'` found only the
shared specification); this placement is based on the executable code and
manifest evidence, not a fabricated report reference.

## New real agents

`districts/design/design_specialists.py` contains the following concrete
`AgentBase` subclasses, each born with real HP, generation tracking, and ghost
inheritance support:

| Persona | Exact task types | Independent result |
| --- | --- | --- |
| Brand Guardian | `brand_identity`, `brand_consistency` | Brand-brief evidence report |
| Inclusive Visuals Specialist | `inclusive_visual_review`, `inclusive_prompt` | Representation-evidence report |
| UX Architect | `ux_architecture`, `information_architecture` | UX-architecture evidence report |
| Visual Storyteller | `visual_storyboard`, `visual_narrative` | Narrative-evidence report |
| Whimsy Injector | `whimsy_design`, `microinteraction_audit` | Delight/accessibility evidence report |
| Level Designer | `level_design`, `level_flow` | Progression-evidence report |
| Narrative Designer | `narrative_design`, `narrative_arc` | Narrative-arc evidence report |
| Technical Artist | `technical_art`, `asset_pipeline` | Asset-pipeline evidence report |
| visionOS Spatial Engineer | `spatial_design`, `spatial_comfort` | Spatial-comfort evidence report |
| XR Immersive Developer | `immersive_design`, `immersive_flow` | Immersive-flow evidence report |
| XR Interface Architect | `xr_interface`, `xr_interaction` | XR interaction evidence report |
| Cultural Intelligence Strategist | `cultural_review`, `cultural_brief` | Locale/reviewer evidence report |

The reports are intentionally evidence-based. If a caller omits required
evidence, the result is `needs_human`; no model is asked to assert that a
brand, culture, accessibility property, or spatial experience is correct.
Optional suggestions are explicitly non-evidentiary and call
`ContextEngine.session_hydration_prompt()` before
`core.inference.vectorcode_llm.chat()`. The three retained Design agents and
the retained QA model specialist now use the same hydrated routed-model path.

All new agents are manifest-registered in `config/agent_manifest.yaml` under
`design`, so normal registry bootstrap provides A2A reachability. No separate
A2A mechanism was added.

## Permission review required

The following twenty-four **new GREEN vocabulary entries** were added in
`core/config.py`, and the same names were mapped to `design` in
`core/city/governor.py`:

`brand_identity`, `brand_consistency`, `inclusive_visual_review`,
`inclusive_prompt`, `ux_architecture`, `information_architecture`,
`visual_storyboard`, `visual_narrative`, `whimsy_design`,
`microinteraction_audit`, `level_design`, `level_flow`, `narrative_design`,
`narrative_arc`, `technical_art`, `asset_pipeline`, `spatial_design`,
`spatial_comfort`, `immersive_design`, `immersive_flow`, `xr_interface`,
`xr_interaction`, `cultural_review`, and `cultural_brief`.

Each is an in-memory analysis/brief operation with no execution branch. No
existing GREEN/YELLOW/RED assignment changed. Per the self-dev specification,
these entries require pending independent review.

## Verification evidence

Focused regression coverage is in `tests/test_district_design_specialists.py`.
It executes each new agent's primary task without mocking HP, session
hydration, or the permission gateway; it verifies the evidence-only
`needs_human` result, real HP change, manifest registration/instantiation,
GREEN classification, and governor routing.

Final verification completed on 2026-09-27:

- `pytest tests/test_district_design_specialists.py -v` — **2 passed**.
  The parametrized execution covers all 12 new concrete agents, and the second
  test confirms their manifest import/instantiation, exact GREEN policy entries,
  and Design governor routes.
- `python -m compileall -q districts/design/design_specialists.py
  districts/design/ui_designer.py districts/design/ux_researcher.py
  districts/design/image_prompt_engineer.py districts/qa/model_qa_specialist.py`
  — exit code 0.
- A real deterministic `ModelQASpecialist.audit_predictions()` smoke check
  returned accuracy 1.0 for `[0.9, 0.1]` predictions against `[1.0, 0.0]`
  labels.

`git diff --check` completed without whitespace errors. No dependency,
database-schema, deployment, credential, branch, commit, push, or merge change
was made.
