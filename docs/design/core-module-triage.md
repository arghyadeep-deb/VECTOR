# core/ module triage (2026-09-24)

Companion to `docs/design/dead-code-deletion-plan-v2.md`. Owner direction: **keep everything, make useful modules integral**. Nothing deleted.

Dispositions: **WIRED** = connected to the running system in this pass; **DORMANT** = duplicates a live mechanism, kept with a banner (a second live path would bypass the Governor / PermissionGateway); **KEEP** = standalone tool, optional/gated feature, or used by another process — no runtime hook needed or safe without its own design.

## Wired in this pass
| module | how |
|---|---|
| `core.repo_hygiene` | wired: `tools/ci_gate.py` now fails on tracked secrets / runtime artifacts |
| `core.cloud.heartbeat` | wired: cron `cloud-heartbeat` (5 min); no-op until `VECTOR_BRAIN_URL` is configured |
| `core.engine.oauth.flows` | (already live) proactive refresh now scheduled: cron `oauth-refresh` (30 min) |

## Dormant duplicates (banner added, files unchanged otherwise)
| module | superseded by |
|---|---|
| `core/api/auth.py` | the API auth middleware (validates VECTOR_API_KEY) and core/api/routers/auth_jwt.py |
| `core/brain/router.py` | Governor routing (core/city/governor.py) |
| `core/brain/self_evolve.py` | core/city/evolution_engine.py |
| `core/city/point_system.py` | the HP system in core/city/agent_base.py |
| `core/city/task_router.py` | Governor routing (core/city/governor.py) |
| `core/inference/model_router.py` | core/inference/provider_client.py + model_pool |
| `core/inference/provider_registry.py` | core/inference/llm_providers.py (PROVIDERS) and model_catalog.yaml |
| `core/inference/district_llm.py` | vectorcode_llm / provider_client via AgentBase |
| `core/communications/hub.py` | the vectorcode channel gateway |
| `core/loop/planner.py` | core/runtime/plans.py (PlanStore/PlanRunner) |

