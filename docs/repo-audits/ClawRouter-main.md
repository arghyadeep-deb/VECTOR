# ClawRouter-main Audit

**Repo:** ClawRouter — LLM router for autonomous agents (MIT)
**Audited:** 2026-06-02

---

## 1. Repo Reality

ClawRouter is an npm tool (`npx @blockrun/clawrouter`) that runs a local OpenAI-compatible proxy server at `http://localhost:8787`. It exposes 10+ free NVIDIA-hosted models (Llama-3.1-70B, Mixtral-8x7B, Qwen2.5-72B, etc.) via the OpenAI chat completions API — no API key required. Also proxies 55+ paid models from various providers. Primary value: zero-cost 70B-class inference as a fallback when Ollama is unavailable or slow.

**Features:**
- OpenAI-compat API at port 8787
- 10 free NVIDIA models (no key)
- 55+ paid models (needs provider keys)
- `npx @blockrun/clawrouter` — zero install

---

## 2. VECTOR Parity

| Feature | VECTOR equivalent | Verified output | Status |
|---------|------------------|-----------------|--------|
| 27-provider LLM routing | `core/inference/provider_client.py` | ProviderClient OK | ✅ |
| Free local models | Ollama (permanent) | 15+ models installed | ✅ |
| 70B free cloud fallback | ❌ No zero-key 70B fallback | N/A | ❌ Missing |
| OpenAI-compat proxy | Not needed — provider_client handles routing | N/A | N/A |

---

## 3. Frontend: N/A

---

## 4. Verdict

**PATCH CONFIG** — Add ClawRouter as a fallback provider entry in `core/config.py`. Run via `npx @blockrun/clawrouter` on port 8787 as an optional sidecar. No code changes needed beyond one config entry. VECTOR's `provider_client.py` already handles OpenAI-compat endpoints.

**Delete-readiness:** DELETE-NOW clone — use `npx`, no local code needed.

---

## 5. Gaps

| ID | Issue | File:line | Severity |
|----|-------|-----------|----------|
| G1 | ClawRouter not in `core/config.py` as a provider — 10 free NVIDIA models unavailable when Ollama busy | `core/config.py` | LOW |
