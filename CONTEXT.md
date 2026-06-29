# VECTOR

Virtual Entity for Cognitive Tasks & Operational Reasoning. A Darwinian multi-agent autonomous personal AI running 24/7 on a local machine (Legion Pro 5, RTX 5070 Ti). VECTOR governs a city of agents that evolve, die, and are reborn. The owner is Arghyadeep Deb.

## Language

**District**:
A specialized folder of agents (`districts/<name>/`) with a single domain responsibility — e.g. `coding/`, `finance/`, `research/`. Districts are VECTOR's org chart.
_Avoid_: module, service, plugin, subsystem

**Agent**:
A Python class (subclass of `AgentBase`) that lives inside a district, holds HP, and performs tasks. Agents are citizens of VECTOR City.
_Avoid_: bot, worker, handler, process

**HP (Health Points)**:
A 0–1000 integer tracking an agent's lifetime performance. Gained by completing tasks well; lost by failure. At 0 HP the agent dies. HP gates model access: >800 = Claude Sonnet, >700 = Council seat, 600–800 = kimi-k2.6.
_Avoid_: score, rating, points, credits

**Governor**:
`core/city/governor.py` — the central router. Routes incoming tasks to the correct district by keyword matching and LLM classification. The single entry point for all agent work.
_Avoid_: router, dispatcher, controller, orchestrator

**Permission Gateway**:
`core/loop/permission_gateway.py` — the ONLY interface between LLM decisions and real-world actions. Enforces GREEN/YELLOW/RED permission levels. LLM proposes; Gateway executes. Nothing bypasses this.
_Avoid_: action layer, executor, runner

**GREEN / YELLOW / RED**:
The three permission tiers. GREEN = execute silently (read_calendar, web_search). YELLOW = execute + notify (commit_code, send_message). RED = stop and wait for explicit human yes (send_email, deploy_production, financial_transaction).
_Avoid_: safe/unsafe, low/high risk, tier-1/tier-2

**Autonomous Loop**:
`core/loop/autonomous_loop.py` — the main coroutine: `observe → think → act → reflect`. Runs forever via `run_forever()`. Every sub-coroutine must catch all exceptions and restart — the loop must never die.
_Avoid_: main loop, event loop, tick, daemon

**Context Engine**:
`core/loop/context_engine.py` — builds the 14-domain world state and generates `session_hydration_prompt()`. Must be called before EVERY LLM call, without exception.
_Avoid_: state manager, world model, prompt builder

**Decision Engine**:
`core/loop/decision_engine.py` — scores 4 action candidates using the formula: goal_alignment(30%) + confidence(25%) + policy(20%) + urgency(15%) + timing(10%) − cost(5%).
_Avoid_: planner, scorer, ranker

**Policy Memory**:
`core/memory/policy.py` — reinforcement learning table. `get_score()` BEFORE every decision; `update_from_outcome()` AFTER every action. Both must be wired.
_Avoid_: reward table, RL memory, feedback store

**Episodic Memory**:
`core/memory/episodic.py` — SQLite FTS5 table storing what happened, when, and with what outcome. The primary memory store.
_Avoid_: log, event store, history

**Ghost Memory**:
The summarized lifetime knowledge of a dead agent, preserved in `agent_history` table and injected into the next generation of the same agent role.
_Avoid_: agent log, death record, backup

**Council**:
The LLM deliberation body invoked for high-stakes decisions. Members: `vector-reasoning + vector-r1 + qwen3:30b-a3b + vector-chairman`. Only agents with HP > 700 vote. Sessions stored as training data.
_Avoid_: committee, panel, board, ensemble

**Vectorcode**:
The communications layer (`vectorcode/src/`) — 30+ platform channel adapters (Telegram, WhatsApp, Discord, Slack, Gmail, etc.), neural routing, swarm coordination, and agent scaffolding. This is the only supported cross-platform messaging implementation.
_Avoid_: comms layer, messaging system (use "vectorcode" specifically)

**District LLM**:
`vectorcode/src/district_llm.py` — unified LLM interface for all district agents. Automatically loads the district's `.md` system prompt and calls `vectorcode_llm.chat()`.
_Avoid_: LLM wrapper, model caller, chat interface

**GNN Router**:
`vectorcode/src/router.py` — 4-layer routing: MoE(L0) → GNN(L1) → keyword(L2) → regex(L3). Routes incoming messages to the correct district agent.
_Avoid_: message router, dispatcher

**MCP Server**:
`core/mcp_server.py` — exposes VECTOR's 28+ tools over Model Context Protocol so Claude Code and Cursor can call VECTOR as a tool server.
_Avoid_: tool server, API server

**Reflect**:
The 2AM nightly process in `core/loop/autonomous_loop.py` that summarizes the day, updates semantic memory, extracts patterns, and prunes old episodic memories.
_Avoid_: nightly job, cron, batch

**Session Hydration**:
The call to `context_engine.session_hydration_prompt()` that must precede every LLM call. Gives the LLM full world state so it never has amnesia.
_Avoid_: context injection, prompt building, state loading

## Relationships

- A **District** contains one or more **Agents**
- The **Governor** routes tasks to **Districts** using keyword + LLM classification
- Every **Agent** action goes through the **Permission Gateway** — no exceptions
- The **Decision Engine** consults **Policy Memory** before and after every action
- The **Context Engine** feeds **Session Hydration** into every **Council** and agent LLM call
- **HP** gates which model an **Agent** can access; at 0 HP the agent dies and **Ghost Memory** is preserved
- The **Council** is only convened when a task's stakes are "high" or "critical"
- **Vectorcode** is the only interface for all cross-platform messaging — the **Governor** routes comms tasks to the `communications` district which uses vectorcode adapters

## Example dialogue

> **Dev:** "Can the agent call the Claude API to draft a reply?"
> **Domain expert:** "No — VECTOR's **Autonomous Loop** uses local Ollama models only at runtime. The **Permission Gateway** would block an outbound API call to Claude. Only build sessions (Claude Code) use the API."

> **Dev:** "Should we add a new comms platform by editing the Governor?"
> **Domain expert:** "No — add a channel adapter under `vectorcode/src/channels/`. The **GNN Router** will discover it. The **Governor** only handles district routing, not platform-specific logic."

## Flagged ambiguities

- "skill" refers to two distinct things: (1) Claude Code slash commands in `~/.claude/skills/`, and (2) the `skills/` district in VECTOR City. Context always clarifies which.
- "memory" without qualification is ambiguous — always specify: episodic_memory, semantic_memory, policy_memory, ghost_memory, or reasoning_chains.
- "agent" in the vectorcode/ruflo layer means a Python class orchestrating LLM calls; in VECTOR City it means an HP-bearing citizen. Both are valid — context clarifies.
