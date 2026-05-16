# 04 — Constraints

## Hardware Constraints

| Constraint | Limit | Design Decision |
|------------|-------|----------------|
| VRAM (RTX 5070 Ti) | 12GB | `OLLAMA_MAX_LOADED_MODELS=1`. vector-focus permanent. All others load on demand. KV cache quantized q8_0. |
| System RAM | 32GB | gemma4:26b and gemma4:31b run hybrid (VRAM + RAM) at 3-6 tok/s. Acceptable for non-real-time only. |
| Storage | 1TB | Models ~75GB. VECTOR data ~10GB. Infrastructure ~5GB. Comfortable headroom. |
| CPU | Core Ultra 9 275HX | Ambient loop on CPU. Whisper on CPU when GPU occupied. OpenCV 1fps on CPU. |
| Old phone | 4-8GB RAM | Runs Qwen 0.5B or Gemma 4 E2B via llama.cpp in Termux. |

## Cost Constraints

| Service | Constraint | Enforcement |
|---------|-----------|-------------|
| Claude API | Pro plan — unlimited chat | Never call Claude API from VECTOR runtime. Build sessions only. |
| VECTOR runtime | ₹0 target | All autonomous decisions use local Ollama models only. |
| LLM Council | Max ₹64/month | Max 10 sessions/week. Weekly counter in policy_memory. |
| kimi-k2.6 + glm-5.1 | Free Ollama tier | Monitor usage. Alert if approaching paid limit. |
| Gemini 2.5 Pro | 1500 req/day free | api_manager.py limits to 1400/day (100 buffer). |
| Total monthly | ₹500 target | Dashboard shows real-time cost. Alert at ₹400. |

## Privacy Constraints — Non-Negotiable

| Data Type | Rule |
|-----------|------|
| 🔴 Voice audio | NEVER leaves device. Whisper local only. No streaming to any API. |
| 🔴 Message content | WhatsApp/Telegram NEVER sent to cloud APIs. Style-matching = local models only. |
| 🔴 Camera data | Face recognition runs locally. No frames uploaded anywhere. |
| 🟡 Personal memories | Cloud DBs store encrypted summaries only. Full episodic DB stays on-device. |
| 🟡 API keys | Windows Credential Manager via keyring. Never in .env, git, or logs. |
| 🟡 Screen content | Gemini Vision sees layout only for PC control. Message text never sent to cloud. |

## Technical Constraints

- Python 3.11+ only
- Windows 11 primary. WSL2 for Hermes Agent only.
- All async code uses `asyncio`. Never `threading`.
- All HTTP calls use `httpx` (async). Never `requests`.
- All logging via `loguru`. Never `print()` in production.
- SQLite FTS5 + SQLCipher AES-256 for all local databases.
- Ollama v0.20.4+ with CUDA. `nvidia-smi` must return RTX 5070 Ti.