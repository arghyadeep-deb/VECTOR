# Phase Status — VECTOR Implementation Tracker
> Last updated: 2026-06-11 — see `HANDOFF_TODO.md` DONE sections + `plans/` for current work; this file is the historical tracker
> Status key: ✅ Done · ⚠️ Code done, needs deploy/install · ❌ Not built

## Corrections — Session 2026-06-11 ✅

| Item | Truth |
|------|-------|
| Gaps 4/6/7/8 "Year 2, not built" (below) | **STALE — all four exist**: `core/memory/counterfactual.py` (Gap 4), `core/memory/causal_graph.py` (Gap 6, SQLite-backed since 2026-05-30), `core/brain/person_model.py` (Gap 7), `core/city/meta_cognition.py` (Gap 8) |
| "Next.js Dashboard ❌ not built" | Superseded by `frontend/` HUD (6.3k LOC, served at `/hud/`, vendored three.js/MediaPipe); dashboard `.tsx` tests skip when `dashboard/src` absent |
| Loop mode agent bootstrap | `run_loop()` now calls `bootstrap_agents()` (was: empty registry, every dispatch → no_agents); smoke reports `agents_registered` and fails on 0 |
| SQLCipher access discipline | Main DB is encrypted; 5 modules were opening it with plain sqlite3 (memory_persona, avatar_state, emergency log, DBCorruptionPlaybook, `_is_connection_closed` driver mismatch) — all fixed; rule: go through `core.memory.episodic.get_db_connection()` / `close_db_connection()` |

## Corrections — Session 2026-06-20 ✅

| Item | Truth |
|------|-------|
| "Fly.io brain server... ❌ Run: `fly launch`" (below) | **RESOLVED, not a gap** — Fly.io requires a card; owner declined. `cloud/brain_server/` removed entirely. The Cloudflare Worker (`api/src/router.ts`) has full endpoint parity (`/status`, `/health`, `/heartbeat`, `/command`+queue via D1, `/memory/recent`, `/agents`, `/goals`) and is confirmed live with real authenticated requests. |
| "Cloudflare Worker API... ❌ Run: wrangler deploy" / "Cloudflare D1/R2/KV... ❌ Provision" (below) | **STALE — already deployed.** Worker live, D1 fully migrated (7 tables incl. `command_queue`), KV active. |
| "Kokoro model not downloaded" (Day 3, below) | **STALE — already working.** Model files + `kokoro-onnx` package present; confirmed loading on GPU (`kokoro-v1.0.fp16-gpu.onnx`). |
| "face_recognition pip install pending" (Day 4, below) | **STALE — already installed and working** (`dlib`/`face_recognition` import cleanly; CPU-only by design, no CUDA wheel exists for dlib). |
| HumanLayer removed | Replaced entirely with Pushover (owner-phone approval) for RED-tier actions, 2026-06-19. All doctor/test/code references to HumanLayer removed. |
| `sre_monitor.py` chaos probe was silently broken | Called `DecisionEngine.decide()` — method doesn't exist (real name: `.evaluate()`). Fixed; chaos probe now genuinely runs. |
| `devops_automator.py` had a live false-alarm bug | `all_ok = fly.ok and cf.ok` always failed (Fly never deployed) even when Cloudflare was perfectly healthy, deducting agent HP every run. Fly check removed; now correctly reports Cloudflare-only status. |
| Multi-DB mesh + quarantine + remote command relay (Phase 1-5 of an earlier internal plan) | **All 5 phases already built and tested** — `core/memory/multi_db_manager.py` (`sync_all()`, quarantine), `core/mcp_tools/db_control.py`, `frontend/js/command-box.js`. Discovered already-complete, not started fresh. |
| torch was CPU-only despite RTX 5070 Ti | Reinstalled torch+torchvision+torchaudio with CUDA (cu128) — full suite verified zero regressions. ComfyUI, Whisper STT now genuinely GPU-resident (Whisper was silently running on CPU before, no error, just slow). |
| starlette stuck on old `0.52.1` despite `==1.0.0` pin in requirements.txt | Installed the pinned version; verified FastAPI app + `chatterbox-tts` (which pulls in `gradio`, unused directly) both still work. |

## Production Hardening — Session 2026-05-29 ✅ COMPLETE

| Fix | File | What changed |
|-----|------|-------------|
| HumanLayer timeout → REJECT | `core/loop/permission_gateway.py:113,282` | `asyncio.wait_for` timeout now catches `asyncio.TimeoutError` → returns `False` (reject) instead of propagating exception |
| DB key fail-fast | `core/memory/episodic.py:58-63` | Removed hardcoded `"vector_dev_fallback_change_me"` fallback; raises `RuntimeError` if SQLCipher is active but no key is found |
| SSRF guard wired | `core/inference/provider_client.py` | Added `_ssrf_check()` helper; called before every httpx POST in `_call_openai_compat`, `_call_anthropic`, `_call_gemini` |
| Prompt injection at API boundary | `core/api/routers/commands.py` | `scan_text()` called on `body.text` before any processing; CRITICAL findings raise HTTP 400 |
| asyncio.timeout on observe loop | `core/loop/autonomous_loop.py:458-473` | `async with asyncio.timeout(15)` wraps `_observe_tick()`; `TimeoutError` caught and logged |
| asyncio.timeout on think loop | `core/loop/autonomous_loop.py:547-556` | `async with asyncio.timeout(60)` wraps `_think_tick()`; `TimeoutError` caught and logged |
| ScreenObserver/FaceDetector non-blocking | `core/loop/autonomous_loop.py:1572,1582` | `ScreenObserver().observe` and `FaceDetector().capture_and_scan` moved to `asyncio.to_thread()` in `_sense_tick` |
| CI enforces tests | `.github/workflows/ci.yml:46-49` | Removed `continue-on-error: true`; pytest now blocks merges on failure |
| NSSM service installer | `scripts/install_service.ps1` | PowerShell script: installs VECTOR as Windows service (auto-restart on crash, log rotation) via NSSM |