## Everything else (unreachable by static analysis)
| module | lines | disposition | why |
|---|---|---|---|
| `core.api_manager` | 351 | KEEP | legacy API manager; superseded by key_pool / provider_health (verify before removal) |
| `core.city.evolution_audit` | 45 | KEEP | audit schemas (dataclasses); no live mechanism duplicates them, no caller yet |
| `core.city.intent_bert` | 302 | KEEP | used by scripts/train_intent_real.py & auto_retrain_intent.py (offline classifier training); live routing uses intent_matcher + regex |
| `core.city.intent_monitor` | 250 | KEEP | used by scripts/train_intent_real.py & auto_retrain_intent.py (offline classifier training); live routing uses intent_matcher + regex |
| `core.city.intent_qwen3_8b` | 235 | KEEP | used by scripts/train_intent_real.py & auto_retrain_intent.py (offline classifier training); live routing uses intent_matcher + regex |
| `core.cloud.failover` | 117 | KEEP | cloud-brain failover/sync; Fly.io was declined, Cloudflare Worker is the cloud path |
| `core.cloud.heartbeat` | 109 | WIRED | wired: cron `cloud-heartbeat` (5 min); no-op until `VECTOR_BRAIN_URL` is configured |
| `core.cloud.remote_sync` | 148 | KEEP | cloud-brain failover/sync; Fly.io was declined, Cloudflare Worker is the cloud path |
| `core.communications` | 2 | KEEP | standalone / used by scripts or other processes |
| `core.control.legion_wake` | 35 | KEEP | Wake-on-LAN for the Legion node; used from the phone node, outside this process |
| `core.control.security.node_router` | 161 | KEEP | Wake-on-LAN for the Legion node; used from the phone node, outside this process |
| `core.control.wake_on_lan` | 67 | KEEP | Wake-on-LAN for the Legion node; used from the phone node, outside this process |
| `core.engine.agents` | 15 | KEEP | role templates + sub-agent runner; candidate for the coding/research swarms (needs design) |
| `core.engine.agents.roles` | 372 | KEEP | role templates + sub-agent runner; candidate for the coding/research swarms (needs design) |
| `core.engine.agents.subagent_runner` | 207 | KEEP | role templates + sub-agent runner; candidate for the coding/research swarms (needs design) |
| `core.engine.oauth.refresh_scheduler` | 121 | KEEP | self-hosted OAuth proxy server; the API's own oauth router is the live path |
| `core.engine.oauth.server` | 392 | KEEP | self-hosted OAuth proxy server; the API's own oauth router is the live path |
| `core.engine.token_juice` | 3 | KEEP | token compression; candidate to wire into context hydration (needs design + tests) |
| `core.engine.token_juice.compressor` | 263 | KEEP | token compression; candidate to wire into context hydration (needs design + tests) |
| `core.errors` | 139 | KEEP | typed exception hierarchy; adopt incrementally, not a runtime path |
| `core.experiments` | 2 | KEEP | A/B framework; no experiment defined yet |
| `core.experiments.ab_testing` | 246 | KEEP | A/B framework; no experiment defined yet |
| `core.integrations` | 1 | KEEP | one-time Gmail OAuth setup helper (manual CLI) |
| `core.integrations.gmail_auth` | 85 | KEEP | one-time Gmail OAuth setup helper (manual CLI) |
| `core.jcode.semantic_cache` | 68 | KEEP | semantic LLM cache; would touch every LLM call, so flag-gated wiring needs its own design |
| `core.mcp` | 10 | KEEP | outbound MCP client; needs an explicit gateway policy before use |
| `core.mcp.client` | 310 | KEEP | outbound MCP client; needs an explicit gateway policy before use |
| `core.memory.external_mirror` | 35 | KEEP | disabled optional external mirror boundary (by design) |
| `core.memory.vector_index_gate` | 22 | KEEP | optional vector-index scale gate (by design) |
| `core.mining._constants` | 12 | KEEP | opt-in Pearl miner providers; off by default, own subprocess entry points |
| `core.mining._install` | 65 | KEEP | opt-in Pearl miner providers; off by default, own subprocess entry points |
| `core.mining._miner_loop_main` | 226 | KEEP | opt-in Pearl miner providers; off by default, own subprocess entry points |
| `core.mining._mps_miner_loop_main` | 312 | KEEP | opt-in Pearl miner providers; off by default, own subprocess entry points |
| `core.mining._pearl_subprocess` | 210 | KEEP | opt-in Pearl miner providers; off by default, own subprocess entry points |
| `core.mining.apple_mps_pearl` | 106 | KEEP | opt-in Pearl miner providers; off by default, own subprocess entry points |
| `core.mining.cpu_pearl` | 214 | KEEP | opt-in Pearl miner providers; off by default, own subprocess entry points |
| `core.mining.vllm_pearl` | 159 | KEEP | opt-in Pearl miner providers; off by default, own subprocess entry points |
| `core.models` | 3 | KEEP | data models for the health endpoint |
| `core.models.health_models` | 71 | KEEP | data models for the health endpoint |
| `core.repo_hygiene` | 95 | WIRED | wired: `tools/ci_gate.py` now fails on tracked secrets / runtime artifacts |
| `core.resilience.hot_failover_api` | 77 | KEEP | hot-failover API helper; no live caller |
| `core.sandbox.skill_sandbox` | 200 | KEEP | skill/WASM sandboxes; would sit behind the gateway, needs design |
| `core.sandbox.wasm_runner` | 160 | KEEP | skill/WASM sandboxes; would sit behind the gateway, needs design |
| `core.scheduler.tools` | 349 | KEEP | MCP scheduler tools; would add tool surface, gateway policy first |
| `core.scraper.cli` | 679 | KEEP | vendored scraper with its own CLI |
| `core.scraper.core._shell_signatures` | 118 | KEEP | vendored scraper with its own CLI |
| `core.scraper.core.ai` | 918 | KEEP | vendored scraper with its own CLI |
| `core.scraper.core.shell` | 690 | KEEP | vendored scraper with its own CLI |
| `core.scraper.core.utils._shell` | 48 | KEEP | vendored scraper with its own CLI |
| `core.security.secrets_providers` | 317 | KEEP | secrets-provider backends / workspace audit; candidates for the security district (needs design) |
| `core.security.workspace_audit` | 40 | KEEP | secrets-provider backends / workspace audit; candidates for the security district (needs design) |
| `core.sensing.sound_classifier` | 250 | KEEP | sound classifier; needs a mic sensing hook in the observe loop |
| `core.services.orchestrator.main` | 118 | KEEP | service templates, not used by the single-owner runtime |
| `core.services.service_template` | 114 | KEEP | service templates, not used by the single-owner runtime |
| `core.trading.agents.analysts.social_media_analyst` | 23 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.cli.announcements` | 57 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.cli.config` | 6 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.cli.main` | 1258 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.cli.models` | 12 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.cli.stats_handler` | 76 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.cli.utils` | 524 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.crypto_trading` | 49 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests` | 1 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.conftest` | 52 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_api_key_env` | 149 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_capabilities` | 107 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_checkpoint_resume` | 147 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_dataflows_config` | 61 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_deepseek_reasoning` | 240 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_env_overrides` | 98 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_google_api_key` | 31 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_memory_log` | 860 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_minimax` | 73 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_model_validation` | 55 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_ollama_base_url` | 167 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_safe_ticker_component` | 52 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_signal_processing` | 90 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_structured_agents` | 232 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.trading.tests.test_ticker_symbol_handling` | 21 | KEEP | TradingAgents subtree with its own CLI and tests; analysis only (never trades) |
| `core.training.benchmarks.voice_engine_benchmark` | 177 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.data_prep` | 336 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.forward` | 328 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.train` | 419 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.vendor.examples.moda_example` | 73 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.vendor.examples.variants_example` | 10 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.vendor.open_mythos` | 55 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.vendor.open_mythos.main` | 1085 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.vendor.open_mythos.moda` | 1063 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.vendor.open_mythos.tokenizer` | 64 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.vendor.open_mythos.variants` | 198 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.openmythos.vendor.training.3b_fine_web_edu` | 551 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.training.weekly_scheduler` | 186 | KEEP | offline training/benchmark tooling, gated off by default |
| `core.ui.chat` | 459 | KEEP | terminal chat UI / HUD broadcaster; the web HUD is the live UI |
| `core.ui.websocket_broadcaster` | 157 | KEEP | terminal chat UI / HUD broadcaster; the web HUD is the live UI |
| `core.utils` | 1 | KEEP | market-hours helper; no live caller |
| `core.utils.market_hours` | 56 | KEEP | market-hours helper; no live caller |
| `core.video.hyperframes_sidecar` | 99 | KEEP | Media Studio server + Hyperframes sidecar; separate FastAPI apps |
| `core.video.studio_server` | 541 | KEEP | Media Studio server + Hyperframes sidecar; separate FastAPI apps |
| `core.voice.effects` | 152 | KEEP | optional voice engines/effects/streamer; selected by config |
| `core.voice.elevenlabs_tts` | 285 | KEEP | optional voice engines/effects/streamer; selected by config |
| `core.voice.engines.supertonic_engine` | 41 | KEEP | optional voice engines/effects/streamer; selected by config |
| `core.voice.streamer` | 156 | KEEP | optional voice engines/effects/streamer; selected by config |
| `core.voice.voice_personality` | 57 | KEEP | optional voice engines/effects/streamer; selected by config |

## Candidates for a follow-up design (highest value, each needs its own spec + tests)
- `core.engine.token_juice` → context hydration (token savings).
- `core.jcode.semantic_cache` → provider_client, behind a config flag.
- `core.engine.agents` roles/sub-agent runner → coding/research swarms.
- `core.security.secrets_providers` / `workspace_audit` → security district.
- `core.sensing.sound_classifier` → observe loop (needs mic hook).

Regenerate with the reachability method in the dead-code plan; re-check before acting.
