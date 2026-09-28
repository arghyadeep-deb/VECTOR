# Dead-code deletion plan v2 — REPORT ONLY (2026-09-24)

**Nothing was deleted or modified.** This is a plan for owner approval (Phase 6 of the external-review program). Regenerate with the method below before acting on any line.

## Method (my own, not Opus's)
- Universe: 6,677 git-tracked `.py` modules, excluding `tests/`, `_cleanup_trash*`, `node_modules`, `test_tmp`.
- Edges: every `import` / `from … import` (including function-local and relative imports), plus string constants shaped like a module path (`pkg.mod` or `pkg.mod:Class`) and f-strings with a package prefix. Importing `a.b.c` also reaches `a` and `a.b`.
- Roots: `run_vector.py`, `core/api/app.py`, `core/mcp_server.py`, `core/mcp_server_stdio.py`, `hands/registry.py`, every class in `config/agent_manifest.yaml`, and any module path mentioned in tracked yaml/json/bat/ps1/toml/sh/Dockerfile (219 roots).
- Dynamic loading: the only real package-scanning loader is `core/swarm/generic_swarm.py` (globs `districts/<d>/*.py`), so all `districts.*` modules are treated as reachable. Other `import_module`/`__import__` sites take constant strings (already captured) or config values.
- Result: **4,434 reachable / 2,243 unreachable** of 6,677. Opus reported ~2,100 reachable of 6,599; my count is higher because string-referenced and manifest/config-referenced modules and all district agents count as reachable. I trust the higher reachable number for deletion safety (it only errs toward keeping code).
- Limits: no runtime tracing; a module loaded by a path built at runtime from data (e.g. a DB row or user config) would look dead. Unreachable ≠ safe to delete until the checks below pass.

## Where the 2,243 unreachable modules live
| area | count | note |
|---|---|---|
| `vectorcode/*` | 1,716 | vendored package; only `vectorcode.src.*` bits used by core are reached. Owner decision on whether the rest is a dependency, not dead code. |
| `core/*` | 338 | detailed below |
| `scripts/*` | 86 | standalone entry scripts — expected to be unreachable from the runtime |
| `tools/*`, `.claude/*`, `VECTOR_TECHNICAL_KNOWLEDGE/*`, `data/*`, other | ~100 | tooling / docs / training artefacts |

## Opus's named `core/` candidates — verified with my method
| module | unreachable? | referenced outside runtime (tests / scripts) | verdict |
|---|---|---|---|
| `core.brain.self_evolve` | **yes** | none | delete candidate |
| `core.brain.router` | **yes** | none | delete candidate |
| `core.loop.planner` | **yes** | none | delete candidate |
| `core.memory.external_mirror` | **yes** | 1 test file(s) | delete candidate (update/delete its tests first) |
| `core.memory.vector_index_gate` | **yes** | 1 test file(s) | delete candidate (update/delete its tests first) |
| `core.city.intent_bert` | **yes** | none | delete candidate |
| `core.city.intent_qwen3_8b` | **yes** | scripts: scripts/auto_retrain_intent.py, scripts/integrate_intent_qwen3.py | delete candidate |
| `core.city.intent_monitor` | **yes** | scripts: scripts/auto_retrain_intent.py | delete candidate |
| `core.city.point_system` | **yes** | 1 test file(s) | delete candidate (update/delete its tests first) |
| `core.city.task_router` | **yes** | none | delete candidate |
| `core.city.evolution_audit` | **yes** | 1 test file(s) | delete candidate (update/delete its tests first) |
| `core.inference.model_router` | **yes** | 1 test file(s) | delete candidate (update/delete its tests first) |
| `core.inference.provider_registry` | **yes** | 1 test file(s) | delete candidate (update/delete its tests first) |
| `core.inference.district_llm` | **yes** | none | delete candidate |
| `core.api.auth` | **yes** | none | delete candidate |
| `core.api_manager` | **yes** | none | delete candidate |
| `core.communications.hub` | **yes** | none | delete candidate |
| `core.experiments.ab_testing` | **yes** | none | delete candidate |
| `core.sandbox.skill_sandbox` | **yes** | 1 test file(s) | delete candidate (update/delete its tests first) |
| `core.sandbox.wasm_runner` | **yes** | none | delete candidate |

