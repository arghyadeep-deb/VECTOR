# Domain Docs

How engineering skills should consume VECTOR's domain documentation.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root — VECTOR's domain glossary (District, Agent, HP, Governor, Permission Gateway, Vectorcode, etc.)
- **`docs/adr/`** — VECTOR's 6 architectural decision records. Always check before proposing architectural changes.
- **`brain/VECTOR/Architecture.md`** — detailed autonomous loop, coroutines, memory schema, voice pipeline, council, deployment
- **`brain/VECTOR/README.md`** — full 20-district overview and critical rules summary

## File structure

Single-context repo:

```
/
├── CONTEXT.md                    ← domain glossary
├── docs/
│   ├── adr/                      ← 6 architectural decisions
│   │   ├── 0001-local-first-no-cloud-runtime.md
│   │   ├── 0002-darwinian-hp-over-static-agents.md
│   │   ├── 0003-permission-gateway-only-action-interface.md
│   │   ├── 0004-vectorcode-replaces-hermes-as-comms-layer.md
│   │   ├── 0005-one-ollama-model-at-a-time.md
│   │   └── 0006-sqlite-not-postgres-for-local-runtime.md
│   └── agents/                   ← skill configuration (this folder)
├── core/                         ← intelligence stack (loop, memory, inference, city)
├── districts/             ← 45+ specialized districts
├── vectorcode/src/               ← comms layer (30+ channels, neural, swarm)
└── cloud/                        ← Cloudflare Workers + Fly.io deployment
```

## Use the glossary's vocabulary

When naming issues, tests, refactor proposals, or hypotheses — use CONTEXT.md terms exactly.

- Say **District**, not "module" or "service"
- Say **Agent**, not "bot" or "worker"
- Say **HP**, not "score" or "rating"
- Say **Permission Gateway**, not "action layer"
- Say **Ghost Memory**, not "agent log" or "backup"
- Say **Vectorcode**, not "Hermes" or "comms layer"

## Critical rules that constrain architecture proposals

Before proposing any change, check against the 12 critical rules in `CLAUDE.md`. The non-negotiable ones:

- **RULE 1**: `session_hydration_prompt()` before every LLM call
- **RULE 2**: The loop never stops — every coroutine catches exceptions and restarts
- **RULE 3**: All actions through `permission_gateway.py` — zero exceptions
- **RULE 4**: `OLLAMA_MAX_LOADED_MODELS=1` — one model at a time
- **RULE 11**: Claude API never called at VECTOR runtime

## Flag ADR conflicts

If a proposal contradicts an existing ADR, surface it explicitly:

> _Contradicts ADR-0003 (permission gateway is the only action interface) — worth reopening because…_
