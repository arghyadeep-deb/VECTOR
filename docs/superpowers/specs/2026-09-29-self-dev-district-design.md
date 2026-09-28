# Self-Development District Design

Date: 2026-09-29

## Scope

Create a new `self_dev` district containing seven real `AgentBase` specialists inferred from the requested persona names because their `.claude/agents/` source files are absent in this worktree. The district improves VECTOR's own agent, plugin, skill, and hook tooling by inspecting caller-supplied artifacts in memory. It does not edit files, execute commands, call an LLM, or act on product code.

## Boundary

`self_dev` is a distinct capability and routing domain. Every new manifest registration and exact Governor route belongs only to `self_dev`. The implementation may import `AgentBase` but may not import `districts.coding`, `core.city.governor`, or any product-code executor. It performs no filesystem writes. If later work requires a coding-district opinion or action, it must use the inherited governed `a2a_ask` interface and target a registered coding agent; direct in-process access is forbidden.

## Components

- `districts/self_dev/self_dev_specialists.py`: one shared evidence-gated base and seven deterministic specialists.
- `districts/self_dev/__init__.py`: district exports.
- `config/agent_manifest.yaml`: seven registrations under a single new `self_dev` key.
- `core/city/governor.py`: fourteen exact routes, all to `self_dev`.
- `core/config.py`: fourteen new GREEN action types, explicitly marked for pending independent review.
- `tests/test_self_dev_specialists.py`: behavior, HP, manifest, tier, routing, and source-boundary regression tests.
- `VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_P10_SELF_DEV.md`: findings, limitations, tier decisions, verification, risks, and any `NEEDS_HUMAN` disclosures.

## Specialist behavior

Each specialist has a brief action and a check action. A brief reports `ready` only when all declared evidence fields are present. A check is `verified` only when its analyzer can deterministically recompute checks from valid evidence. HP increases only for a ready brief or a verified passing check; missing or failing evidence never earns HP.

The analyzers cover:

1. Agent-definition metadata and Python AST structure.
2. Plugin JSON manifest shape, identifiers, entrypoints, and permission declarations.
3. Skill document frontmatter and required instruction sections.
4. Skill structure, imperative steps, referenced resources, and unresolved placeholders.
5. Baseline/candidate skill comparison against explicit expected changes.
6. Weighted grading against explicit caller-supplied criteria and evidence.
7. Conversation-to-hook rules checked against supplied transcript events and hook definitions.

## Error handling and verification semantics

Unsupported task types return an error without HP. Invalid or incomplete evidence returns an unverified result with a reason rather than raising or fabricating a verdict. Analyzer exceptions are caught, logged with `loguru`, and deduct HP as a real failed task. No LLM is used, so session hydration is neither required nor bypassed.

## Test strategy

The focused test file uses real agent instances and real manifest/config/map data. It covers complete and missing evidence for every specialist, a known failing verification, exact HP behavior, exact `self_dev` routing and GREEN-only classification, manifest instantiation, and an AST/source regression proving the implementation has no direct coding/Governor import and no filesystem-write call. The module smoke check and pytest file are both executed directly before completion.