## All unreachable `core/` modules by package (candidates only)

### `core.research_engine` — 125 module(s), 0 referenced by tests
**LOW CONFIDENCE — do not treat as dead.** This vendored engine has its own plugin loaders (`llm/providers/auto_discovery.py:118`, `security/module_whitelist.py:238` call `importlib.import_module` on names built at runtime), so its search engines/providers/exporters are probably loaded by name and only *look* unreachable to static analysis. Needs a runtime check (or owner decision on whether this subsystem is used at all) before anything here is considered.

`advanced_search_system.answer_decoding`, `advanced_search_system.filters.journal_reputation_filter`, `advanced_search_system.questions.followup.llm_followup_question`, `advanced_search_system.repositories`, `advanced_search_system.strategies.direct_search_strategy`, `advanced_search_system.strategies.improved_evidence_based_strategy`, `advanced_search_system.strategies.llm_driven_modular_strategy`, `advanced_search_system.tools.fetch_content_tool`, `api.benchmark_functions`, `config.core_config_adapter`, `config.default_settings.database_settings`, `database.migrations`, `database.migrations.env`, `database.migrations.versions`, `database.migrations.versions.0001_initial_schema`, `database.migrations.versions.0002_add_task_progress_columns`, `database.migrations.versions.0003_add_research_indexes`, `database.migrations.versions.0004_migrate_legacy_app_settings`, `database.migrations.versions.0005_add_resource_document_id`, `database.migrations.versions.0006_journal_quality_system`, `database.migrations.versions.0007_backfill_missing_indexes`, `database.migrations.versions.0008_fix_research_strategy_fk`, `database.migrations.versions.0009_default_fetch_mode_summary`, `database.models.user_base`, `database.queue_service`, `database.temp_auth`, `error_handling`, `error_handling.error_reporter`, `error_handling.openai_compat_errors`, `error_handling.report_generator`, `exceptions`, `exporters`, `exporters.base`, `exporters.latex_exporter`, `exporters.odt_exporter`, `exporters.pdf_exporter`, `exporters.quarto_exporter`, `exporters.registry`, `exporters.ris_exporter`, `followup_research`, `followup_research.models`, `followup_research.routes`, `followup_research.service`, `journal_quality`, `journal_quality.data_sources`, `journal_quality.data_sources._openalex_common`, `journal_quality.data_sources.base`, `journal_quality.data_sources.doaj`, `journal_quality.data_sources.institutions`, `journal_quality.data_sources.jabref`, `journal_quality.data_sources.openalex`, `journal_quality.data_sources.predatory`, `journal_quality.db`, `journal_quality.downloader`, `journal_quality.models`, `journal_quality.scoring`, `library.download_management.database_init`, `llm.providers.implementations.deepseek`, `llm.providers.implementations.ionos`, `llm.providers.implementations.xai`, `metrics.pricing`, `metrics.pricing.cost_calculator`, `metrics.pricing.pricing_cache`, `metrics.pricing.pricing_fetcher`, `news.core.card_factory`, `news.core.card_storage`, `news.core.news_analyzer`, `news.core.relevance_service`, `news.core.storage_manager`, `news.flask_api`, `news.preference_manager.base_preference`, `news.preference_manager.in_memory_preference`, `news.preference_manager.storage`, `news.rating_system.base_rater`, `news.rating_system.storage`, `news.recommender.base_recommender`, `news.recommender.topic_based`, `news.utils`, `news.utils.headline_generator`, `news.utils.topic_generator`, `news.web`, `security.url_builder`, `storage`, `storage.base`, `storage.database`, `storage.database_with_file_backup`, `storage.factory`, `storage.file`, `text_optimization`, `text_optimization.citation_formatter`, `utilities.es_utils`, `utilities.formatting`, `utilities.log_utils`, `utilities.setup_utils`, `web_search_engines.default_search_engines`, `web_search_engines.engines.meta_search_engine`, `web_search_engines.engines.search_engine_arxiv`, `web_search_engines.engines.search_engine_brave`, `web_search_engines.engines.search_engine_ddg`, `web_search_engines.engines.search_engine_elasticsearch`, `web_search_engines.engines.search_engine_exa`, `web_search_engines.engines.search_engine_github`, `web_search_engines.engines.search_engine_google_pse`, `web_search_engines.engines.search_engine_guardian`, `web_search_engines.engines.search_engine_gutenberg`, `web_search_engines.engines.search_engine_mojeek`, `web_search_engines.engines.search_engine_nasa_ads`, `web_search_engines.engines.search_engine_openalex`, `web_search_engines.engines.search_engine_openlibrary`, `web_search_engines.engines.search_engine_paperless`, `web_search_engines.engines.search_engine_pubchem`, `web_search_engines.engines.search_engine_pubmed`, `web_search_engines.engines.search_engine_scaleserp`, `web_search_engines.engines.search_engine_searxng`, `web_search_engines.engines.search_engine_semantic_scholar`, `web_search_engines.engines.search_engine_serpapi`, `web_search_engines.engines.search_engine_serper`, `web_search_engines.engines.search_engine_stackexchange`, `web_search_engines.engines.search_engine_tavily`, `web_search_engines.engines.search_engine_wayback`, `web_search_engines.engines.search_engine_wikinews`, `web_search_engines.engines.search_engine_wikipedia`, `web_search_engines.engines.search_engine_zenodo`, `web_search_engines.rate_limiting.__main__`, `web_search_engines.rate_limiting.cli`