**Verification:** 101 unit tests pass (permission gateway × 63+, memory stores × 38). Wake word already `hey_vector` (no change needed).

## Logic Fixes — Session 2026-05-29 (second pass) ✅ COMPLETE

| Fix | File | What changed |
|-----|------|-------------|
| ReasoningBank import path | `core/loop/decision_engine.py:81-92` | Changed `from reasoning_bank import` → `from vectorcode.src.reasoning_bank import` with fallback; RULE 8 was silently disabled — now online with 57 entries |
| ReasoningBank failure visibility | `core/loop/decision_engine.py:90` | `logger.debug` → `logger.warning` so RULE 8 failure is always visible |
| Guidance/ThreatDetector failure visibility | `core/loop/autonomous_loop.py:203` | `logger.debug` → `logger.warning`; self-defense layer loss is now logged at warning level |
| ContinueGate failure visibility | `core/loop/autonomous_loop.py:214` | Same: `logger.debug` → `logger.warning` |
| Goal expiry | `core/brain/goal_system.py` | Added `_prune_expired()`: expires goals past `due_date` or stale (SHORT 7d, MID 30d, LONG 90d with zero progress); `add_goal()` now accepts `due_date`; `get_active_goals()` prunes first |
| NSSM graceful shutdown | `scripts/install_service.ps1` | Added `AppStopMethodConsole=1` so NSSM sends CTRL+C → Python asyncio drains cleanly before exit |

**Verification:** 112 decision/goal tests pass. ReasoningBank loads 57 entries live. Goal expiry confirmed: expired goals excluded from active list.

**Remaining manual steps (one-time setup):**
- `pip install face-recognition mediapipe openwakeword` — activates vision + voice
- Train "Hey VECTOR" ONNX wake word (10 samples → openWakeWord)
- `fly launch && fly deploy` in `cloud/brain_server/` — cloud brain
- `bash phone_node/setup.sh` on old Android (Termux)
- `powershell -File scripts/install_service.ps1` (as Admin) — supervised Windows service

---

## Deferred (post-v1 — explicitly not production-blocking)

| Item | What remains | Why deferred |
|------|-------------|--------------|
| SysPath S3-S5 | Remove remaining 16 `sys.path.insert` calls in `districts/` and `vectorcode/` | All are legitimate runtime or architecture uses (bare imports, optional SDK paths); removing them requires editable-install verification per-file |
| RunVectorRefactor S2-S3 | Delete `bootstrap_agents()` and replace fully with manifest-driven loading | Manifest co-exists; full rewrite is a breaking refactor requiring migration testing |
| CloudDeployGaps S3 | Cloudflare KV namespace binding, Supabase migrations, dashboard panels for failover | Multi-region HA — not applicable for local-first single-owner VECTOR |

---

## Absorbed Repos — Session 2026-05-28 ✅ COMPLETE

