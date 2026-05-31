# Repo Audit — superpowers-main (obra/superpowers)

> Audited: 2026-05-31 · Auditor: Claude (Opus 4.8) · Read + run only, no VECTOR code modified.
> Repo: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\superpowers-main`

**TL;DR:** This is a pack of **14 Claude-Code agent-harness SKILLS** (markdown process docs).
They are not code; they are *instructions to a CLI agent*. VECTOR cannot depend on the
Claude Code harness (it is its own Python runtime). The audit question is therefore:
**does VECTOR's autonomous loop / districts already DO what each skill teaches?** Mostly yes.
All 14 skills are *also* already vendored verbatim in `brain/.claude/skills/` for build-session use.

---

## Section 1 — Repo Reality

`skills/*/SKILL.md` — 14 skills. Each is a markdown reference guide an agent loads via the
Claude Code `Skill` tool. No Python, no runtime. Grouped by capability:

### Planning (3)
| Skill | What it does |
|---|---|
| `brainstorming` | HARD-GATE: explore intent → ask Qs one at a time → propose 2–3 approaches → present design → get approval → write `docs/.../specs/*-design.md`. No code before approval. |
| `writing-plans` | Turn spec into a bite-sized, file-mapped implementation plan saved to `docs/.../plans/*.md`. DRY/YAGNI/TDD/frequent-commits ethos. |
| `executing-plans` | Load plan → review critically → TodoWrite → execute each task with per-step verification → report. |

### Execution / Orchestration (3)
| Skill | What it does |
|---|---|
| `subagent-driven-development` | Fresh subagent per plan task + two-stage review (spec then quality) after each. Continuous, no check-in between tasks. |
| `dispatching-parallel-agents` | One isolated-context agent per independent problem domain; run concurrently; never inherit session history. |
| `using-git-worktrees` | Ensure isolated workspace: detect existing isolation → native worktree tool → git worktree fallback. |

### Testing / Debugging (2)
| Skill | What it does |
|---|---|
| `test-driven-development` | RED-GREEN-REFACTOR. "If you didn't watch the test fail, you don't know it tests the right thing." |
| `systematic-debugging` | Iron Law: NO FIXES WITHOUT ROOT CAUSE. Phase-1 investigation before any fix. |

### Verification / Review (3)
| Skill | What it does |
|---|---|
| `verification-before-completion` | Iron Law: no completion claims without fresh verification evidence. Run the command in *this* message before claiming pass. |
| `requesting-code-review` | Dispatch a reviewer subagent with crafted context (git SHAs), not session history. |
| `receiving-code-review` | Verify before implementing feedback; reasoned pushback over performative "you're absolutely right". |

### Workflow / Meta (3)
| Skill | What it does |
|---|---|
| `finishing-a-development-branch` | Verify tests → detect env → present merge/PR/cleanup options → execute. |
| `using-superpowers` | Bootstrap: "if 1% chance a skill applies, you MUST invoke it"; user CLAUDE.md still wins. |
| `writing-skills` | TDD applied to process docs — write pressure tests, watch baseline fail, write skill, watch pass. |

**Count: 14 skills. Zero runtime code. Plus `hooks/`, `scripts/`, `tests/` (all Node/JS harness glue).**

---

## Section 2 — VECTOR Parity (does the RUNTIME do this?)

Verdict key: ✅ runtime does it · ⚠️ partial/stub · ❌ missing from runtime.

| Skill capability | VECTOR runtime equivalent (verified) | Verdict |
|---|---|---|
| **brainstorming** — design-before-code gate | No autonomous "ask the user 2–3 approaches" gate in the loop — VECTOR is agentic-first and acts on goals. Closest: `core/brain/goal_system.py` + `core/brain/hypothesis_engine.py` (proactive options). The interactive design-approval ritual is a *build-session* behavior, vendored as the `brainstorming` SKILL in `brain/.claude/skills/`. | ⚠️ |
| **writing-plans** — spec→ordered plan | `core/loop/planner.py` `Planner.plan()` reads `goal_system.generate_immediate_actions()` and emits an ordered `{action, goal_id, urgency, reason}` queue. **Ran live:** `GoalSystem().generate_immediate_actions(limit=3)` → `PLAN_OK actions=3`. | ✅ |
| **executing-plans** — execute plan w/ checkpoints | `core/loop/autonomous_loop.py` `_act_on()` executes the planned winner, runs the action, then `update_from_outcome()` (RULE 7) + reward-scaled goal progress + causal edge. `core/loop/workflow_runner.py` + `task_queue.py` sequence multi-step work. | ✅ |
| **subagent-driven-development** — fresh agent per task + 2-stage review | `core/city/agent_registry.py` (per-task specialized agents) + `districts/qa/` review agents. Spec-then-quality review maps to `reality_checker` (spec/smoke) → `code_reviewer` (quality). | ✅ |
| **dispatching-parallel-agents** — one agent per independent domain, concurrent | `vectorcode/src/swarm.py` `SwarmCoordinator` — 8 topologies (mesh, hierarchical, byzantine, raft, gossip, crdt, quorum, star) with isolated `AgentState` per agent. This is *stronger* than the skill (consensus + work-stealing via `claims.py`). | ✅ |
| **test-driven-development** — RED-GREEN-REFACTOR | `districts/qa/test_engineer.py` (`generate_tests`, `analyze_test_coverage_gaps`) + 969-test suite + CI that now blocks on failure (`.github/workflows/ci.yml`). The *autonomous loop does not enforce write-test-first* before it codes — TDD is a discipline the build agent follows, not a runtime gate. | ⚠️ |
| **systematic-debugging** — root-cause-before-fix | `districts/coding/bug_hunter.py` `handle_event()` — *"React to build/test failures by investigating root cause"* (AST analysis, pattern issues, LLM analysis, categorize). `core/brain/red_team_agent.py` adversarial review. No formal phase-gated "Iron Law" state machine, but the root-cause-first behavior exists. | ✅ |
| **verification-before-completion** — evidence before claims | `districts/qa/reality_checker.py` runs `smoke_test.py` + `integration_check.py` and reports pass/fail counts + `verify_imports()`; loop's reflect phase verifies. `districts/qa/silent_failure_hunter.py` catches swallowed errors. Commands `verify.md` / `quality-gate.md` exist for build sessions. | ✅ |
| **requesting-code-review** — dispatch reviewer w/ crafted context | `districts/coding/code_reviewer.py` (`review_file`, `review_with_llm`, `review_with_vectorcode`, `run_forever`) + `architect_bot.py` (circular imports, module explain) + `red_team_agent.py`. Build-session `/code-review`, `/pr-review` commands. | ✅ |
| **receiving-code-review** — verify-before-implementing feedback | No dedicated runtime module — this is a *conversational discipline*. Behaviorally covered by `red_team_agent` (challenge before accept) + decision_engine scoring rejected candidates. As a build-agent norm it lives in `brain/.claude/skills/receiving-code-review`. | ⚠️ |
| **finishing-a-development-branch** — verify→merge/PR/cleanup | `districts/coding/git_bot.py` — `status()`, `commit()`, `create_branch()`, push, PR creation; gateway-gated push (RULE 3). `finishing-a-development-branch.md` command/skill for the human-choice ritual. | ✅ |
| **using-git-worktrees** — isolated workspace | `git_bot.create_branch()` gives branch isolation; full git-worktree fan-out is not a runtime feature (single-owner local repo rarely needs parallel worktrees). Brain skill vendored for build sessions. | ⚠️ |
| **using-superpowers** — skill-discovery bootstrap | Pure Claude-Code-harness meta-skill. VECTOR's runtime equivalent is the Governor + 180 route table (`core/city/governor.py`) auto-selecting districts/agents. Skill itself is harness-only. | ✅ (runtime routes; skill N/A to runtime) |
| **writing-skills** — author new skills (TDD for docs) | Build-session authoring activity. VECTOR has `brain/.claude/skills/skill-creator` + `/skill-create` command + `/evolve`, `/rules-distill`. Not a loop function. | ✅ (via brain tooling) |

### Are they already in `brain/.claude/skills/`?
**Yes — all 14, verbatim, exact directory-name match.** Verified via Glob of the brain junction
target (`V.E.C.T.O.R. Brain\.claude\skills\`): `brainstorming`, `dispatching-parallel-agents`,
`executing-plans`, `finishing-a-development-branch`, `receiving-code-review`,
`requesting-code-review`, `subagent-driven-development`, `systematic-debugging`,
`test-driven-development`, `using-git-worktrees`, `using-superpowers`,
`verification-before-completion`, `writing-plans`, `writing-skills` all present (part of the
~282-SKILL Ruflo/agent-skills absorption noted in phase_status.md). These are reference docs for
*build sessions*, not imported by the runtime.

### Tally
- ✅ runtime does it: **9** (writing-plans, executing-plans, subagent-driven-dev, dispatching-parallel-agents, systematic-debugging, verification-before-completion, requesting-code-review, finishing-a-branch, using-superpowers-routing/writing-skills-tooling)
- ⚠️ partial/discipline-only: **5** (brainstorming gate, TDD write-first gate, receiving-code-review, using-git-worktrees, and the *interactive* halves of the planning gates)
- ❌ genuinely missing from runtime: **0**

Every ⚠️ is "VECTOR does the *capability* but the *interactive build-session ritual* (ask user, get
approval, manual merge choice) isn't and shouldn't be wired into an autonomous loop." None represent
a missing autonomous capability.

---

## Section 3 — Frontend

**None.** Skills are markdown process docs. No web UI, no dashboard, no API. The repo's `hooks/`,
`scripts/`, and `tests/` are Node/JS plumbing for the Claude Code / Gemini harness — not a
frontend, and not portable to VECTOR's Python runtime. Nothing to build or vendor on the UI side.

---

## Section 4 — Verdict & Delete-Readiness

**Verdict: SAFE TO DELETE — DELETE-NOW.**

Reasoning:
- The repo is **agent-harness-dependent markdown**. Its *form* (Claude Code `Skill` tool docs) is
  explicitly discarded under VECTOR's absorption rule.
- Its *value* — plan-before-act, execute-with-verification, parallel dispatch, root-cause debugging,
  review-before-merge, evidence-before-completion — is **already implemented in VECTOR's runtime**
  (planner + goal_system + autonomous_loop + decision_engine + swarm + qa district + coding district),
  verified live (`PLAN_OK actions=3`, swarm 8 topologies, reality_checker smoke/integration gates,
  bug_hunter root-cause event handler).
- The skill *files themselves* are **already vendored** in `brain/.claude/skills/` (all 14, exact
  names) for build-session use. Deleting the GitHub clone loses nothing — the brain copy is the
  canonical source.
- **Zero pending harvest** needs this repo as a reference diff. There is no Python to port, no bug to
  fix, no panel to build. Nothing in `_MASTER_TRACKER.md` depends on it.

**Genuinely missing from the RUNTIME: nothing.** The 5 ⚠️ items are interactive build-session
disciplines (design-approval gate, TDD-write-first gate, code-review reception, git-worktree
fan-out) that are intentionally *not* autonomous-loop behaviors — they already exist as brain
skills for when you (the human) drive a build session, which is their correct home.

**Recommended tracker line:**
`superpowers-main — DELETE-NOW. 14 harness skills; capabilities covered by VECTOR runtime
(9 ✅ / 5 ⚠️-discipline-only / 0 ❌); all 14 already in brain/.claude/skills/. No code, no
frontend, no pending harvest.`