### `core.coding_assistant` — 80 module(s), 0 referenced by tests
`acp.acp_agent_loop`, `acp.acp_logger`, `acp.commands`, `acp.commands.registry`, `acp.entrypoint`, `acp.exceptions`, `acp.session`, `acp.tools.base`, `acp.tools.builtins.bash`, `acp.tools.builtins.grep`, `acp.tools.builtins.read_file`, `acp.tools.builtins.search_replace`, `acp.tools.builtins.skill`, `acp.tools.builtins.task`, `acp.tools.builtins.todo`, `acp.tools.builtins.web_fetch`, `acp.tools.builtins.web_search`, `acp.tools.builtins.write_file`, `acp.tools.session_update`, `acp.utils`, `cli.autocompletion.base`, `cli.autocompletion.path_completion`, `cli.autocompletion.slash_command`, `cli.cli`, `cli.clipboard`, `cli.commands`, `cli.entrypoint`, `cli.history_manager`, `cli.narrator_manager`, `cli.narrator_manager.narrator_manager`, `cli.narrator_manager.narrator_manager_port`, `cli.narrator_manager.telemetry`, `cli.profiler`, `cli.stderr_guard`, `cli.turn_summary`, `cli.turn_summary.noop`, `cli.turn_summary.port`, `cli.turn_summary.tracker`, `cli.turn_summary.utils`, `cli.voice_manager`, `cli.voice_manager.telemetry`, `cli.voice_manager.voice_manager`, `cli.voice_manager.voice_manager_port`, `core.audio_player`, `core.audio_player.audio_player`, `core.audio_player.audio_player_port`, `core.audio_player.utils`, `core.audio_recorder`, `core.audio_recorder.audio_recorder`, `core.audio_recorder.audio_recorder_port`, `core.auth`, `core.auth.crypto`, `core.autocompletion.completers`, `core.autocompletion.fuzzy`, `core.autocompletion.path_prompt`, `core.autocompletion.path_prompt_adapter`, `core.log_reader`, `core.loop`, `core.session.resume_sessions`, `core.session.saved_sessions`, `core.tools.arity`, `core.tools.builtins.ask_user_question`, `core.tools.builtins.bash`, `core.tools.builtins.exit_plan_mode`, `core.tools.builtins.grep`, `core.tools.builtins.read_file`, `core.tools.builtins.skill`, `core.tools.builtins.task`, `core.tools.builtins.todo`, `core.tools.builtins.webfetch`, `core.tools.builtins.websearch`, `core.tools.builtins.write_file`, `core.tools.mcp_settings`, `core.transcribe`, `core.transcribe.factory`, `core.transcribe.transcribe_client_port`, `core.tts`, `core.tts.factory`, `core.tts.tts_client_port`, `setup.trusted_folders.trust_folder_dialog`

