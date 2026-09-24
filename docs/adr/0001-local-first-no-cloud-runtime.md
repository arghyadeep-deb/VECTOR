# Claude API is never called during VECTOR's autonomous runtime

> **Note added 2026-09-25 (docs-vs-code audit) — partly out of date, needs a superseding ADR from the owner.** The code no longer runs "local Ollama only": `core/inference/route_policy.py` keeps security/privacy/RED-tier/secret-bearing work local-only but sends other work to pooled free cloud keys with Ollama as the fallback (owner decision 2026-07-08: free-tier only, no paid Anthropic/OpenAI keys at runtime). The "Claude API never called at runtime" part still holds in practice (no paid key configured). The "2AM reflect calls Claude Opus once per night" exception was not verified against the code.

All autonomous operation uses local Ollama models only. The Claude API (Pro plan) is used exclusively for build sessions via Claude Code — never in the hot path. The ONE exception is the 2AM reflect, which calls Claude Opus once per night, non-interactively. Any feature needing an LLM at runtime must use `core/inference/ollama_safe.py`, not the Anthropic client.

**Why**: Cost (₹0 local vs ₹10,000+/month API for 24/7), latency (0.3–1s local vs 1–5s API), privacy (sensor data never leaves device), and reliability (no API outage can kill the loop).
