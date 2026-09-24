# Phase 4.3 — Permission-tier coverage report (2026-09-24)

Scope: `DISTRICT_TASK_MAP` keys and `config/agent_manifest.yaml` capabilities that the real `PermissionGateway.classify()` returns **UNKNOWN** for (blocked, fail-closed since RR-1). **No tiers were changed — proposals only, awaiting owner approval.**

## Counts (measured with the real classifier)
- `DISTRICT_TASK_MAP`: 659 keys → 590 GREEN / 36 YELLOW / 32 RED / **1 UNKNOWN** (`research_papers`).
- Manifest capabilities: 524 distinct → 182 GREEN / 18 YELLOW / 8 RED / **316 UNKNOWN**.

## `research_papers` (map) — no change proposed
Deliberately UNKNOWN: it is a classifier alias folded onto the authorized `search_arxiv` by `core/api/routers/commands.py` (`_PAPER_RETRIEVAL_ALIASES`) and `governor._TASK_IDENTITY_ALIASES`. Adding a tier would create a second entry path for the same action.

## Manifest capabilities — how to read the 316
Most manifest capabilities are **routing labels** (nouns like `budgeting`, `tracking`, `patterns`), not `task['type']` values, so they never reach the gateway as an action. Blocking them if they ever did is the correct fail-closed default. Only **action-shaped** names need a tier: 134 of the 316 are action-shaped and listed below with a proposed tier. The remaining 182 are labels — **no tier proposed**.

### Proposed RED (18)
| capability | declared by | rationale |
|---|---|---|
| `autonomous_chaining` | governance/autopilot | chains autonomous actions |
| `autopilot_trigger` | governance/autopilot | starts autonomous action chains |
| `create_and_upload` | content/video_pipeline | generates and publishes |
| `cross_machine` | governance/federation_agent | acts on other machines |
| `delete_client` | agency/client_manager | destructive, client data |
| `escalate` | security/alert_manager | pages the owner / external |
| `execute_playbook` | security/incident_playbook_runner | runs incident-response actions |
| `execute_scheduled_uploads` | content/uploader | publishes queued content |
| `github` | coding/git_bot | external repo writes |
| `hot_reload` | security/detection_rules_engine | reloads live rules/code |
| `prune_retention` | security/log_aggregator | deletes retained logs |
| `rollback` | security/incident_playbook_runner | reverts system state |
| `run_pending` | content/content_scheduler | runs queued (possibly publishing) jobs |
| `schedule_upload` | content/uploader | queues a public publish |
| `upload_instagram` | content/uploader | publishes to a public platform |
| `upload_tiktok` | content/uploader | publishes to a public platform |
| `upload_twitter` | content/uploader | publishes to a public platform |
| `upload_youtube` | content/uploader | publishes to a public platform |

### Proposed YELLOW (48)
| capability | declared by | rationale |
|---|---|---|
| `acknowledge` | security/alert_manager | state change |
| `acknowledge_alert` | agency/performance_tracker_agency | state change |
| `add_background_music` | content/video_merger | local media edit |
| `add_client` | agency/client_manager | local write |
| `add_subtitles` | content/video_merger | local media edit |
| `add_transitions` | content/video_merger | local media edit |
| `adjust_voice_speed` | content/voice_generator | local media edit |
| `blocklist` | security/network_monitor | changes blocklist state |
| `build_storyboard` | content/asset_video_pipeline | local generation |
| `capture_url` | content/website_to_video | network fetch |
| `clone_voice` | content/voice_generator | creates a voice profile from audio |
| `create_note` | memory_curator/consolidation_bot | local write |
| `dead_code_cleanup` | coding/refactor_cleaner | edits source |
| `detection_rule` | security/threat_detection_engineer | changes detection rules |
| `download_dataset` | karpathy_lab/data_prep | network download + disk |
| `export_report` | interview_prep/report_generator | writes a file |
| `extract_audio` | content/video_merger | local media edit |
| `fetch_trending` | content/youtube_trend_scout | network fetch |
| `generate_batch` | content/voice_generator | bulk generation (cost) |
| `generate_captions` | content/caption_generator | local media generation |
| `generate_config` | karpathy_lab/architecture_builder | writes config files |
| `generate_highlight_captions` | content/caption_generator | local media generation |
| `generate_in_my_voice` | content/voice_generator | local media generation |
| `generate_subtitles` | content/caption_generator | local media generation |
| `generate_tags` | content/video_generator | local generation |
| `generate_voice` | content/voice_generator | local media generation |
| `link_notes` | learning/note_organizer | local write |
| `log_step` | karpathy_lab/karpathy_progress_tracker | local write |
| `memory_store` | memory_curator/consolidation_bot | local write |
| `merge_clips` | content/video_merger | local media edit |
| `network_scan` | security/network_monitor | active network probe |
| `organize_notes` | learning/note_organizer | local write |
| `port_scan` | security/network_monitor | active network probe |
| `preprocess_data` | karpathy_lab/data_prep | local write |
| `process_event` | security/siem_pipeline | feeds SIEM state |
| `refactor_clean` | coding/refactor_cleaner | edits source |
| `remove_metric` | agency/performance_tracker_agency | local delete of metric |
| `save_note` | memory_curator/consolidation_bot | local write |
| `scan_artifact` | security/skill_spector | scan of a file |
| `scan_vulnerabilities` | coding/security_reviewer | active scan |
| `start_run` | karpathy_lab/karpathy_progress_tracker | starts a training run (GPU) |
| `title_thumbnail` | content/video_generator | local generation |
| `tokenize_data` | karpathy_lab/data_prep | local write |
| `track_metric` | agency/performance_tracker_agency | local write |
| `translate_captions` | content/caption_generator | local media generation |
| `trim_video` | content/video_merger | local media edit |
| `update_client` | agency/client_manager | local write |
| `yt_dlp` | learning/video_ingestor | network download + disk |

