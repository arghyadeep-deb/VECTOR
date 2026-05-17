# Claude API is never called during VECTOR's autonomous runtime

All autonomous operation uses local Ollama models only. The Claude API (Pro plan) is used exclusively for build sessions via Claude Code — never in the hot path. The ONE exception is the 2AM reflect, which calls Claude Opus once per night, non-interactively. Any feature needing an LLM at runtime must use `core/inference/ollama_safe.py`, not the Anthropic client.

**Why**: Cost (₹0 local vs ₹10,000+/month API for 24/7), latency (0.3–1s local vs 1–5s API), privacy (sensor data never leaves device), and reliability (no API outage can kill the loop).
