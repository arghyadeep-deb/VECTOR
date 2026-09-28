# Design Self-Development Agents Design

## Scope approval

The owner's 2026-09-27 implementation task is the approved scope: make the
selected Design personas real under the SELF_DEV_AGENT_SPEC without changing
runtime architecture or permission policy.

## Design

Three required personas already have real, manifest-registered `AgentBase`
implementations: `UIDesigner`, `UXResearcher`, and `ImagePromptEngineer`.
They remain the authoritative implementations; adding aliases would create
competing routes with no new behavior.

Twelve unrepresented personas will share a focused implementation module.
Each concrete class will subclass a common `DesignSpecialist`, itself an
`AgentBase`, and expose two unique read-only task types. A task validates the
provided evidence against a persona-specific brief schema and returns a
traceable report. This makes the work useful without claiming that an LLM has
verified a brand, culture, accessibility property, or spatial experience.

Optional synthesis calls use `ContextEngine.session_hydration_prompt()` before
`core.inference.vectorcode_llm.chat()` and are clearly marked as suggestions,
not evidence. No agent writes files, calls external services directly, or
executes actions.

## Routing and safety

The twenty-four new, exact task types are added to the existing GREEN list and
to `DISTRICT_TASK_MAP`, all routing to `design`. They only construct or audit
in-memory briefs. This is a new tier-vocabulary entry, not a change to any
existing permission level, and requires the independent review named in the
SELF_DEV_AGENT_SPEC.

`ModelQASpecialist` remains in `qa`: its current implementation has real
prediction, bias, and drift calculations and is loaded by `QASwarm`. The
requested P1/QA report is absent from this worktree; the P4 report will state
that finding rather than fabricate it.

## Verification

The new district test will instantiate every concrete specialist, execute its
primary real task with evidence, verify the expected unmet-evidence result,
and verify manifest loading/importability. Existing design and QA tests remain
in scope for regression checks.
