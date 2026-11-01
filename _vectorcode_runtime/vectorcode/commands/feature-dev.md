<!-- VECTOR-INGESTED ASSET
  Source: .claude/commands/feature-dev.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

---
description: Guided VECTOR feature development — codebase exploration, clarifying questions, architecture design, then implementation
argument-hint: Feature description (e.g. "KIITScraper district agent" or "voice wake word pipeline")
---

# VECTOR Feature Development

You are implementing a new VECTOR feature. Follow this systematic approach: understand the codebase, ask about all unknowns, design architecture, then implement.

## Core Rules (always apply)
- Follow all 12 Critical Rules in `vectorcode/rules/critical_rules.md`
- All new agents extend `AgentBase` from `core/city/agent_base.py`
- All new coroutines catch ALL exceptions (RULE 2)
- All actions through `permission_gateway.py` (RULE 3)
- HP wired to actual outcomes (RULE 9)
- Every file needs `if __name__ == "__main__":` smoke test
- Use loguru, never print()

## Phase 1: Discovery

Feature request: $ARGUMENTS

1. Summarize what needs to be built
2. Check `PROGRESS.md` and `phase_status.md` to understand current state
3. Identify which T-day this belongs to (T3/T4/T5/T6/T7)

## Phase 2: Codebase Exploration

Launch 2 parallel agents:
- Agent 1: Find similar existing VECTOR modules — trace through their `__init__`, methods, `__main__` test
- Agent 2: Map dependencies — what does this need from core/ (config, memory, gateway, governor)?

Read all key files identified by agents before proceeding.

## Phase 3: Clarifying Questions

Identify unknowns before designing:
- Which district does this belong to?
- What permission tier (GREEN/YELLOW/RED) are its actions?
- Does it need LLM calls? Which model (follow model routing in models.md)?
- What HP events (success → +X, failure → -Y)?
- What does the `__main__` smoke test need to verify?

**Wait for answers before Phase 4.**

## Phase 4: Architecture

Present 2 options:
1. Minimal — smallest change, maximum reuse of existing modules
2. Clean — right abstractions even if more code

State your recommendation and why. **Wait for user choice.**

## Phase 5: Implementation

DO NOT START without approval.

1. Read all relevant files
2. Implement following chosen architecture
3. Wire HP to outcomes (RULE 9)
4. Wire policy.get_score() BEFORE + update_from_outcome() AFTER (RULE 7)
5. Add `sys.stdout.reconfigure(encoding="utf-8")` at top of `__main__`
6. Smoke test must print `✅ module_name OK` or `❌ FAILED`

## Phase 6: Verify

Run the smoke test: `python core/path/to/module.py`
Confirm ✅ before reporting done.

## Phase 7: Summary

- What was built, what files changed
- Update `PROGRESS.md` status for this module
- Suggest next step in sequence
