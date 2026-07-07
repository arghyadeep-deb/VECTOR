---
name: vector-domain-reference
description: Load when you need the domain THEORY behind VECTOR that a mid-level engineer lacks — the Darwinian agent economy (HP, ghost memory, evolution), the cognitive loop, the multi-agent council/swarm, and how they interact. Not a textbook; the field's concepts as they apply HERE. Triggers: "how does the HP system work", "agent economy", "ghost memory", "council", "swarm", "what is the theory", "Darwinian", "decision engine scoring".
---

# VECTOR Domain Reference

The conceptual knowledge pack behind VECTOR — autonomous multi-agent systems as
this project implements them. Read this before reasoning about agent lifecycle,
routing, or the cognitive loop. Ground truth 2026-07-07.

## When NOT to use this skill
For the concrete design decisions/invariants use `vector-architecture-contract`;
for LLM routing internals use `vector-inference-routing`.

## 1. The Darwinian agent economy (the organizing metaphor)
Agents are "citizens" with HP (0–1000). HP is EARNED and LOST by real outcomes,
not faked (`core/city/agent_base.py`, HP validator clamps + EMA-smooths):
- +100 user-approved output; +50 task done well; +30 output used; +40 council vote.
- −30 task failed; −50 ignored 3×; −100 critical error.
- Capability gates by HP: >800 → best models; >700 → council seat; 0 → death.
On death, the agent's learned lessons persist as **ghost memory**, inherited by the
next-generation successor (`agent_registry` death→ghost→successor;
`evolution_engine` cross-gen lesson inheritance, `cull_bottom()`). The POINT:
selection pressure makes useful agents durable and useless ones extinct — the
system gets better without hand-tuning each agent. (This is VECTOR's answer to
"why not just static agents" — see `brain` decision 002.)

## 2. The cognitive loop (how VECTOR thinks)
`observe(0.5s) → think(event-driven) → act(permission-gated) → reflect(2AM)`
(`core/loop/autonomous_loop.py`). Each stage:
- **observe** — senses (screen, camera, sound, system) build world state; every
  coroutine catches-all + backs off so the loop never dies.
- **think** — `context_engine.session_hydration_prompt()` assembles 14-domain world
  state BEFORE every LLM call (RULE 1); `decision_engine` scores 4 candidates:
  goal_alignment(30%)+confidence(25%)+policy(20%)+urgency(15%)+timing(10%)−cost(5%).
- **act** — `permission_gateway` GREEN/YELLOW/RED; the LLM never acts directly.
- **reflect** — 2AM consolidation; `policy_memory` updates from outcomes (RL reward);
  `reasoning_memory` stores chains (reward>0.7 → training data).

## 3. Memory model (3 substrates)
- **Episodic** (SQLCipher FTS5) — events, searchable.
- **Semantic** — consolidated knowledge.
- **Policy** (RL reward, EMA) — what actions worked → biases future decisions.
- **Reasoning chains** — thought traces, become training data.
- **Ghost/agent_history** — cross-generation inheritance.
Sacred: never rename these tables (`vector-change-control`).

## 4. Multi-agent coordination
- **Governor** routes tasks to districts/agents (keyword table + LLM classify
  fallback; HP-aware).
- **LLM Council** — high-stakes decisions; only >700 HP agents vote;
  3-stage deliberation; local models (₹0). Sessions → training data.
- **Swarm** (`vectorcode/src/swarm.py`) — 8 topologies (Byzantine, Raft, Gossip,
  CRDT, Quorum…) for parallel multi-agent work.

## 5. Why cloud-primary + local-terminal (the theory)
Best model per task (cloud free tiers) with a guaranteed local fallback = quality
without a single point of failure. Every routing chain ends on Ollama, so VECTOR
degrades but never crashes. Sensitive prompts never leave the machine. See
`vector-inference-routing`.

## Key terms (defined once)
- **Ghost memory** — lessons an agent leaves on death for its successor.
- **Session hydration** — assembling full world state into the prompt before any
  LLM call (VECTOR's RULE 1).
- **Sensitivity gate** — the check that forces local-only inference for
  secret/security/RED content.
- **Domain chain** — an ordered per-work-domain list of (provider, model) ending on ollama.

## Provenance and maintenance
2026-07-07. Sources: `.claude/rules/architecture.md`, `core/city/*`,
`core/loop/*`, `core/memory/*`. Re-verify HP rules:
`grep -n "HP" .claude/rules/architecture.md`. Decision rationale in
`brain/VECTOR/Decisions/`.
