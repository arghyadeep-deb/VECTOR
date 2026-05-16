# 08 — Key Design Decisions

## Why Hermes Instead of Building Comms from Scratch

`ollama launch hermes --model kimi-k2.6:cloud` provides:
- Multi-platform messaging (WhatsApp, Telegram, Discord, Signal, Email)
- Self-improving skill creation from successful interactions
- Persistent memory across sessions
- Style learning from interaction history

Rebuilding = ~6 hours, lower quality. Engineering rule: never build what already exists well.

## Why OpenMythos Over Plain nanoGPT

OpenMythos RDT achieves 770M param quality equivalent to 1.3B standard transformer.
Each recurrent loop = one chain-of-thought step in latent space.
Better reasoning per parameter = better Chairman LLM.

> **VERIFY FIRST:** Check that `train.py` exists and runs in the OpenMythos repo before committing Month 2 to it. If missing → fallback is karpathy/nanoGPT + LoRA on Colab. Proven, no risk.

## Why Local Models for VECTOR Runtime

- **Privacy:** voice audio never leaves device
- **Cost:** ₹0 for all runtime decisions
- **Latency:** no network round-trip
- **Reliability:** no API downtime affects VECTOR

Claude API = Arghyadeep's build sessions only (unlimited under Pro plan).

## Why Darwinian HP vs Static Agents

Static agents don't improve. An agent with 100 generations of ghost memory is qualitatively different from one starting fresh. Selection pressure (death at 0 HP) creates genuine improvement over time. No other personal AI project has this. It's architecturally sound and genuinely novel.

## Why 8 Districts in Phase 1 Instead of 20

Reviewer confirmed: 20 districts in 50 days = 20 districts at 40% completion. 8 districts fully working is better than 20 districts half-working. Phase 1 = Mayor's Office, Security, Coding, Time/Calendar, Communications, Memory Curator, Research, Intelligence.

## Why One Model at a Time (OLLAMA_MAX_LOADED_MODELS=1)

12GB VRAM + KV cache overhead at 32K context + activations = OOM if two models load simultaneously. vector-focus is the permanent resident. All others load on demand. Swap time = ~5 seconds. Acceptable.

## Why Permission Gateway is Non-Negotiable

Without it: one hallucinated decision can delete files, send wrong emails, push broken code. With it: LLM proposes, gateway validates, audit log captures everything. The gateway is the difference between an autonomous system and an autonomous system you can trust.