### `core.trading` — 25 module(s), 0 referenced by tests
`agents.analysts.social_media_analyst`, `cli.announcements`, `cli.config`, `cli.main`, `cli.models`, `cli.stats_handler`, `cli.utils`, `crypto_trading`, `tests`, `tests.conftest`, `tests.test_api_key_env`, `tests.test_capabilities`, `tests.test_checkpoint_resume`, `tests.test_dataflows_config`, `tests.test_deepseek_reasoning`, `tests.test_env_overrides`, `tests.test_google_api_key`, `tests.test_memory_log`, `tests.test_minimax`, `tests.test_model_validation`, `tests.test_ollama_base_url`, `tests.test_safe_ticker_component`, `tests.test_signal_processing`, `tests.test_structured_agents`, `tests.test_ticker_symbol_handling`

### `core.benchmark` — 20 module(s), 0 referenced by tests
`core.benchmark`, `benchmark_runner`, `benchmark_task`, `isolation`, `report`, `tasks`, `tasks.t01_long_term_memory`, `tasks.t02_context_retention`, `tasks.t03_goal_persistence`, `tasks.t04_multi_step_planning`, `tasks.t05_replanning`, `tasks.t06_proactive_cognition`, `tasks.t07_epistemic_uncertainty`, `tasks.t08_owner_correction_learning`, `tasks.t09_tool_execution`, `tasks.t10_tool_failure_recovery`, `tasks.t11_permission_safety`, `tasks.t12_provider_fallback`, `tasks.t13_autonomous_task_completion`, `tasks.t14_cross_session_continuity`

### `core.training` — 13 module(s), 2 referenced by tests
`benchmarks.voice_engine_benchmark`†, `openmythos.data_prep`, `openmythos.forward`, `openmythos.train`, `openmythos.vendor.examples.moda_example`, `openmythos.vendor.examples.variants_example`, `openmythos.vendor.open_mythos`, `openmythos.vendor.open_mythos.main`, `openmythos.vendor.open_mythos.moda`, `openmythos.vendor.open_mythos.tokenizer`, `openmythos.vendor.open_mythos.variants`, `openmythos.vendor.training.3b_fine_web_edu`, `weekly_scheduler`†

### `core.mining` — 8 module(s), 0 referenced by tests
`_constants`, `_install`, `_miner_loop_main`, `_mps_miner_loop_main`, `_pearl_subprocess`, `apple_mps_pearl`, `cpu_pearl`, `vllm_pearl`

### `core.engine` — 7 module(s), 2 referenced by tests
`agents`, `agents.roles`, `agents.subagent_runner`, `oauth.refresh_scheduler`†, `oauth.server`†, `token_juice`, `token_juice.compressor`

### `core.city` — 6 module(s), 2 referenced by tests
`evolution_audit`†, `intent_bert`, `intent_monitor`, `intent_qwen3_8b`, `point_system`†, `task_router`