### Proposed GREEN (68)
| capability | declared by | rationale |
|---|---|---|
| `active_alerts` | agency/performance_tracker_agency | read-only / analysis |
| `alert_anomaly` | agency/performance_tracker_agency | read-only / analysis |
| `analyze_competitor` | content/youtube_trend_scout | read-only / analysis |
| `analyze_feedback` | interview_prep/feedback_analyst | read-only / analysis |
| `analyze_financials` | investment/fundamentals_bot | read-only / analysis |
| `analyze_gaps` | skills/gap_analyst | read-only / analysis |
| `ast_analysis` | coding/code_reviewer | read-only / analysis |
| `calculate_indicators` | investment/technical_bot | read-only / analysis |
| `check_pep8` | coding/python_reviewer | read-only / analysis |
| `check_valuation` | investment/fundamentals_bot | read-only / analysis |
| `client_summary` | agency/client_manager | read-only / analysis |
| `code_review` | coding/code_reviewer, coding/git_bot | read-only / analysis |
| `compare_to_sector` | investment/fundamentals_bot | read-only / analysis |
| `deep_code_review` | coding/addy_code_reviewer | read-only / analysis |
| `dependency_trace` | coding/code_explorer | read-only / analysis |
| `design_architecture` | karpathy_lab/architecture_builder | read-only / analysis |
| `detect_anomalies` | predictive_analytics/strategy_recommender | read-only / analysis |
| `detect_patterns` | investment/technical_bot | read-only / analysis |
| `district_report` | documentation/doc_generator | read-only / analysis |
| `dividend_analysis` | investment/fundamentals_bot | read-only / analysis |
| `estimate_compute` | karpathy_lab/architecture_builder | read-only / analysis |
| `evaluate` | security/detection_rules_engine | read-only / analysis |
| `extract_action_items` | calls/transcription_bot | read-only / analysis |
| `extract_concepts` | learning/concept_extractor | read-only / analysis |
| `generate_response` | calls/voice_responder | read-only / analysis |
| `get_at_risk_clients` | agency/client_manager | read-only / analysis |
| `get_client` | agency/client_manager | read-only / analysis |
| `get_comparison` | agency/performance_tracker_agency | read-only / analysis |
| `get_metric_summary` | agency/performance_tracker_agency | read-only / analysis |
| `get_price_data` | investment/technical_bot | read-only / analysis |
| `get_progress` | karpathy_lab/karpathy_progress_tracker | read-only / analysis |
| `get_top_clients` | agency/client_manager | read-only / analysis |
| `get_trend` | agency/performance_tracker_agency | read-only / analysis |
| `get_voices` | content/voice_generator | read-only / analysis |
| `health_check` | health/health_advisor | read-only / analysis |
| `hedge_status` | investment/hedgebot_agent | read-only / analysis |
| `identify_improvements` | interview_prep/feedback_analyst | read-only / analysis |
| `job_history` | content/video_pipeline | read-only / analysis |
| `job_queue` | content/video_pipeline | read-only / analysis |
| `job_status` | content/video_pipeline | read-only / analysis |
| `list_alerts` | security/alert_manager | read-only / analysis |
| `list_clients` | agency/client_manager | read-only / analysis |
| `list_incidents` | security/incident_playbook_runner | read-only / analysis |
| `list_models` | content/media_studio_agent | read-only / analysis |
| `list_rules` | security/detection_rules_engine | read-only / analysis |
| `list_skills` | investment/finagent_agent | read-only / analysis |
| `log_query` | security/log_aggregator | read-only / analysis |
| `match_event` | security/detection_rules_engine | read-only / analysis |
| `memory_query` | memory_curator/consolidation_bot | read-only / analysis |
| `obra_review` | coding/obra_code_reviewer | read-only / analysis |
| `order_summary` | investment/execution_engine | read-only / analysis |
| `portfolio_summary` | investment/finagent_agent | read-only / analysis |
| `prioritize_gaps` | skills/gap_analyst | read-only / analysis |
| `profile_competitor` | marketing/competitor_intel_agent | read-only / analysis |
| `progress_report` | interview_prep/report_generator | read-only / analysis |
| `recommend` | predictive_analytics/strategy_recommender | read-only / analysis |
| `review_security` | coding/security_reviewer | read-only / analysis |
| `root_cause` | coding/bug_hunter | read-only / analysis |
| `security_code_review` | coding/security_reviewer | read-only / analysis |
| `session_report` | interview_prep/report_generator | read-only / analysis |
| `siem_alerts` | security/siem_pipeline | read-only / analysis |
| `siem_stats` | security/siem_pipeline | read-only / analysis |
| `suggest_learning_path` | skills/gap_analyst | read-only / analysis |
| `suggest_prerequisites` | learning/concept_extractor | read-only / analysis |
| `summarize_transcript` | calls/transcription_bot | read-only / analysis |
| `text_to_ssml` | content/voice_generator | read-only / analysis |
| `transcribe_audio` | calls/transcription_bot | read-only / analysis |
| `upload_history` | content/uploader | read-only / analysis |

