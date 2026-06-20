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

### 2. Frontend Polish — ✅ ALL 5 RESOLVED (2026-06-20)
- ✅ Service worker for offline HUD — `offline.js`/`sw.js` were complete and
  correct but never loaded by `VECTOR.prod.html` (no `<script>` tag). Fixed;
  verified end-to-end (HTML serves the tag, both files reachable, 200).
- ✅ Clean dev/prod split for HUD — was already done. `_is_production_env()`
  switches `VECTOR.html`/`VECTOR.prod.html` and blocks `js/demo.js` in prod.
- ✅ JS build pipeline — `tools/build_frontend.py` + `frontend/dist/` already
  existed (deterministic concatenation in production script order, no
  external bundler dependency) but `VECTOR.prod.html` never actually
  referenced the built bundle — it still loaded 20 individual `<script>`
  tags. Wired the HTML to load `dist/vector-hud.prod.js`, rebuilt, added a
  permanent staleness guard (`tests/test_frontend_bundle.py`) so this can't
  silently rot again. Verified live (HTML serves 2 script tags now, bundle
  reachable, contains all current code).
- ✅ Config UI for provider keys — added `GET/POST/DELETE /keys/providers`
  (`core/api/routers/keys.py`), allowlisted to 30 known third-party providers
  only (never VECTOR's own secrets), localhost + current-key-required to
  mutate, newline-injection guarded. New self-contained HUD panel
  (`frontend/js/provider-keys.js`). 12 new tests; verified live end-to-end
  (set → status → clear round-trip, all security guardrails).
- ✅ ARIA/keyboard accessibility — full pass across every interactive surface
  in the HUD: `widgets.js`'s `shell()` (fixes all ~30 panels at once — real
  `role="dialog"` + labelled close button + Escape-to-close + focus
  management on open/close), `terminal.js`, `city3d.js`, `command-box.js`
  (`aria-live` status region), `orb.js` (primary wake control now also
  independently focusable/keyboard-operable), `demo.js` (dev-only debug
  panel). `hud-controls.js`/`approvals.js`/`backend.js` were already correct
  (real `<button>`s with visible text or existing `aria-label`).

### 3. Agent Lifecycle — HP Death/Rebirth — ✅ ALL 3 RESOLVED (2026-06-20)
- ✅ Death → ghost memory → successor agent birth loop — **was genuinely
  broken**: `agent_registry.deregister()` had the complete ghost+successor
  logic already built, but nothing in the codebase ever called it. Wired
  `AgentBase.die()` to call it. Verified end-to-end live: killed a registered
  agent, confirmed gen2 successor spawned with inherited ghost, population
  count unchanged.
- ✅ RL policy training loop — **was already working**, doc was stale.
  `DecisionEngine.record_outcome()` runs real online training
  (`trainer.train_episode()`) with periodic checkpointing after every action.
- ✅ ContextEngine output piped to agents at decision time — `evaluate()`
  now injects a full `ContextEngine().get_world_state()` snapshot onto every
  `Candidate` before scoring (mirrors the existing RULE 8 reasoning-bank
  injection pattern exactly). Deliberately does NOT change the score formula
  itself — that's a product decision (e.g. "should a tired/absent owner
  change which action wins, and how") that needs its own sign-off, not
  something to improvise silently inside a bug-fix pass. 3 new tests.

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
