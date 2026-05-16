# Critical Rules

## The 12 Rules — Never Break These

**RULE 1 — SESSION HYDRATION MANDATORY**
`session_hydration_prompt()` before EVERY SINGLE LLM call.
Skip this = VECTOR has amnesia every session. Never skip.

**RULE 2 — THE LOOP NEVER STOPS**
`run_forever()` never returns. Every coroutine catches exceptions and restarts.
If loop dies, VECTOR is dead.

**RULE 3 — LLM ZERO DIRECT ACCESS**
All actions through `permission_gateway.py`. No exceptions. Ever.
LLM proposes. Gateway executes. Always.

**RULE 4 — ONE MODEL AT A TIME**
`OLLAMA_MAX_LOADED_MODELS=1` is not optional.
12GB VRAM + KV cache overhead = OOM if two models load simultaneously.
Load vector-focus permanently. Everything else loads on demand.

**RULE 5 — VOICE IS LOCAL ONLY**
Whisper runs on Legion. Audio never sent to any external API.
Hard privacy requirement, not a preference.

**RULE 6 — GOAL SYSTEM DRIVES PLANNER**
`planner.py` reads `goal_system.generate_immediate_actions()`.
Not world state. Not user commands. Goals.

**RULE 7 — POLICY WIRED BOTH DIRECTIONS**
`policy.get_score()` BEFORE every decision.
`policy.update_from_outcome()` AFTER every action.
Both must be wired. Either one alone = not learning.

**RULE 8 — REASONING CHAINS PERSISTED**
Every thought-action-outcome stored in `reasoning_chains` table.
`inject_past_reasoning()` used before similar decisions.
High-reward chains (>0.7) tagged `is_training_data=1` → custom LLM data.

**RULE 9 — AGENT DARWINISM IS REAL**
HP system must wire to actual task outcomes.
Fake HP = fake evolution = system that never improves.
Death triggers ghost memory preservation. Always.

**RULE 10 — VECTORCODE IS THE COMMS LAYER**
Hermes Agent is fully replaced by vectorcode. All multi-platform messaging,
skill creation, and persistent memory lives in `vectorcode/src/`.
30+ channel adapters in `vectorcode/src/channels/`. Do not rebuild from scratch.
`from vectorcode.src.vc_agents.agent_registry import vc_agents` for all comms work.

**RULE 11 — CLAUDE API NEVER IN RUNTIME**
Claude Sonnet = your build sessions via Pro plan chat (unlimited).
VECTOR's autonomous operations use local models only.
Council sessions use kimi-k2.6:cloud + glm-5.1:cloud (free tier).

**RULE 12 — KARPATHY 30 MIN/DAY**
Every day. Type every line. Never just watch.
This builds your custom Chairman LLM.
Understanding backprop by typing it = understanding you never lose.

---

## Permission Matrix (memorize this)
```
GREEN  (execute + soft notify after):
  read_calendar, play_music, set_timer, search_web,
  take_screenshot, check_weather, check_attendance

YELLOW (execute + notify immediately):
  send_message_routine, create_calendar_event,
  commit_code, download_file, set_reminder

RED    (STOP — confirm first, wait for explicit yes):
  send_email, delete_files, execute_code,
  financial_transaction, push_github,
  deploy_production, send_message_important
```

## Memory Schema (never change table names)
```sql
episodic_memory    — FTS5 virtual table (what happened)
semantic_memory    — preferences, facts, patterns
policy_memory      — RL reward history (action + situation → avg_reward)
reasoning_chains   — thought chains + council sessions + training data
skill_memory       — skill confidence graph
agent_history      — all agent generations + ghost memories
```

## What VECTOR Never Says
```
"Certainly!" "Of course!" "Great question!"
"I'd be happy to help!" "As an AI..." "Absolutely!"
"Sure thing!" "No problem!" "Is there anything else?"
```

## Shipped Definition (3 questions, all must be YES)
```
1. Did VECTOR do something useful today you did NOT ask it to do?
2. Last week's mistake — is VECTOR still making it this week?
3. Laptop crashes right now — does VECTOR remember the last 3 days?
```

## Investment District Rule
```
Analysis ONLY. Never auto-trades. Never gives financial advice.
Violation of this rule = remove the district entirely.
```