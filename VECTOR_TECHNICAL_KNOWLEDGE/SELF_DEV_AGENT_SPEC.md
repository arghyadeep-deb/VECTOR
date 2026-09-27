# VECTOR self-dev program: making the owner's selected Claude Code personas real (owner-approved 2026-09-27)

The owner selected 239 Claude Code agent personas (from `.claude/agents/` across the VECTOR Codebase repo, the Brain vault, the
global marketplace, and installed plugins) that VECTOR should eventually be able to do itself, without Claude or Codex. This spec
is what every district package in this program must follow. Read it once per package; don't ask the owner to repeat it.

## What "real" means (not persona copying)

A selected persona becomes real only when the resulting agent:
1. Subclasses `core.city.agent_base.AgentBase` — real HP (born 500), ghost memory, generation tracking, like every other citizen.
2. Declares real `capabilities` (its actual task types) and is registered in `config/agent_manifest.yaml` under the district this
   package names.
3. Calls models through `core.inference.vectorcode_llm` / `core.inference.provider_client` — free-tier/local routing (RULE 11:
   no paid Anthropic/OpenAI key at runtime), `session_hydration_prompt()` before every LLM call (RULE 1, no exceptions).
4. Is reachable via the A2A bus automatically (any registered `AgentBase` is) — do not build a separate mechanism.
5. Has its action types classified GREEN/YELLOW/RED in `core/config.py`. **Any new tier entry must be named explicitly in the
   package's own commit message / report and flagged for the pending independent review — never added silently, never used to
   loosen an existing entry.**
6. Has at least one real test per `.claude/rules/testing.md` (no mocking `permission_gateway`, HP, or `session_hydration`).
7. Where the persona's job is to check/verify something (review, QA, security, PR-toolkit personas): the verification must check
   something other than the model's own claim — a real diff, a real test run, a real static check, a real file — never "ask the
   LLM if it's good and trust the answer." This is the same discipline `core/city/work_board.py`'s drills already use.

## District map (owner-approved; see also `docs/OPEN_ISSUES.md` / chat history for the reasoning)

Existing districts absorb most of this: `coding/` (Engineering, PR review toolkit, Legacy modernization pipeline, Agent SDK
tooling), `security/` (Security scan pipeline + existing security agents), `qa/` (Testing-* — mostly already real, verify first),
`marketing/` (Marketing + paid-media-*), `design/` (Design + XR/spatial + narrative/level/technical-artist), `agency/` (Sales +
real-estate/loan-officer/hospitality/retail/recruitment/gov-presales), `chief_of_staff/` (orchestrator/planner/context-loader/
cross-linker/brag-spotter/slack-archaeologist/people-profiler/product-*/review-*), `memory_curator/` (vault-librarian/vault-
migrator/vc-codebase-explorer/zk-steward/lsp-index-engineer/identity-graph-operator), `finance/`, `ops/` (project-management-*,
support-*, HR-onboarding). Two NEW districts: `legal_compliance/` (Legal + healthcare personas — kept separate on purpose, never
folded into a general district, because regulated advice needs its own tier discipline) and `self_dev/` (Claude Code meta-tooling
— VECTOR improving its own tooling, must never touch product code directly; only talks to `coding/`).

Academic/worldbuilding personas (anthropologist, geographer, historian, narratologist, psychologist) are explicitly OUT OF SCOPE
for this program — they don't fit "build apps/websites from research and trends." Do not build them without a separate owner
decision.

## Inter-district A2A links to wire (informational — most already work once agents are registered normally)

`coding/` <-> `design/`, `coding/` <-> `security/`, `coding/` <-> `qa/` (every build cycle), `coding/` <-> `marketing/` (what
ships shapes the campaign and vice versa), `marketing/` <-> `agency/` (campaign to deal handoff), `legal_compliance/` <-> anyone
touching regulated claims (finance, healthcare, sales) — **advisory-only, gated, never a direct executor**, `self_dev/` <-> only
`coding/`, `chief_of_staff/` <-> everyone (unchanged, it's the router today).

## Guardrails (every package)

- No permission tier loosened, ever.
- No fabricated capability: if a persona's description doesn't map to something VECTOR can actually verify, say so in the
  report instead of faking behavior with an LLM-only stub.
- Ambiguous district placement or scope -> stop and mark `NEEDS_HUMAN`, don't guess.
- One task-branch (`vector-dev/<task_id>`) per package, merged only into `vector-integration`. Never the owner's live branch
  (`fix/external-review-2026-09` or `main`), never pushed, never deployed.
- Before building anything in a district, check whether the persona already has a real match in that district (see the `qa/`
  package for the pattern) — VECTOR already has ~230 real agents; don't duplicate what exists under a different name.
