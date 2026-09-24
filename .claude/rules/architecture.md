# Architecture

## Core Concept
VECTOR City — Darwinian multi-agent civilization. VECTOR governs. Agents are citizens with HP (0-1000). Die at 0 HP. Ghost memory preserved → next generation inherits. You are the God layer.

## Three-Layer System
```
Layer A — Devices:   Legion Pro 5 (primary) | Old Android Termux (ambient) | Daily phone (alerts)
Layer B — Cloud:     Cloudflare Worker + D1 + KV (api/wrangler.toml; live) | Supabase | Turso   (Fly.io dropped — owner declined the card requirement)
Layer C — APIs:      Claude Sonnet (Pro chat, build sessions) | Gemini 2.5 Pro (free) | Ollama local
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

Born at 500 HP. Awards are damped (repeat-reason decay x headroom); deductions are not.

HP → local model (AgentBase._calculate_model):
>=800 vector-dev | 600-799 vector-r1 | 400-599 vector-focus
200-399 vector-reasoning | 1-199 vector-ambient | 0 → death + ghost memory
>=700 HP → Council eligibility (CONFIG["council"]["hp_gate"])
```

## VECTOR Gaps (all 8 modules exist in the code; live behavior not re-verified here)
```
Gap 1: core/brain/synthesis_bridge.py    — cross-domain pattern detection every 30min
Gap 2: core/brain/red_team_agent.py      — adversarial review before RED actions
Gap 3: core/brain/epistemic_tracker.py   — knows what it doesn't know
Gap 4: core/memory/counterfactual.py     — learns from rejected decisions
Gap 5: core/brain/hypothesis_engine.py   — proactive insights (needs fine-tuned model)
Gap 6: core/memory/causal_graph.py       — causal reasoning (SQLite-backed)
Gap 7: core/brain/person_model.py        — theory of mind per person
Gap 8: core/city/meta_cognition.py       — monthly bias detection
```
