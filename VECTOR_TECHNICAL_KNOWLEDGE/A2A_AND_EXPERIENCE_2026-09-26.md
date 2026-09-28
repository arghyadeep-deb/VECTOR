# Agent-to-agent bus, experience ledger and fair HP (2026-09-26)

Owner brief (2026-09-26): treat each agent as a person. Idle agents are safe; every agent should get work; death rare and meaningful;
all experience carries to successors so they know what to do and what not to do; agent-to-agent (A2A) communication must exist in every
district. Built in four phases, each behind flags where it changes behaviour. Nothing pushed.

## 1. A2A: a governed bus for the real city (`core/city/a2a_bus.py`)

Before: the only internal A2A call was `AgentBase.request_agent_help()` (two callers) and it called `target.run()` directly, around the
Governor and PermissionGateway; the `/a2a/*` HTTP surface reads a different registry (wrapper agents with no behaviour).

Now every agent inherits `a2a_ask / a2a_delegate / a2a_tell / a2a_inbox / a2a_describe`. Delivery is `Governor.dispatch()` (tier gate,
unknown-task-type gate, timeout, HP accounting, events); the bus adds depth (3), cycle detection, a 12-message budget per conversation,
20 requests/minute per sender, an in-flight cap, a payload cap, an injection screen and an audit trail (ring buffer + episodic memory).
Authority is never inherited: the gateway classifies the ACTION, so asking a peer cannot make an action easier. YELLOW/RED types are
answered `requires_approval` (or, with `escalate=True`, become an ordinary PermissionGateway proposal from the untrusted proposer
`a2a_agent`). `ping`/`describe` are answered from the registry, so every agent is reachable for discovery without per-agent code.
`request_agent_help` now goes through the bus (bypass closed). No new tier entries.

Live (backend restarted on the final code): **230/230 agents answered a ping across all 39 districts**; research <-> coding <->
chief_of_staff requests delivered; RED requests refused. `tests/test_a2a_conformance_all_districts.py` bootstraps the real manifest and
fails if any district's agents cannot be reached or a district advertises no capability. New endpoints: `/a2a/internal/directory`,
`/ping-all`, `/recent`, `/conversation/{id}`, `/ask`, `/work-board`, `/agent/{name}`. The HUD Civilization Atlas shows recent bus
messages (refusals included) and, per agent, level/XP/skills/playbook.
Found by running it live: `describe_agent` called `get_status()`, which GitBot overrides to run git and award HP; it now reads HP directly.

## 2. What the recorded history said about death (the replay)

Of 573 real-agent deaths on record, **560 (98%) were agents at 200+ HP** and 548 (96%) happened in the 02:xx hour: the nightly reflect
pass ran `cull_bottom(district, keep_top=5)` for every district and killed the lowest-ranked agents of any district with more than
five, healthy or idle, regardless of performance (94 last night, 62 the night before). Only 13 deaths were at HP < 200 (12 at exactly 0).
That is the opposite of "idle agents are safe; death rare and meaningful". Fixed: `VECTOR_FAIR_CULL` (**default on**) - a candidate must
have HP < 200 AND at least three recorded own-fault failures.

Also found: the HP validator's EMA was one state per agent shared by rewards and penalties, so a -5 after a -30 was deducted as 22.5 and
a -5 after a +50 as 33.5 (via `abs()` in `deduct_points`). Under `VECTOR_HP_FAIR` penalties are no longer smoothed.

## 3. Experience (`core/city/experience.py`) and the flags

Append-only ledger keyed by district+name (successors share it): every Governor outcome (also status-less handlers and dispatches with no
literal capability match), whose fault it was, whether verified. XP is weighted by difficulty, novelty (Nth identical success worth
1/sqrt(1+N)) and verification (x0.3 if unverified). XP never decreases; each death multiplies the lineage's *standing* XP by 0.75 but
nothing is erased. Level = floor(sqrt(standing/25)), max 10. Failures: environment (no key, provider down, timeout, missing module) is
not the agent's fault; the first failure of a kind teaches (+2 XP, cheap HP, a lesson); repeats cost full. Deterministic playbook of
DO / DON'T / NOTE lines per lineage (no LLM).

| Flag | Default | Effect |
|---|---|---|
| (recording) | on | ledger rows for every outcome, death records |
| `VECTOR_FAIR_CULL` | **on** | cull needs HP<200 and 3 own-fault failures (idle agents safe) |
| `VECTOR_HP_FAIR` | off | env failures free; first-of-kind -5 + lesson, repeat -30; probation (3 chances) at 0 HP; model-tier floor by level; penalties unsmoothed |
| `VECTOR_PLAYBOOK` | off | lineage playbook injected into agent prompts (`get_system_prompt`, `vchat`) |
| `VECTOR_LEVEL_COUNCIL` | off | council vote needs level 5 + HP 300 instead of HP 700 (no agent has a level yet) |
| `VECTOR_EXPLORE` (+`_SHARE`, 0.15) | off | a share of GREEN dispatches go to a less-tried capable agent (never YELLOW/RED/UNKNOWN, never non-capable/dead) |
| `VECTOR_GYM` / `VECTOR_GYM_LLM` | off / off | practice drills for idle agents (below); LLM drills additionally opt-in |

## 4. Work board and honest limits (`core/city/work_board.py`)

Practice drill = a real GREEN task with an answer checked independently (the GitBot drills compare against `git` itself). A drill moves
no HP (agent self-awards are restored), earns 0.3x XP, waits while the owner is coding, is capped at 3/day per agent, and runs from the
`agent-gym` cron job (no-op unless `VECTOR_GYM` is on). Collaboration credit: only an answer the asker verifies earns the helper XP
(0.5x, 3/day per pair), so trading requests cannot farm.

**Honest limit: only the GitBot has a drill today (1 of 230 agents).** The 230 agents declare ~715 distinct capabilities and most have no
safe canned test, so "every agent works" cannot be met by drills alone. Real work (goals, plans, the owner, other agents over the bus) is
the main supply; drills fill gaps, and `register_drill()` makes each new one a few lines. `/a2a/internal/work-board` shows the coverage.

## 5. Suggested order to switch things on, and review notes

Let the ledger collect for a few days, then `VECTOR_HP_FAIR`, `VECTOR_PLAYBOOK`, `VECTOR_EXPLORE`; author drills per district before
`VECTOR_GYM`; `VECTOR_LEVEL_COUNCIL` only once agents have levels. For the Codex review: `a2a_bus.py`, the Governor additions (pinned
agent, `_no_reward`, exploration, fault attribution, ledger hooks), the HP validator change, `AgentBase` probation/model floor, and the
fair-cull default. No permission tier was loosened or added by this work.
