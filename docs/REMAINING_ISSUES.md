# VECTOR Remaining Work — 2026-06-18 (updated)

Accurate audit of what genuinely still needs work.

## Already Done (previous assessment was wrong)

| Item | Reality |
|------|---------|
| CI/CD | 5 workflows in `.github/workflows/`: ci.yml, tests.yml, lint.yml, code-health.yml, release.yml |
| Test coverage | 3,839 tests collected (pytest --collect-only). Smoke 38/38, integration 51/51 |
| Circuit breakers | `core/resilience/circuit_breaker.py` exists; DB quarantine via `core/memory/db_guardian.py` |
| Retry with backoff | `provider_client.py:_call_with_retry()` — exponential backoff, respects Retry-After header |
| Model fallback | `model_pool.py` — 27 logical aliases, provider cooldown, auto-fallback across 8+ providers |
| Health endpoint | `/health`, `/health/system`, `/metrics` endpoints in API |
| DB encryption | SQLCipher AES-256 on primary `vector_memory.db` |
| Graceful degradation | Fallback chains: Ollama → cloud → cached. Every coroutine has try/except. |

## Q0 — Genuine Gaps

### 1. DB Backup / Retention
- 16+ SQLite databases, no backup rotation script
- `scripts/db_backup.py` needed: daily backup, 7-day rolling window
- **~2 hrs**

### 2. Frontend Polish (7 items, parallelizable)
- JS build pipeline (21 loose files, no bundler)
- ARIA/keyboard accessibility gaps
- Service worker for offline HUD
- Config UI (no way to set provider keys from HUD)
- Clean dev/prod split for HUD
- **3-4 days** in parallel

### 3. Agent Lifecycle — HP Death/Rebirth
- HP system exists in `core/city/agent_base.py`
- Death → ghost memory → successor agent birth loop not fully wired
- No RL policy training loop running
- ContextEngine output not piped to agents at decision time
- **3-5 days** (needs design first)

### 4. Kokoro TTS / Wake Word (owner action required)
- `pip install kokoro` + model weights (~300MB)
- Record 10 "Hey VECTOR" samples → openWakeWord training
- **~2 hrs owner time**

### 5. Cloud Deployment (owner action required)
- `fly launch && fly deploy` in `cloud/brain_server/`
- `wrangler deploy` in `api/`
- Android Termux `setup.sh`
- **~2 hrs owner time**

---

## Honest Assessment (corrected)

| Dimension | Current |
|-----------|---------|
| Security | 85/100 |
| Code Quality | 80/100 |
| Feature Completeness | 70/100 |
| Test Coverage | ~3,839 tests, good core coverage |
| Production Readiness | 75/100 |
| JARVIS Closeness | 70% |

**Total code work remaining: ~1 week.** Agent lifecycle is the biggest gap.
Owner actions (Kokoro, cloud deploy) are 2-4 hrs combined.
