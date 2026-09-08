# Capability Matrix

**Purpose:** What VECTOR can and cannot do
**Level:** System Level (Level 1)

---

## Overview

This matrix documents VECTOR's capabilities, distinguishing implemented vs planned features.

**Key Properties:**
- **Implemented** — fully working
- **Partial** — code exists, needs setup
- **Planned** — not yet built
- **Deferred** — explicitly not building

---

## Core Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Autonomous loop | ✅ Implemented | observe→think→act→reflect, never dies |
| Context engine | ✅ Implemented | 14-domain world state, RULE 1 |
| Decision engine | ✅ Implemented | 5-factor scoring |
| Policy memory | ✅ Implemented | EMA get_score() + update_from_outcome() |
| Reasoning memory | ✅ Implemented | All chains stored |
| Permission gateway | ✅ Implemented | GREEN/YELLOW/RED, Pushover approval |
| Goal system | ✅ Implemented | 3 horizons, 5 pre-seeded goals |
| HP system | ✅ Implemented | 0-1000, death at 0, ghost memory |
| LLM Council | ✅ Implemented | HP >700 gate, 3-stage deliberation |
| Agent registry | ✅ Implemented | Death→ghost→successor |
| Evolution engine | ✅ Implemented | Cross-gen lesson inheritance |

---

## Inference Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| 27 LLM providers | ✅ Implemented | Anthropic, OpenAI, Gemini, Groq, DeepSeek, etc. |
| Ollama local | ✅ Implemented | 10 custom models |
| Model routing | ✅ Implemented | Complexity-based + domain routing |
| Budget tracking | ✅ Implemented | Free-tier quota management |
| Hard whitelist | ✅ Implemented | Paid models never called at runtime |
| Flash Attention | ✅ Implemented | O(N) block-tiled |
| MoE routing | ✅ Implemented | 8-expert gating |
| Neural training | ✅ Implemented | 6 RL algorithms |

---

## Memory Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Episodic memory | ✅ Implemented | SQLite FTS5, WAL, AES-256 |
| Semantic memory | ✅ Implemented | LightRAG, nano-vectordb |
| Policy memory | ✅ Implemented | EMA, alpha=0.1 |
| Reasoning memory | ✅ Implemented | Decision chains |
| Ghost memory | ✅ Implemented | Deceased agent lessons |
| Obsidian sync | ✅ Implemented | Bidirectional |
| Multi-DB mesh | ✅ Implemented | Local + Supabase + Cloudflare |
| Collections engine | ✅ Implemented | Dynamic schema tables |

---

## Communication Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| 30+ platforms | ✅ Implemented | Telegram, WhatsApp, Discord, Slack, Gmail, etc. |
| VectorCode gateway | ✅ Implemented | Unified interface |
| Inbound messaging | ✅ Implemented | Bidirectional |
| Outbound messaging | ✅ Implemented | Bidirectional |
| Bulk sending | ✅ Implemented | Rate-limited |
| WhatsApp Business | ✅ Implemented | Templates, media, reactions |
| OAuth 2.0 | ✅ Implemented | 80+ providers |
| OAuth 1.0a | ✅ Implemented | Twitter, etc. |
| Webhook signing | ✅ Implemented | HMAC-SHA256 |

---

## Tool Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Filesystem tools | ✅ Implemented | read, write, delete, move, copy |
| Shell tools | ✅ Implemented | exec, async, kill |
| Browser tools | ✅ Implemented | navigate, click, type, screenshot, scrape |
| Web tools | ✅ Implemented | search, fetch, download |
| Coding tools | ✅ Implemented | analyze, format, test, git |
| Database tools | ✅ Implemented | query, insert, update, delete |
| Communication tools | ✅ Implemented | send to 30+ platforms |
| System control | ✅ Implemented | PC + phone control |
| Media tools | ✅ Implemented | image, video, audio |
| MCP server | ✅ Implemented | 100+ tools |

---

## Sensing Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Camera | ✅ Implemented | opencv-python |
| Face detection | ✅ Implemented | face-recognition |
| Face recognition | ⚠️ Partial | Code ready, pip install pending |
| Screen capture | ✅ Implemented | mss |
| OCR | ✅ Implemented | pytesseract |
| Sound classification | ✅ Implemented | RMS+ZCR |
| Fatigue monitoring | ✅ Implemented | EAR via mediapipe |
| Wake word | ⚠️ Partial | hey_jarvis placeholder, custom training needed |
| STT | ✅ Implemented | Whisper local |
| TTS | ⚠️ Partial | Kokoro model needs download |
| Voice cloning | ⚠️ Partial | Chatterbox-TTS, needs setup |

---

## Control Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| PC control | ✅ Implemented | pyautogui |
| Phone control | ✅ Implemented | ADB |
| Screenshot (PC) | ✅ Implemented | pyautogui |
| Screenshot (phone) | ✅ Implemented | ADB |
| Tap/swipe (phone) | ✅ Implemented | ADB |
| Type (PC) | ✅ Implemented | pyautogui |
| Type (phone) | ✅ Implemented | ADB |

---

## Security Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Threat detection | ✅ Implemented | Process/registry/network scan |
| Malware detection | ✅ Implemented | VirusTotal + MIME + LightGBM |
| SSRF guard | ✅ Implemented | URL validation |
| Prompt injection | ✅ Implemented | Boundary scanning |
| Permission gating | ✅ Implemented | GREEN/YELLOW/RED |
| Privacy enforcement | ✅ Implemented | Cloud vs local |
| Data flow auditing | ✅ Implemented | Privacy district |
| SQLCipher encryption | ✅ Implemented | AES-256 |

---

## Deployment Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Local service | ✅ Implemented | NSSM Windows service |
| Cloudflare Worker | ✅ Deployed | Live, authenticated |
| Supabase | ✅ Configured | Schema applied |
| Cloudflare D1 | ✅ Deployed | 7 tables |
| Cloudflare KV | ✅ Deployed | Active |
| Cloudflare R2 | ✅ Deployed | Active |
| GitHub Actions CI | ✅ Implemented | Tests on push |
| HUD frontend | ✅ Implemented | 6.3k LOC |

---

## Planned Capabilities (Not Yet Built)

| Capability | Status | Notes |
|------------|--------|-------|
| Counterfactual learning | ❌ Planned | Gap 4 — Year 2 |
| Causal graph | ❌ Planned | Gap 6 — Year 2 |
| Person model (ToM) | ❌ Planned | Gap 7 — Year 2 |
| Meta-cognition | ❌ Planned | Gap 8 — Year 2 |
| OpenMythos custom LLM | ❌ Planned | Month 4-6 |
| Full vector-chairman fine-tune | ❌ Planned | Month 2-3 |
| Next.js dashboard | ❌ Deferred | HUD serves this role |
| Fly.io brain server | ❌ Deferred | Owner declined |

---

## Capability Summary

| Category | Implemented | Partial | Planned |
|----------|-------------|---------|---------|
| Core | 11 | 0 | 0 |
| Inference | 8 | 0 | 0 |
| Memory | 8 | 0 | 0 |
| Communication | 9 | 0 | 0 |
| Tools | 10 | 0 | 0 |
| Sensing | 6 | 4 | 0 |
| Control | 7 | 0 | 0 |
| Security | 8 | 0 | 0 |
| Deployment | 8 | 0 | 0 |
| **Total** | **75** | **4** | **8** |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `34_CAPABILITY_MATRIX.md` — this document
- `35_REACHABILITY_MATRIX.md` — Reachability
- `39_AUTONOMY_ASSESSMENT.md` — Autonomy level

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
