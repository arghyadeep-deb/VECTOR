# VECTOR Remaining Work — 2026-06-20 (updated)

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

### 2. Frontend Polish — 2 of 5 resolved (2026-06-20)
- ✅ Service worker for offline HUD — `offline.js`/`sw.js` were complete and
  correct but never loaded by `VECTOR.prod.html` (no `<script>` tag). Fixed;
  verified end-to-end (HTML serves the tag, both files reachable, 200).
- ✅ Clean dev/prod split for HUD — was already done. `_is_production_env()`
  switches `VECTOR.html`/`VECTOR.prod.html` and blocks `js/demo.js` in prod.
- ❌ JS build pipeline — still genuinely missing (22 loose files, no bundler
  config anywhere). Real gap, multi-day undertaking.
- ❌ ARIA/keyboard accessibility — still genuinely missing (zero ARIA/tabindex
  attributes anywhere in the HUD). Real gap; needs a careful, design-aware
  pass — rushing this can make screen-reader UX worse, not better.
- ❌ Config UI for provider keys — still genuinely missing. `/keys/rotate`
  only handles VECTOR's own internal `VECTOR_API_KEY`; there is no endpoint
  or UI for third-party provider keys (Anthropic, OpenAI, etc.). Real gap —
  also security-sensitive (arbitrary env-var writes need careful validation),
  should go through the brainstorming gate as a real feature, not a patch.
- **Remaining: ~2-3 days** (bundler + ARIA + provider-key config UI)

### 3. Agent Lifecycle — HP Death/Rebirth — 1 of 3 resolved (2026-06-20)
- ✅ Death → ghost memory → successor agent birth loop — **was genuinely
  broken**: `agent_registry.deregister()` had the complete ghost+successor
  logic already built, but nothing in the codebase ever called it. Wired
  `AgentBase.die()` to call it. Verified end-to-end live: killed a registered
  agent, confirmed gen2 successor spawned with inherited ghost, population
  count unchanged.
- ✅ RL policy training loop — **was already working**, doc was stale.
  `DecisionEngine.record_outcome()` runs real online training
  (`trainer.train_episode()`) with periodic checkpointing after every action.
- ❌ ContextEngine output not piped to agents at decision time — still
  genuinely true. `DecisionEngine.evaluate()` never references ContextEngine
  or session hydration — candidate *scoring* is context-blind, even though
  agents separately hydrate their own LLM calls during execution. Real gap,
  but it's a design addition (what should scoring actually use from world
  state, and how), not a one-line wire-up — needs its own design pass.
- **Remaining: needs design first** (ContextEngine → candidate scoring)

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

## Honest Assessment (corrected 2026-06-20)

| Dimension | Current |
|-----------|---------|
| Security | 85/100 |
| Code Quality | 80/100 |
| Feature Completeness | 75/100 — Darwinian death/rebirth now genuinely fires (was completely dead code before today) |
| Test Coverage | ~3,839 tests, good core coverage, full suite re-verified clean after today's fixes |
| Production Readiness | 78/100 |
| JARVIS Closeness | 75% |

**Total code work remaining: ~3-4 days** (down from ~1 week) — JS bundler,
ARIA accessibility, and provider-key config UI in frontend polish; the
ContextEngine→decision-scoring design in agent lifecycle. Both genuine
death/rebirth wiring and the HUD offline service worker — the two biggest
"looks done but isn't actually connected" bugs — are fixed and verified.
Owner actions remaining: phone Termux node setup, wake word training decision.