### Labels — no tier proposed (fail-closed stays)

`academic`, `ads_orchestration`, `agency`, `aggregation`, `ai_research`, `alert_management`, `alerts`, `amazon_ads_audit`, `analysis`, `anomaly_detection`, `architecture`, `assessment`, `audit`, `audit_consent_mode`, `behavior`, `benchmarking`, `biometrics`, `bottleneck_analysis`, `briefing`, `budgeting`, `calls`, `camera`, `cli_adapter`, `clustering`, `coaching`, `code-intel`, `code_conductor`, `code_exploration`, `coding`, `communication`, `companies`, `company_specific`, `competitor_intel`, `components`, `connection_rate`, `consolidation`, `contacts`, `content`, `content_creation`, `context_compression`, `courses`, `crm`, `data_pipelines`, `database-optimizer`, `deadlines`, `deal_strategy`, `debugging`, `deliberation`, `demand_analysis`, `design`, `detection`, `developer_experience`, `diagrams`, `documentation`, `dx`, `email_client`, `email_intelligence`, `email_parsing`, `enforcement`, `english`, `exercise`, `expenses`, `financial_analysis`, `fpa_analysis`, `frontend_developer`, `gaps`, `geo`, `geopolitics`, `gui`, `habits`, `health_recommendations`, `high_stakes`, `ideas`, `image_generation`, `image_prompts`, `incident_response`, `india`, `insights`, `intelligence`, `interview`, `investment`, `journaling`, `journey_maps`, `languages`, `learning`, `lightrag`, `log_aggregation`, `logging`, `mapping`, `marketing`, `markets`, `milestones`, `minimal-change`, `mlops`, `mock`, `modeling`, `monitoring`, `multi_platform_ads`, `nlp`, `obsidian`, `onboarding`, `opportunities`, `orchestration`, `outbound`, `papers`, `parsing`, `patterns`, `performance`, `performance_optimization`, `personas`, `pii`, `planning`, `playwright`, `practice`, `privacy`, `problems`, `processes`, `product_roadmap`, `productivity`, `projects`, `pytest`, `quant_research`, `ranking`, `rapid-prototype`, `reddit`, `reflection`, `registry`, `relationships`, `reporting`, `repurposing`, `respond_to_audio`, `rfp`, `rice_scoring`, `rss`, `scanning`, `scheduling`, `scraping`, `screening`, `scripts`, `secrets_redaction`, `sentiment`, `side_hustle`, `signals`, `skills`, `sms`, `soc2`, `social`, `social_media_strategy`, `social_mining`, `stable_diffusion`, `startups`, `stealth`, `stealth_scout`, `stocks`, `strategic_gaps`, `strategy`, `summarisation`, `summarize_notes`, `summary`, `synthesis`, `tax`, `technical_writing`, `testing`, `text_to_speech`, `track_engagement`, `track_progress`, `tracking`, `transcribe_live`, `trends`, `upi`, `validation`, `venture`, `voice`, `voting`, `web_search`, `win_strategy`, `window_management`, `writing`, `xray_brief`, `youtube`, `youtube_competitor`, `youtube_trending`

## Caveats
- Tier proposals are judgment calls from the capability name and declaring agent, not from reading each handler; the RED list in particular should be confirmed by you before any `core/config.py` edit. Several (`run_pending`, `blocklist`, `escalate`, `github`) depend on what the agent actually does.
- The tier lists are frozen by `tests/test_v1_trust_t3_permission_vocabulary.py` (`_FROZEN_RED/_FROZEN_YELLOW`); any approved change must update that guard in the same commit.
- Generated by running `PermissionGateway().classify()` over `DISTRICT_TASK_MAP` and every capability in `config/agent_manifest.yaml`.
