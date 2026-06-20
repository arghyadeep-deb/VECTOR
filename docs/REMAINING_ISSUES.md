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

### 1. DB Backup / Retention ✅ DONE (2026-06-18)
- `scripts/db_backup.py` built: finds all .db files, sqlite3.Connection.backup() online API, 7-day rolling retention
- Wired into `_reflect_tick()` (2AM) via `asyncio.to_thread(run_backup)`
- Usage: `python scripts/db_backup.py [--dry-run | --list | --prune]`

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

### 4. Kokoro TTS ✅ DONE / Wake Word ⚠️ blocked (2026-06-20)
- Kokoro: model weights + `kokoro-onnx` package already present, confirmed loading on GPU — no action needed.
- Wake word: 15 real "Hey VECTOR" samples recorded, but `openwakeword`'s training
  pipeline has since moved to a synthetic-data model (Piper TTS generation +
  background-noise/RIR datasets) that 15 real clips alone can't satisfy.
  Owner decision needed: set up the full synthetic pipeline, downgrade
  `openwakeword` to the version the original simple flow assumed, or skip for now.

### 5. Cloud Deployment — mostly done (2026-06-20)
- Fly.io: **resolved, not deployed by choice** (requires a card) — `cloud/brain_server/`
  removed entirely. The Cloudflare Worker has full endpoint parity, confirmed
  live and working (D1 fully migrated incl. command queue, KV, authenticated
  endpoints tested).
- `wrangler deploy`: ✅ done — Worker live at the configured `*.workers.dev` URL.
- Android Termux `setup.sh`: still pending — needs the physical device.
- **Remaining owner time: just the phone node setup.**

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