| Repo | What was absorbed (reimplemented in Python — zero foreign code copied) | Python Location | Status |
|------|----------------------------------------------------------------------|-----------------|--------|
| Understand-Anything-main (TypeScript/Vue, MIT) | **Not absorbable as a whole** — 90% is a TypeScript codebase visualization tool (tree-sitter parsers, Vue dashboard, 9 LLM agent workflow .md files). VECTOR already has VectorCode Intelligence (`vc_search`, `vc_impact`, `vc_flow`, `vc_graph`, `vc_symbol`). Five genuine Python utility scripts (~2,800 LOC total) absorbed as `core/knowledge/`: **(1) DomainExtractor** — multi-language entry point + file signature scanner: HTTP routes (Express/Flask/FastAPI/NestJS/Next.js), CLI (argparse/yargs), events, cron, GraphQL, gRPC across 11+ languages; gitignore-aware file tree scan; priority-weighted file signatures; 4-step output clamping to ≤512KB. **(2) WikiParser** — Karpathy-format markdown wiki → scan manifest: H1 article nodes, `##` topic nodes from index.md, wikilink resolution, backlink computation, complexity from wikilink density, category/tag extraction. **(3) WikiMerger** — assembles scan-manifest + LLM analysis batches into final knowledge graph: entity deduplication (normalized name), edge type normalization (aliases), layer building from categories, tour generation from index.md section ordering, "Other" layer for uncategorized nodes. **(4+5) GraphMerger + SubgraphMerger** — normalize codebase batch analysis results: node ID normalization (double prefix, project-name prefix, `func:`→`function:`, bare paths), complexity normalization (low/medium/high → simple/moderate/complex), deterministic two-pass tested_by linker (Pass 1: flip inverted LLM edges; Pass 2: path-convention supplement for Go/Python/JS-TS/Java/Kotlin/C#/C++), edge deduplication (weight-aware), importMap recovery from scan-result.json; SubgraphMerger: node dedup (last wins), edge dedup (higher weight), layer union, tour title merge with longer description. | `core/knowledge/__init__.py`, `core/knowledge/domain_extractor.py`, `core/knowledge/wiki_parser.py`, `core/knowledge/wiki_merger.py`, `core/knowledge/graph_merger.py` | ✅ |
| postiz-app-main (TypeScript/NestJS/AGPL-3.0) | **Not absorbable as a whole** — core is a TypeScript SaaS with Temporal workflows, Prisma ORM, Bull queues, and a Next.js dashboard (AGPL, 200h+ cost). VECTOR already has: `districts/content/` (ScriptGen, VideoGen, Uploader), instagrapi, YouTube upload, agency/client manager. Three genuine Python-portable gaps absorbed: **(1) Post analytics retriever** (`districts/content/analytics_retriever.py`) — `AnalyticsRetriever` fetches real post-publish metrics: YouTube Data API v3 (views/likes/comments/watch_time) + YouTube Analytics API v2 (estimatedMinutesWatched) via `google-api-python-client`; Instagram Graph API (impressions/reach/likes/comments/shares) via httpx. `PostMetrics` dataclass with `engagement_rate` auto-computed. `get_batch_metrics(posts)` + `summary()` aggregator. All methods degrade gracefully without credentials. **(2) Blog platform publisher** (`districts/content/blog_publisher.py`) — `BlogPublisher` publishes Markdown/HTML to three platforms: Dev.to (REST POST /articles, api-key header), Hashnode (GraphQL `publishPost` mutation, Authorization header), Medium (2-step: GET /me → POST /users/{id}/posts, Bearer token). `publish_all(title, content, platforms=[...])` targets all configured platforms. Tags capped at platform limits (4 for Dev.to, 5 for Medium). `PublishResult` dataclass. All methods degrade gracefully without API keys. **(3) Post job tracker** (`districts/content/post_job.py`) — `PostJobTracker` SQLite WAL-backed state machine: PENDING→PUBLISHING→PUBLISHED/RETRYING/FAILED/CANCELLED. `mark_retrying()` auto-transitions to FAILED when `attempt_count≥max_retries`. Error log kept (last 20). `update_metrics()` merges analytics after publish. `list_pending()` returns PENDING+RETRYING. `summary()` returns per-status counts. Closes the content district feedback loop: publish→track→optimize. | `districts/content/analytics_retriever.py`, `districts/content/blog_publisher.py`, `districts/content/post_job.py` | ✅ |
| OpenWA-main (TypeScript/Node.js NestJS, MIT) | **Not absorbable as a whole** — core is `whatsapp-web.js` (Puppeteer reverse-engineering of WhatsApp Web; TypeScript-only, violates WhatsApp ToS for production, would require 200–400h to reimplement). VECTOR already has: `core/audit/` (MerkleAuditChain), `core/collections/storage.py` (Local+S3), 30+ channel adapters including WhatsApp Cloud API. Three genuine Python-portable gaps absorbed: **(1) HMAC-SHA256 webhook signing** (`core/engine/webhook/hmac_signer.py`) — `WebhookSigner.sign(body, secret)` → `sha256=<hex>`, constant-time `verify()`, `signed_headers()` producing X-Signature-256+X-Delivery-Id+X-Timestamp; `WebhookDelivery` with retry+backoff; upgraded `vectorcode/src/channels/webhook.py` to use HMAC instead of raw secret header. **(2) Bulk message scheduler** (`vectorcode/src/channels/bulk_sender.py`) — `BulkSender(channel)` with per-provider rate limits (WhatsApp 80msg/s, Telegram 30, Slack 1, Discord 5, default 2); `send_bulk(messages, dry_run=False)` → `BulkResult(sent, failed, skipped, success_rate, elapsed_seconds)`; `fail_fast` mode; configurable rate_limit_override. **(3) WhatsApp Business Cloud API extensions** (`vectorcode/src/channels/whatsapp_business.py`) — `WhatsAppBusinessChannel` extends `WhatsAppChannel` with: `send_template()` (HSM), `send_image/video/audio/document/sticker()` (media types), `send_reaction()/remove_reaction()` (emoji reactions), `send_interactive_buttons()` (max 3, caps at 3), `send_interactive_list()` (list picker), `send_channel_message()` (Channels/Newsletter API). Skipped: whatsapp-web.js Puppeteer engine, React dashboard, TypeORM migrations, NestJS DI patterns, QR lifecycle (all tied to unofficial reverse-engineering). | `core/engine/webhook/__init__.py`, `core/engine/webhook/hmac_signer.py`, `vectorcode/src/channels/bulk_sender.py`, `vectorcode/src/channels/whatsapp_business.py`, upgraded `vectorcode/src/channels/webhook.py` | ✅ |

Verified: `tests/test_postiz_absorption.py` 69 passed (PostMetrics dataclass + to_dict; PostRef; AnalyticsRetriever YouTube no-creds graceful/no-crash/missing-path/type; YouTube mock API views+likes+engagement; Instagram no-token/mock-api-success/api-error; batch empty/youtube/instagram/ig-alias/unsupported/mixed/summary; PublishResult to_dict; BlogPublisher Dev.to no-key/no-httpx/mock-success/api-error/tags-cap-4/exception; Hashnode no-token/no-pub-id/mock-success/graphql-errors; Medium no-token/get-me-fail/mock-success/tags-cap-5; publish_all no-keys/platform-filter/two-platforms/default-all/partial-success; JobStatus enum values; PostJob can_retry/is_terminal x5; PostJobTracker create/get-none/publishing/published/failed/retrying/retrying-auto-fail/cancel/update-metrics/list-pending/list-by-status/list-by-platform/summary/error-log-max-20/scheduled-for/payload/nonexistent-no-crash/multiple-independent).

Verified: `tests/test_openwa_absorption.py` 50 passed (WebhookSigner sign/verify/constant-time/headers; WebhookDelivery success/4xx-no-retry/5xx-retry/signature-in-headers/fan-out/network-error; WebhookChannel HMAC upgrade; BulkSender dry-run/success/partial/fail-fast/empty/success-rate/rate-limits/override/exception/elapsed; WhatsAppBusinessChannel no-token graceful/template/image/reaction/button-cap/video/document/remove-reaction/api-error/inheritance/registry).

Verified: `tests/test_understand_anything_absorption.py` 105 passed (DomainExtractor: scan returns context, file count, HTTP route detect, CLI subparser detect, entry point fields, file signatures, README metadata, to_dict structure+values, output JSON write, 512KB size limit, invalid root raises, skip_dirs excluded, source ext filtered, forward slashes, FastAPI decorator detect; WikiParser: parse returns manifest, required keys, article nodes, topic nodes, article fields, complexity valid values, categorized_under edges, wikilink→related edge, categories from index headings, backlinks computed, edge fields, parse_to_file writes JSON, no duplicate node IDs, no duplicate edges, article prefix, topic prefix, empty wiki minimal manifest; WikiMerger: merge returns dict, version, kind knowledge, required keys, base nodes preserved, batch entity added, entity dedup, dangling edge dropped, edge dedup, layer built from categories, layer contains article, uncategorized gets other layer, tour generated, tour step order, node type alias normalized, edge type alias normalized, unknown node type skipped, write output, project name detected, no batches uses manifest, empty/None batches accepted; GraphMerger: returns tuple, empty batches, double prefix stripped, func: canonicalized, project-name prefix stripped, bare path prefixed, complexity low/medium/high/numeric/unknown normalization, node missing id skipped, duplicate nodes last wins, edge dedup weight-aware, dangling edge dropped, direction both→bidirectional/invalid→forward, tested_by inverted flipped, tested_by Go/Python/TS path convention, tested_by production tagged, test↔test dropped, report summary, importMap recovery success/no-file/no-importmap/skip-duplicates; SubgraphMerger: empty, single passthrough, node dedup last wins, edge dedup weight-aware, dangling edge dropped, layer union, dangling layer refs dropped, tour merge same title, tour reordered, project languages merged, project latest analyzedAt, required keys, report summary, node missing id reported; Integration pipeline: parser→merger, valid structure, all edge endpoints exist, all layer refs exist, parse_to_file→merge_from_disk; __init__ imports).

---

## Absorbed Repos — Session 2026-05-27 ✅ COMPLETE

| Repo | What was absorbed (reimplemented in Python — zero foreign code copied) | Python Location | Status |
|------|----------------------------------------------------------------------|-----------------|--------|
| nango-master (TypeScript/ELv2) | **Not absorbable** (ELv2 license, TypeScript-only). Revealed four genuine VECTOR OAuth gaps, all reimplemented natively in Python: **(1) Provider registry expanded 20→80+ via YAML** — `providers.yaml` with 83 providers across 9 categories (dev_tools, productivity, communication, social, finance, crm, ai, storage, ecommerce); `ProviderConfig` unified dataclass with `auth_mode` field (oauth2/oauth1/api_key/basic); `OAuthProviderConfig`/`OAuth1ProviderConfig` backward-compat aliases kept. **(2) `expires_at` bug fixed** — was stored as raw seconds string `str(expires_in)`, now stored as absolute ISO-8601 UTC timestamp via `_expires_at_from_seconds()`. `OAuthToken.is_expired(buffer_minutes)` added. `get_token()` now auto-checks expiry. **(3) Auto-refresh** — `OAuthFlowManager._sync_refresh()` + `get_token()` auto-refreshes on expiry; `refresh_expiring_tokens(threshold_minutes=60)` for proactive refresh. **(4) OAuth 1.0a** — `get_oauth1_request_token()` + `complete_oauth1()` + `get_oauth1_session()` via `requests-oauthlib` (guarded import, degrades gracefully). Background refresh scheduler every 30 min via APScheduler. OAuth 1.0a authorize+callback endpoints added to server. | `core/engine/oauth/providers.yaml` (83 providers), `core/engine/oauth/providers.py` (YAML loader + ProviderConfig), `core/engine/oauth/flows.py` (is_expired + auto-refresh + OAuth1), `core/engine/oauth/server.py` (absolute expiry + OAuth1 endpoints + scheduler startup), `core/engine/oauth/refresh_scheduler.py` (APScheduler background job) | ✅ |
| auto-browser-main (Python/FastAPI/Playwright) | **DOM pruner** (relevance-scored interactive element pruning — reduces ~18k-token browser observations to ~500 tokens; scoring: task keyword match + element type priority + visibility + recency), **PII scrubber** (17 regex patterns: AWS/GCP/Azure keys, JWT, Bearer, PEM, credit cards + Luhn check, SSN, email, US/intl phone, generic hex/b64; Pillow pixel-redaction of screenshots via OCR bounding boxes, guarded import; network body + console log scrubbing), **named browser auth profiles** (save Playwright `context.storage_state()` → named folder, load on demand, list/delete/export/import tar.gz, path-traversal-safe). Skipped: mesh/delegation (multi-browser-agent distributed fleet), harness/skill-induction (auto-browser's own agent framework), witness policy system, BrowserObservationService (VECTOR already has browser_controller + stealth_browser), provider adapters (VECTOR has 27-provider provider_client.py), session tunnel/share, cron/maintenance (VECTOR has APScheduler + autonomous_loop). | `core/browser/__init__.py`, `core/browser/dom_pruner.py`, `core/browser/pii_scrub.py`, `core/browser/auth_profiles.py` + `core/config.py` (browser section) + `core/mcp_server.py` (3 MCP tools: browser_prune_dom, browser_list_auth_profiles, browser_save_auth_profile) | ✅ |
| voicebox (Python/React/Tauri) | **Local zero-shot voice cloning** (Chatterbox-TTS, CUDA, guarded dep), **voice profiles** (cloned/preset/designed + per-profile effects + personality + reference samples, persisted via collections engine + FileStorage), **audio effects/DSP chain** (pedalboard guarded + numpy-native fallback: gain/normalize/delay/echo/pitch/reverb/chorus/compressor/highpass/lowpass), **long-form chunking + crossfade** (unlimited text). Skipped: Tauri/Rust desktop, React UI, MLX backend (Mac-only), STT/VAD/wake-word (VECTOR already has these). Wired ElevenLabs to local-first (`prefer_local_voice=True`): cloning fires before ElevenLabs cloud in both `synthesize()` and `speak_content()`, ElevenLabs stays as graceful fallback. | `core/voice/effects.py`, `core/voice/voice_profiles.py`, `core/voice/cloning.py` + wired `core/voice/tts.py` (`_speak_clone`) + `core/voice/elevenlabs_tts.py` (local-first) + `core/api/routers/voice.py` (4 profile endpoints) + `core/mcp_server.py` (2 MCP tools) + `core/config.py` (VoiceConfig extended) | ✅ |
| pocketbase (Go BaaS) | Collections/schema engine (14 field types + validators, dynamic tables, generic validated CRUD, SAFE parameterized filter parser, sort/paginate/relation-expand), versioned migration runner (`_migrations`, up/down, bootstrap apply), pluggable file storage (local + S3 + Pillow thumbnails, path-traversal-safe), JWT access+refresh auth + bcrypt/PBKDF2 hashing + per-collection RBAC rule DSL (safe AST interpreter, never `eval()`) + OAuth2 login (delegates to existing `core/engine/oauth`), per-collection before/after CRUD hooks bridged to `core/event_bus`. **Only the gaps** — VECTOR already had encrypted SQLite, FastAPI, WebSocket/EventBus realtime, dashboards (those were NOT duplicated). | `core/collections/` (fields, schema, store, migrations, storage, auth, hooks) + `core/api/routers/collections.py` + `core/config.py` (`collections` section) + `core/api/app.py` (router + lifespan bootstrap) | ✅ |

Verified: `tests/test_oauth_nango.py` 40 passed (provider registry 80+ via YAML, is_expired, buffer_minutes, expires_at round-trip, refresh_expiring_tokens, OAuth1 guarded ImportError, scheduler no-crash, /oauth/providers count). `core/engine/oauth/providers.py` OAuthProviderConfig/OAuth1ProviderConfig backward-compat aliases verified. `_expires_at_from_seconds` verified.

Verified: `tests/test_browser_absorption.py` 59 passed (DOMPruner prune/prune_observation/keyword boost/recency/visibility/singleton; PII scrubber 17 patterns + network/console/screenshot-disabled graceful; BrowserAuthStore save/load/list/get/delete/export/import/path-traversal-block/overwrite; MCP tools browser_prune_dom/browser_list_auth_profiles/browser_save_auth_profile; create_app builds). Zero Playwright dependency in tests. Reused: `core/config.py` CONFIG["browser"] section.

Also wired: `POST /api/collections/{name}/auth-with-oauth2` (exposes `AuthService.oauth_login`) and 3 MCP tools in `core/mcp_server.py` (`collection_list`, `collection_query`, `collection_record_create`) so VECTOR's own agents can use the data layer. Deferred as out-of-scope for a single-owner local system: transactional mailer + email-verify/password-reset flows (multi-user-SaaS feature) and a collections admin UI panel (frontend).

Verified: `tests/test_collections.py` 55 passed (data CRUD, safe-filter injection rejection, migrations up/down, storage round-trip+thumbnails, JWT/RBAC, hooks, end-to-end HTTP via TestClient, oauth2 find-or-create login, MCP tool round-trip). 5 sacred memory tables confirmed untouched; collections live in their own `_collections` / `col_<name>` namespace. Reused `core.memory.episodic.get_db_connection` (SQLCipher), `core.event_bus`, `core.engine.oauth`.

---

## Absorbed Repos — Session 2026-05-17 ✅ ALL COMPLETE

| Repo | What was absorbed | Python Location | Status |
|------|-------------------|-----------------|--------|
| jcode (Rust) | CacheTracker, multiedit, apply_patch, AmbientScheduler, SessionPersistence, trajectory auto-compact | `core/jcode/` | ✅ |
| openhuman (Rust+TS) | MemoryTree, TokenJuice, 16 agent roles, ParallelResearcher, OAuthRegistry+Server, VectorTelemetry, VectorSentry, OFP P2P, SubagentRunner, ReliableProvider, ModelRouter, ToolDispatcher, ChannelRuntime, JARVIS dashboard, ElevenLabsTTS | `core/engine/` + `dashboard/` | ✅ |
| openfang (Rust) | MerkleAuditChain, BudgetMeter, GCRARateLimiter, PromptInjectionScanner, SSRFGuard, TaintTracker, KnowledgeGraph, LoopGuard, SessionRepair, 9 Autonomous Hands, VectorSandbox, OFPNode P2P, PeerDiscovery, VectorMigrator, 27 LLM providers, 5 new channel adapters | `core/audit/` + `core/metering/` + `core/security/` + `core/network/` + `core/sandbox/` + `core/migration/` + `core/inference/` + `agents/hands/` + `vectorcode/src/channels/adapters/` | ✅ |

---

## Core Intelligence Stack ✅ COMPLETE

| Module | File | Status |
|--------|------|--------|
| Config + secrets | `core/config.py` | ✅ Pydantic-validated, SecretStr, no hardcoded keys |
| Context engine (RULE 1) | `core/loop/context_engine.py` | ✅ 14-domain world state, session_hydration_prompt() |
| Decision engine (5-factor) | `core/loop/decision_engine.py` | ✅ goal(30%)+conf(25%)+policy(20%)+urgency(15%)+timing(10%)-cost(5%) |
| Policy memory (RULE 7) | `core/memory/policy.py` | ✅ EMA get_score() BEFORE + update_from_outcome() AFTER |
| Reasoning memory (RULE 8) | `core/memory/reasoning_memory.py` | ✅ All chains stored, reward>0.7 → training data |
| Permission gateway (RULE 3) | `core/loop/permission_gateway.py` | ✅ GREEN/YELLOW/RED, Pushover owner approval (HumanLayer removed 2026-06-19), FORBIDDEN list |
| Autonomous loop (RULE 2) | `core/loop/autonomous_loop.py` | ✅ run_forever(), observe→think→act→reflect, never stops |
| Episodic memory | `core/memory/episodic.py` | ✅ SQLite FTS5, WAL, AES-256 optional (SQLCipher) |
| Goal system (3 horizons) | `core/brain/goal_system.py` | ✅ LONG/MID/SHORT, 5 pre-seeded goals |
| Epistemic tracker (Gap 3) | `core/brain/epistemic_tracker.py` | ✅ Confidence decay, staleness detection |
| Red team agent (Gap 2) | `core/brain/red_team_agent.py` | ✅ Adversarial review before RED actions |
| Hypothesis engine (Gap 5) | `core/brain/hypothesis_engine.py` | ✅ Proactive insights every 4h |
| Synthesis bridge (Gap 1) | `core/brain/synthesis_bridge.py` | ✅ Cross-domain pattern detection every 30min |
| Ollama safe (RULE 11 updated) | `core/inference/ollama_safe.py` + `core/inference/provider_client.py` | ✅ Ollama primary; 27 cloud providers via API keys (RULE 11 updated 2026-05-17) |
| Provider registry (27 providers) | `core/inference/llm_providers.py` | ✅ Anthropic, Gemini, OpenAI, Groq, DeepSeek, Mistral, OpenRouter, Together, Fireworks, Perplexity, Cohere, Azure, Cloudflare, vLLM, HF, Replicate, Anyscale, Cerebras, SambaNova, NVIDIA, Moonshot, Zhipu, Baidu, Yi, LMStudio, Ollama + 1 more |

**VECTOR Gaps not yet built (architecture.md marks these Year 2):**
| Gap | Module | Notes |
|----|--------|-------|
| Gap 4 | `counterfactual.py` | ❌ Learns from rejected decisions — Year 2 |
| Gap 6 | `causal_graph.py` | ❌ Causal reasoning — Year 2 |
| Gap 7 | `person_model.py` | ❌ Theory of mind per person — Year 2 |
| Gap 8 | `meta_cognition.py` | ❌ Monthly bias detection — Year 2 |

---

## Agent City ✅ COMPLETE

| Module | File | Status |
|--------|------|--------|
| Agent base + HP system | `core/city/agent_base.py` | ✅ HP 0-1000, ghost memory, council gate >700 HP |
| Agent registry (Darwinism) | `core/city/agent_registry.py` | ✅ Death→ghost→successor, thread-safe singleton |
| Governor (routing) | `core/city/governor.py` | ✅ RULE 9 HP wired, LLM classify fallback, council |
| Evolution engine | `core/city/evolution_engine.py` | ✅ Cross-gen lesson inheritance, cull_bottom() |
| MCP server | `core/mcp_server.py` | ✅ 14 real tools + kanban(4) + claims(7) + guidance(3) |

---

## Voice Pipeline ⚠️ PARTIAL

| Component | Status |
|-----------|--------|
| STT — Whisper | ✅ `core/voice/stt.py` ready (base model; upgrade to large-v3 for prod) |
| TTS — Kokoro | ⚠️ `core/voice/tts.py` wired but using pyttsx3 fallback — **model files ARE in `models/kokoro/`** (fp16-gpu.onnx + voices.bin), path just needs wiring |
| Wake word | ⚠️ `core/voice/wake_word.py` uses hey_jarvis placeholder — **"Hey VECTOR" custom training needed** |
| Language detector | ✅ `core/voice/language_detector.py` — HI/BN/AS/JA/EN auto-switch |
| Ambient listener | ✅ `core/voice/ambient_listener.py` |

**To activate full voice:**
1. Download Kokoro model: `pip install kokoro` + pull model weights (~300MB)
2. Train custom wake word: record 10 samples of "Hey VECTOR" → openWakeWord training

---

## Sensing + Control ✅ COMPLETE (libs pending install)

| Component | Status |
|-----------|--------|
| Camera + face ID | ✅ `core/sensing/camera.py` — ⚠️ `face_recognition` + `mediapipe` not pip-installed yet → neutral fallback active |
| Screen observer | ✅ `core/sensing/screen_observer.py` — mss live, pytesseract optional |
| Health monitor | ✅ `core/sensing/health_monitor.py` — psutil live, EAR fatigue scoring |
| Sound classifier | ✅ `core/sensing/sound_classifier.py` — RMS+ZCR heuristic |
| PC controller | ✅ `core/control/pc_controller.py` — pyautogui + screenshots |
| Phone controller (ADB) | ✅ `core/control/phone_controller.py` — ADB bridge |
| Malware detector | ✅ `core/control/security/malware_detector.py` — 3-layer: VT + MIME + LightGBM |

**To activate face recognition:** `pip install face-recognition mediapipe`

---

## Districts — ALL 25 PLANNED ✅ BUILT (28 total, 3 bonus)

### Phase 1 Districts (Days 1-25)
| # | District | Agents | Status |
|---|----------|--------|--------|
| 01 | governance/ | llm_council.py | ✅ 3-stage deliberative council, HP>700 gate |
| 02 | security/ | threat_scout.py, node_guard.py, malware_hunter.py | ✅ Process+registry+network scan |
| 03 | coding/ | git_bot.py, code_reviewer.py, architect_bot.py, bug_hunter.py, test_writer.py | ✅ AST review, circular imports, gateway-gated push |
| 04 | time_calendar/ | kiit_scraper.py, deadline_manager.py, time_blocker.py | ✅ Playwright KIIT, Google Calendar |
| 05 | communications/ | communications_adapter.py, person_model.py, style_model.py | ✅ VectorCode gateway adapter |
| 06 | memory_curator/ | consolidation_bot.py, pattern_finder.py | ✅ LightRAG, Obsidian sync |
| 07 | research/ | web_scout.py, paper_reader.py, news_aggregator.py, reddit_miner.py, opencli_adapter.py, research_hub.py | ✅ DuckDuckGo, ArXiv, RSS, Reddit |
| 08 | intelligence/ | (via news_trends + pattern_detective) | ✅ Absorbed into Phase 3 districts |

### Phase 2 Districts (Days 26-40)
| # | District | Agents | Status |
|---|----------|--------|--------|
| 09 | skills/ | skill_mapper.py, gap_analyst.py, mastery_tracker.py | ✅ Skill graph, gap analysis |
| 10 | languages/ | hindi_coach.py, bengali_coach.py, assamese_coach.py, english_coach.py, japanese_coach.py | ✅ 5 language coaches |
| 11 | interview_prep/ | mock_interviewer.py, report_generator.py, company_researcher.py, feedback_analyst.py | ✅ MockInterviewer + 50-100 page reports |
| 12 | learning/ | video_ingestor.py, concept_extractor.py, course_tracker.py, note_organizer.py | ✅ Any URL video ingestion |
| 13 | finance/ | upi_parser.py, expense_tracker.py, budget_analyst.py, tax_calendar.py | ✅ UPI SMS, Indian FY deadlines |
| 14 | health/ | sleep_tracker.py, fatigue_monitor.py, exercise_logger.py, biometrics_aggregator.py | ✅ EAR fatigue, sleep inference |
| 15 | reflection/ | daily_reviewer.py, journal_writer.py, growth_analyst.py | ✅ 2AM review, Obsidian journal |
| 21 | projects/ | project_planner.py, deadline_watcher.py, progress_tracker.py, doc_writer.py | ✅ T-7/3/1/0 alerts, 5 doc types |

### Phase 3 Districts (Days 41-50)
| # | District | Agents | Status |
|---|----------|--------|--------|
| 16 | startups/ | market_scanner.py, idea_validator.py, competitor_spy.py, revenue_modeler.py | ✅ HN/Reddit/G2 nightly scan |
| 17 | investment/ | stock_analyst.py, fundamentals_bot.py, technical_bot.py, sentiment_bot.py | ✅ NSE/BSE analysis only, never trades |
| 18 | content/ | script_generator.py, video_generator.py, voice_generator.py, uploader.py, comfyui_adapter.py, video_merger.py, caption_generator.py | ✅ SadTalker + FFmpeg CUDA + YouTube |
| 19 | agency/ | content_strategist.py, client_manager.py, performance_tracker.py | ✅ ContentStrategist + ClientManager |
| 20 | karpathy_lab/ | progress_tracker.py, code_typer.py, data_prep.py, architecture_builder.py, autoresearch_runner.py | ✅ 30min/day tracker, OpenMythos pipeline |
| 22 | relationships/ | contact_manager.py, communication_analyst.py | ✅ ContactManager + CommunicationAnalyst |
| 23 | privacy/ | data_flow_auditor.py, privacy_enforcer.py | ✅ Cloud vs local enforcement |
| 24 | pattern_detective/ | behavior_analyst.py, habit_finder.py | ✅ BehaviorAnalyst + HabitFinder |
| 25 | news_trends/ | ai_news_bot.py, market_trends_bot.py, opportunity_spotter.py | ✅ AINewsBot + OpportunitySpotter |

### Bonus Districts (from agency-agents + original plan)
| District | Agents | Notes |
|----------|--------|-------|
| calls/ | call_screener.py, transcription_bot.py, voice_responder.py | ✅ Call handling |
| ops/ | sre_monitor.py, devops_automator.py, incident_commander.py | ✅ VECTOR self-monitors (SLO, DevOps, Incidents) |
| data_analytics/ | analytics_reporter.py, performance_benchmarker.py, data_engineer.py | ✅ Data insights, benchmarks, ETL/lakehouse pipeline |
| personal_growth/ | behavioral_nudge_engine.py, zk_steward.py, feedback_synthesizer.py | ✅ Nudges, Zettelkasten, feedback synthesis |
| documentation/ | technical_writer.py, doc_generator.py | ✅ VECTOR documents itself |
| qa/ | reality_checker.py, evidence_collector.py, workflow_architect.py, api_tester.py, test_results_analyzer.py, accessibility_auditor.py, tool_evaluator.py, workflow_optimizer.py, model_qa_specialist.py | ✅ Full QA suite + WCAG + ML auditing |
| chief_of_staff/ | chief_of_staff.py | ✅ Morning/evening brief, noise filter, district escalation |
| devops/ | merged into ops/ | ✅ Removed — ops/ is the unified DevOps+SRE+Incident district |

### agency-agents Full Alignment — Districts Added 2026-05-17
| District | New Agents | Source |
|----------|-----------|--------|
| coding/ | minimal_change_engineer.py, codebase_onboarding_engineer.py, rapid_prototyper.py | engineering-minimal-change, engineering-codebase-onboarding, engineering-rapid-prototyper |
| security/ | threat_detection_engineer.py | engineering-threat-detection-engineer |
| finance/ | financial_analyst.py, fpa_analyst.py | finance-financial-analyst, finance-fpa-analyst |
| agency/ | sales_strategist.py, proposal_strategist.py | sales-outbound+coach+pipeline, sales-proposal-strategist |
| governance/ | product_manager.py | product-manager |
| marketing/ (**new**) | seo_specialist.py, growth_hacker.py, social_media_strategist.py, content_creator.py, ai_citation_strategist.py | marketing-seo, marketing-growth-hacker, marketing-social-media, marketing-content-creator, marketing-ai-citation+agentic-search |
| design/ (**new**) | ui_designer.py, ux_researcher.py, image_prompt_engineer.py | design-ui-designer, design-ux-researcher, design-image-prompt-engineer |

**Total Python agent files: 133 | Districts: 33 | Governor routes: 180**

---

## Absorbed Repos — ALL COMPLETE ✅

| Repo | What was absorbed | Where |
|------|-------------------|-------|
| OpenJarvis | 98.2% of symbols — VectorAgent SDK, eval backends, LSP | `vectorcode/src/` |
| Hermes/vectorcode | 89.5% — gateway, 25+ platform adapters, curator, swarm, claims, guidance | `vectorcode/src/` |
| Ruflo | 100% — neural RL, MoE router, FlashAttention, ReasoningBank, 282 SKILL.md | `vectorcode/src/` + `brain/.claude/skills/` |

**Zero external repo traces** (hermes/ruflo/openjarvis/Jarvis/NousResearch/HermesBackend) — verified.

---

## Neural Intelligence Layer ✅ COMPLETE (absorbed from Ruflo)

| Module | Contents | Status |
|--------|----------|--------|
| `vectorcode/src/neural_training.py` | A2C, DQN, PPO, SARSA, Q-Learning, DecisionTransformer, VECTORTrainer | ✅ 6 RL algorithms, fully wired into decision_engine |
| `vectorcode/src/neural_flash_attention.py` | FlashAttention — O(N) block-tiled, online softmax | ✅ |
| `vectorcode/src/neural_moe_router.py` | MoERouter — 8-expert gating, top-k, load balance | ✅ Wired as Layer 0 in GNNRouter |
| `vectorcode/src/reasoning_bank.py` | ReasoningBank + PatternLearner — RULE 8 compliance | ✅ Wired into decision_engine (inject before + store after) |
| `vectorcode/src/router.py` | GNNRouter: MoE(L0)→GNN(L1)→keyword(L2)→regex(L3) | ✅ 4-layer routing |
| `vectorcode/src/claims.py` | ClaimService, WorkStealingService, LoadBalancer | ✅ |
| `vectorcode/src/guidance.py` | ThreatDetector, AuthorityGate, CoherenceScheduler, ContinueGate | ✅ Wired in autonomous_loop |
| `vectorcode/src/swarm.py` | SwarmCoordinator — 8 topologies (Byzantine, Raft, Gossip, CRDT, Quorum...) | ✅ |
| `vectorcode/src/agent/curator.py` | Background skill maintenance orchestrator (1749L) | ✅ Wired in vector_cli/curator.py |
| `vectorcode/src/agent/lsp/` | LSP client, manager, protocol — real-time lint delta | ✅ Full 10-file package |
| `vectorcode/src/agent/tool_guardrails.py` | ToolCallGuardrailController | ✅ Wired in run_agent.py |

---

## Cloud Deployment ⚠️ CODE DONE — NOT YET DEPLOYED

| Component | Code | Deploy |
|-----------|------|--------|
| Fly.io brain server | ✅ `cloud/brain_server/main.py` FastAPI + /status | ❌ Run: `fly launch` in cloud/brain_server/ |
| Cloudflare Worker API | ✅ `api/src/` + `wrangler.toml` | ❌ Run: `wrangler deploy` in api/ |
| Cloudflare D1/R2/KV | ✅ Config in wrangler.toml | ❌ Provision via Cloudflare dashboard |
| Supabase cloud DB | ✅ Config in core/config.py | ❌ Create project + run migrations |
| Next.js Dashboard | ❌ `dashboard/src` missing | ❌ Not built yet |
| Phone Termux node | ✅ `phone_node/ambient_server.py` + `setup.sh` | ❌ Run setup.sh on Android |

---

## Tests ✅ ALL PASSING

| Suite | Result |
|-------|--------|
| `scripts/smoke_test.py` | 38/38 PASS |
| `scripts/integration_check.py` | 51/51 PASS |
| `tests/test_phase2_districts.py` | 47/47 PASS |

---

## End-of-Day Gates (Final State)

```
Day 1: python run_vector.py → JSON response + SQLite row        ✅ PASS
Day 2: debug mode → 4 candidates + scores + policy table rows  ✅ PASS
Day 3: "Hey VECTOR" → WAKE → TRANSCRIBE → THINK → SPEAK        ⚠️ PARTIAL (pyttsx3 TTS; Kokoro model not downloaded; hey_jarvis placeholder)
Day 4: Face ID + cursor control + ADB screenshot                ⚠️ PARTIAL (cursor/ADB ready; face_recognition pip install pending)
Day 5: GmailAgent reads + KIIT schedule + auto-commit           ✅ PASS (KIIT scraper + GitBot ready)
Day 6: fly.dev/status 200 + ambient running + Obsidian note     ❌ NOT DEPLOYED (code complete; run fly launch + setup.sh)
Day 7: all 4 end-to-end scenarios pass                          ⚠️ Code complete; integration test pending on live system
Phase 2: Reflection/Health/Finance/Projects districts           ✅ 14 agents, 47 tests passing
Phase 3: All 10 districts built                                 ✅ startups/investment/content/agency/karpathy_lab + 5 more
```

---

## What Needs to Happen Before "Shipped"

### Must-do (blocks autonomous operation)
1. **Download Kokoro TTS model** — `pip install kokoro` + model weights
1b. **[Optional] Activate local voice cloning** — `pip install chatterbox-tts` (torch/CUDA), then record a 10–20s reference WAV and POST it to `POST /voice/profiles/{name}/sample` + `POST /voice/profiles/{name}/default`. After that VECTOR speaks in your voice locally with no ElevenLabs.
2. **Train "Hey VECTOR" wake word** — record 10 samples, openWakeWord training
3. **`fly launch`** in `cloud/brain_server/` → VECTOR has a cloud brain
4. **`setup.sh`** on Android Termux → ambient phone node active
5. **`pip install face-recognition mediapipe`** → face ID works
6. **`wrangler deploy`** in `api/` → Cloudflare API live

### Nice-to-have (not blocking)
7. Build Next.js dashboard (`dashboard/src/`) — monitoring UI
8. `data_analytics/` district has agents — `devops/` merged into `ops/`
9. Build Gap 4 `counterfactual.py` — learns from rejected decisions

### Year 2 (explicitly planned for later)
- Gap 6 `causal_graph.py`
- Gap 7 `person_model.py`
- Gap 8 `meta_cognition.py`
- OpenMythos custom LLM training
- Full vector-chairman fine-tune on reasoning chains
