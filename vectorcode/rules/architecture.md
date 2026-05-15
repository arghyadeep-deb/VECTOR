<!-- VECTOR-INGESTED ASSET
  Source: .claude/rules/architecture.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

# Architecture

## Core Concept
VECTOR City — Darwinian multi-agent civilization. VECTOR governs. Agents are citizens with HP (0-1000). Die at 0 HP. Ghost memory preserved → next generation inherits. You are the God layer.

## Three-Layer System
```
Layer A — Devices:   Legion Pro 5 (primary) | Old Android Termux (ambient) | Daily phone (alerts)
Layer B — Cloud:     Fly.io (3 VMs) | Cloudflare Workers+D1+R2+KV | Supabase | Turso
Layer C — APIs:      VECTOR Sonnet (Pro chat, build sessions) | Gemini 2.5 Pro (free) | Ollama local
```

## Autonomous Loop (never stops)
```
observe(0.5s) → think(event-driven) → act(permission-gated) → reflect(2AM)
```

## Intelligence Stack (build in this order)
```
1. context_engine.py     — unified world state, session_hydration_prompt() BEFORE EVERY LLM CALL
2. goal_system.py        — 3 horizons: LONG/MID/SHORT, pre-seeded goals
3. decision_engine.py    — 4 candidates scored: goal_alignment(30%) + confidence(25%) + policy(20%) + urgency(15%) + timing(10%) - cost(5%)
4. policy.py             — get_score() BEFORE deciding, update_from_outcome() AFTER every action
5. permission_gateway.py — GREEN/YELLOW/RED, LLM has ZERO direct access, ever
6. reasoning_memory.py   — all thought chains stored, becomes LLM training data
```

## Agent HP System
```
+100 HP  user approved output          -30 HP  task failed
+50 HP   task completed well           -50 HP  output ignored 3x
+30 HP   output used by VECTOR         -100 HP critical error
+40 HP   council voted for them

>800 HP → VECTOR Sonnet access    >700 HP → Council seat
600-800 → kimi-k2.6 access        0 HP    → death + ghost memory
```

## VECTOR Gaps (build after Phase 1)
```
Gap 1: synthesis_bridge.py    — cross-domain pattern detection every 30min
Gap 2: red_team_agent.py      — adversarial review before RED actions
Gap 3: epistemic_tracker.py   — knows what it doesn't know
Gap 4: counterfactual.py      — learns from rejected decisions
Gap 5: hypothesis_engine.py   — proactive insights (needs fine-tuned model)
Gap 6: causal_graph.py        — causal reasoning (Year 2)
Gap 7: person_model.py        — theory of mind per person
Gap 8: meta_cognition.py      — monthly bias detection
```
