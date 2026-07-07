---
name: vector-architecture-contract
description: Load when you need to understand WHY VECTOR is built the way it is before changing it — the load-bearing design decisions, the invariants that must hold, and the known weak points. Triggers: "how does VECTOR work", "why is it designed", "architecture", "invariant", "is this safe to change structurally", "what am I allowed to break".
---

# VECTOR Architecture Contract

The load-bearing decisions and invariants. If you're about to change something
structural, check it against this first. Ground truth 2026-07-07.

## When NOT to use this skill
For the rules you must follow use `vector-change-control`; for debugging a
break use `vector-debugging-playbook`; for the LLM routing internals use
`vector-inference-routing`.

## What VECTOR is
A local-first, single-owner autonomous agent system ("Darwinian multi-agent
civilization"): ~1.5M LOC, 38 districts, 133 agents. VECTOR governs; agents are
citizens with HP (0–1000), die at 0, leave ghost memory the next generation
inherits. The owner is the "God layer". Autonomous loop:
observe(0.5s) → think(event-driven) → act(permission-gated) → reflect(2AM).

## Load-bearing decisions (change only with deep care)

1. **Cloud-PRIMARY LLM routing, Ollama terminal fallback** (owner policy
   2026-07-02). All LLM calls go through `core/inference/provider_client.py`,
   which routes across 13 free-tier providers (`model_catalog.yaml`) and falls
   back to Ollama. Owner has NO paid OpenAI/Anthropic keys — free tiers only.
   `route_policy.decide_route()` orders providers; sensitivity gate forces
   local-only for security/privacy/RED/secret-looking prompts (non-negotiable).

2. **`OLLAMA_MAX_LOADED_MODELS=1`** — only one local model in VRAM at a time
   (RTX 5070 Ti, 12GB). Never assume two Ollama models load simultaneously;
   switching models evicts the resident one. This is why classifiers use the
   resident `vector-focus`, not `vector-ambient` (which would thrash).

3. **The 5 sacred memory tables** (episodic/semantic/policy/reasoning_chains/
   agent_history) — never rename/drop. Main DB is SQLCipher-encrypted; access
   only via `core.memory.episodic.get_db_connection()`.

4. **Permission gateway is the ONLY path to real-world actions**
   (`core/loop/permission_gateway.py`): GREEN (auto), YELLOW (owner-confirm),
   RED (owner-approval-always via Pushover), FORBIDDEN (blocked). The LLM has
   ZERO direct access. The trust ladder (`core/loop/trust_ladder.py`) promotes
   YELLOW actions to auto after N approvals — but RED/FORBIDDEN never promote.

5. **Multi-DB cloud sync** (`core/memory/multi_db_manager.py`): local SQLite
   (source) → Supabase + Turso + Cloudflare D1 (via Worker). Confirmed live
   4/4 healthy 2026-07-02. Cloud is durable source of truth; local can forget
   bulk data after sync.

6. **Domain routing for district agents** (`vectorcode_llm.chat(domain=...)`):
   each work domain (coding.review, content.script, research, etc.) is a 3–4
   model cloud chain + ollama terminal, so agents get the best model per task
   and never crash (chain always ends on ollama).

## Invariants (must hold)
- Every autonomous-loop coroutine catches all exceptions and backs off — the
  loop must NEVER die (`.claude/rules/code_style.md`).
- Fallback chains everywhere: Claude/cloud → Ollama → cached → notify owner;
  Kokoro TTS → pyttsx3 → text; Whisper → text input; Supabase → Turso → SQLite.
- No hardcoded paths/keys in business logic — all in `core/config.py` CONFIG.
- Locked providers (opencode_zen, zai) NEVER emit a paid model (whitelist clamp).

## Known weak points (stated plainly)
- NOT running as a service yet — the whole thing is powered off (biggest gap).
- Wake word: pipeline works but recall on owner's real voice is ~13%
  (synthetic-voice → real-voice transfer gap); needs owner recordings.
- Voice command coverage < HUD coverage (LLM intent gate added, but not full).
- Some absorbed OSS (9 Hands) wired but not proactive.
- Windows-specific fragility (cp1252, ACL locks, path-with-spaces breaks workerd CI).

## Provenance and maintenance
Dated 2026-07-07 from `.claude/rules/architecture.md`, project memory, and
lived work. Re-verify: `python -c "from core.config import CONFIG; print(CONFIG['cf_worker_url'])"`,
cloud health via `python core/memory/multi_db_manager.py`.