### `core.scraper` — 5 module(s), 0 referenced by tests
`cli`, `core._shell_signatures`, `core.ai`, `core.shell`, `core.utils._shell`

### `core.voice` — 5 module(s), 5 referenced by tests
`effects`†, `elevenlabs_tts`†, `engines.supertonic_engine`†, `streamer`†, `voice_personality`†

### `core.cloud` — 3 module(s), 1 referenced by tests
`failover`, `heartbeat`†, `remote_sync`

### `core.control` — 3 module(s), 2 referenced by tests
`legion_wake`†, `security.node_router`, `wake_on_lan`†

### `core.inference` — 3 module(s), 2 referenced by tests
`district_llm`, `model_router`†, `provider_registry`†

### `core.brain` — 2 module(s), 0 referenced by tests
`router`, `self_evolve`

### `core.communications` — 2 module(s), 0 referenced by tests
`core.communications`, `hub`

### `core.experiments` — 2 module(s), 0 referenced by tests
`core.experiments`, `ab_testing`

### `core.integrations` — 2 module(s), 0 referenced by tests
`core.integrations`, `gmail_auth`

### `core.mcp` — 2 module(s), 2 referenced by tests
`core.mcp`†, `client`†

### `core.memory` — 2 module(s), 2 referenced by tests
`external_mirror`†, `vector_index_gate`†

### `core.models` — 2 module(s), 0 referenced by tests
`core.models`, `health_models`

### `core.sandbox` — 2 module(s), 1 referenced by tests
`skill_sandbox`†, `wasm_runner`

### `core.security` — 2 module(s), 1 referenced by tests
`secrets_providers`, `workspace_audit`†

### `core.services` — 2 module(s), 0 referenced by tests
`orchestrator.main`, `service_template`

### `core.ui` — 2 module(s), 0 referenced by tests
`chat`, `websocket_broadcaster`

### `core.utils` — 2 module(s), 0 referenced by tests
`core.utils`, `market_hours`

### `core.video` — 2 module(s), 0 referenced by tests
`hyperframes_sidecar`, `studio_server`

### `core.api` — 1 module(s), 0 referenced by tests
`auth`

### `core.api_manager` — 1 module(s), 0 referenced by tests
`core.api_manager`

### `core.errors` — 1 module(s), 1 referenced by tests
`core.errors`†

### `core.jcode` — 1 module(s), 0 referenced by tests
`semantic_cache`

### `core.loop` — 1 module(s), 0 referenced by tests
`planner`

### `core.repo_hygiene` — 1 module(s), 1 referenced by tests
`core.repo_hygiene`†

### `core.resilience` — 1 module(s), 0 referenced by tests
`hot_failover_api`

### `core.scheduler` — 1 module(s), 0 referenced by tests
`tools`

### `core.sensing` — 1 module(s), 0 referenced by tests
`sound_classifier`

† = referenced by at least one test file (deleting the module means deleting/repointing those tests).

## Required checks before any deletion (proposed process)
1. Owner approves per package, not per file.
2. For each package: `git grep -w <module leaf>` across `*.py *.yaml *.json *.bat *.ps1` (non-test) must be empty, and `pytest -k <leaf>` reviewed.
3. Run `scripts/check_first_party_imports.py` (added in Phase 1) and the full suite before/after; compare to the Task 90 baseline (5,012 / 13 / 36).
4. Delete in small commits per package so each is individually revertable.
5. Keep `core/coding_assistant`, `core/research_engine`, `core/trading`, `core/benchmark`, `core/training` for last — large, self-contained subsystems, likely deliberate standalone products (some carry their own `tests/`); treat as an ownership question, not cleanup.

## Not verified
- Runtime-only loading (config/DB-driven paths), and modules loaded by external processes (Termux `phone_node`, Cloudflare workers, `frontend/`).
- That the ~338 unreachable `core/` modules are all *safe*; only the named ones above were individually cross-checked by text search.
