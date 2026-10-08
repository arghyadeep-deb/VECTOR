import os
import sys
from pathlib import Path

# Direct-script guard (same fix as core/mcp_server.py): "python core/config.py"
# auto-prepends core/ to sys.path[0]; core/email/ then shadows the stdlib
# `email` package the moment pydantic's plugin loader does `import email`
# via importlib.metadata, crashing the self-test with a circular ImportError.
# Strip core/ and ensure the repo root is present, before any other import.
_this_dir = str(Path(__file__).resolve().parent)
sys.path[:] = [p for p in sys.path if p != _this_dir]
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from loguru import logger
from typing import Optional
from pydantic import BaseModel, SecretStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Keyring-first secret lookup (env checked first, then OS keyring) for the
# handful of top-level CONFIG password entries below that aren't modeled as
# pydantic SecretStr fields. core.security.secrets_manager only depends on
# core.runtime_paths, so this does not create a circular import with core.config.
from core.security.secrets_manager import get_secret as _get_secret

_BASE_DIR = Path(__file__).parent.parent


# ── Sub-models (each validated at startup) ────────────────────────────────────

class ModelsConfig(BaseModel):
    ambient: str = "vector-ambient"
    focus: str = "vector-focus"
    multilingual: str = "vector-multilingual"
    reasoning: str = "vector-reasoning"
    coder: str = "vector-coder"
    deep: str = "vector-deep"
    chairman: str = "vector-chairman"
    embed: str = "nomic-embed-text"
    r1: str = "vector-r1"               # deepseek-r1:14b — chain-of-thought council member
    dev: str = "vector-dev"             # devstral:24b — code review + refactor specialist
    fast: str = "vector-fast"           # mistral-small3.1 — low-latency general fallback
    cloud_coder: str = "vector-dev"     # was phi4:latest — now devstral-based VECTOR model
    cloud_orchestrator: str = "vector-r1"  # was deepseek-r1:14b raw — now VECTOR custom
    vision: str = "qwen2.5vl:7b"       # GUI automation + screen understanding (dedicated vision model)


class ModelRouterConfig(BaseModel):
    conversation: str = "focus"
    multilingual: str = "multilingual"
    coding: str = "coder"
    code_review: str = "dev"
    council: str = "reasoning"
    chain_of_thought: str = "r1"
    fast_fallback: str = "fast"
    deep_analysis: str = "deep"
    private: str = "chairman"
    embedding: str = "embed"
    ambient_classify: str = "ambient"
    saas_build: str = "dev"
    orchestration: str = "r1"


class LoopConfig(BaseModel):
    observe_interval_sec: float = Field(0.5, ge=0.1, le=60.0)
    db_sync_hours: int = Field(24, ge=1, le=720)            # multi-DB mesh reconcile cadence
    command_poll_sec: float = Field(3.0, ge=0.5, le=60.0)   # remote command relay poll (Phase 4)
    reflect_hour: int = Field(2, ge=0, le=23)
    reflect_minute: int = Field(0, ge=0, le=59)
    # 2026-08-06 (loop-stall root-cause hunt, KNOWN_ISSUES #0): observe_tick
    # (15s) and think_tick (60s) already had asyncio.timeout coverage;
    # reflect_tick had none, despite calling out to DailyReviewer,
    # SelfImprovementCycle, ConsolidationBot, EvolutionEngine, etc. — any one
    # of those hanging would freeze the loop thread with no bound at all.
    # Generous because reflect legitimately does more work than a normal
    # tick (nightly cycle, not a 10s poll).
    reflect_tick_timeout_sec: float = Field(600.0, ge=30.0, le=3600.0)
    # Per-agent ceiling on governor.dispatch()'s `await agent.run(task)` —
    # the one call on the dispatch hot path with no timeout of its own
    # (previously relied entirely on the outer think_tick 60s budget, which
    # can't isolate WHICH agent/district hung, and doesn't apply at all to
    # dispatches made outside think_tick, e.g. from event fan-out). Kept
    # under the 60s think_tick budget so a hung agent is attributed by name
    # before the outer timeout would fire anyway. NOTE: this bounds the wait,
    # not the underlying call — a genuinely synchronous blocking call inside
    # agent.run() (no `await` point) cannot be cancelled by asyncio; see
    # governor.py's dispatch() comment.
    agent_dispatch_timeout_sec: float = Field(45.0, ge=5.0, le=300.0)


class PermissionConfig(BaseModel):
    green: list[str] = Field(default_factory=lambda: [
        "read_calendar", "play_music", "set_timer", "search_web",
        "take_screenshot", "check_weather", "check_attendance",
        "progress_goal", "kickstart_goal",
        "analyze_progress", "research_topic", "check_deadline", "review_goal",
        # concrete action types from think→act pipeline
        "git_status", "check_git", "recent_commits", "git_log",
        "daily_digest", "search_arxiv", "get_hn", "hackernews",
        # 2026-09-26: read-only single-page fetch + structured extraction (core/browser/page_extract.py): http/https
        # GET only, SSRF-guarded on every redirect hop, size/time limited, no cookies/login/forms/JS, output is data
        # (never executed or fed to a model there), page text is injection-scanned. Same class as search_web /
        # search_arxiv. NOTE for the independent review: this is a NEW GREEN entry (a tier addition, not a change).
        "web_extract",
        "check_fatigue", "consolidate", "daily_review", "reflect",
        "deadline_check", "progress",
        # VectorCode read-only actions
        "code_review_vc", "code_status", "read_code", "analyze_code",
        # VECTOR UI events — purely local dashboard side effects, no real-world impact
        "respond", "open_panel",
        "widget_open", "widget_close", "widget_show_location",
        "music_play", "music_pause", "music_next", "music_prev",
        # Hand Execution Engine — scheduled autonomous Hands with
        # requires_approval=False (hands/registry.py). GREEN = auto-execute,
        # no owner gate (matches each Hand's own requires_approval flag).
        "hand_researcher", "hand_collector", "hand_predictor",
        "hand_trader", "hand_lead", "hand_vault_sync",
        # R18-EQ (2026-09-10): "script" and "idea_validate" already had real
        # handlers (districts/content/script_generator.py::ScriptGenerator,
        # districts/startups/idea_validator.py::IdeaValidator) and real,
        # exact-match Governor routing (core/city/governor.py's
        # DISTRICT_TASK_MAP: "script" -> "content", "idea_validate" ->
        # "startups") but were never added to any permission tier — the
        # same "real capability, unclassified, therefore UNKNOWN, therefore
        # always blocked at the gateway" pattern this file's own Task
        # 58B/58C/58D remediations already fixed for other action_types.
        # Both are purely local (an LLM-drafted video script; an LLM-scored
        # startup-idea validation, both written only to in-memory/episodic
        # state) — no external communication, no financial transaction, no
        # irreversible side effect, matching this list's existing GREEN
        # content/research/analysis entries exactly.
        "script", "idea_validate",
        # R19 (2026-09-10): "schedule_post" already had a real handler
        # (districts/content/content_scheduler.py::ContentScheduler
        # .schedule_post()) and real, exact-match Governor routing
        # (DISTRICT_TASK_MAP: "schedule_post" -> "content") but was never
        # classified — same defect class as the script/idea_validate entry
        # above. Verified safe by direct source read: schedule_post() ONLY
        # creates a local PostJob row via PostJobTracker.create() (SQLite,
        # no network call) — it never publishes anything itself. The actual
        # external, irreversible publish is a SEPARATE method
        # (ContentScheduler.run_pending()) gated behind its OWN, separate,
        # already-RED "content_publish" action_type requiring real
        # PermissionGateway owner approval (fail-closed on gateway error) —
        # schedule_post's own dispatch path never reaches it. This entry
        # enables the R19 script -> schedule_post composition (real
        # structural data handoff: generate_script()'s real "content" field
        # becomes schedule_post()'s real "content" payload, not a
        # coincidental same-named-but-unused pass-through).
        "schedule_post",
        # RR-1.5 (2026-09-15, VECTOR_TECHNICAL_KNOWLEDGE/
        # RR1_5_PERMISSION_VOCABULARY_REPORT.md): RR-1 unified owner
        # /command actions classify_chat_intent() recognizes onto this same
        # GREEN/YELLOW/RED/FORBIDDEN vocabulary — its own production
        # validation then exposed that most REAL, established district
        # task_types classify_chat_intent can name were never classified at
        # all (UNKNOWN -> correctly fail-closed-blocked). Of 19 such
        # task_types individually source-verified for this remediation,
        # only these 2 had a confirmed, exact, genuinely read-only real
        # implementation — the other 17 (including system_status, which has
        # NO implementation anywhere in the codebase under that name) are
        # deliberately left UNKNOWN: no exact capability-string match, a
        # confirmed stub, or insufficient evidence, per this task's own
        # "do not classify merely to remove UNKNOWN warnings" rule.
        # "list_districts": a dedicated, real, read-only endpoint
        # (core/api/routers/city.py) that enumerates Governor's own
        # internal district/agent registry — no mutation, no external call.
        # "test_feature": APITester.run()'s real default path
        # (districts/qa/api_tester.py) — a local-only HTTP self-diagnostic
        # loop hitting VECTOR's own /health,/status,/agents,/command
        # endpoints via httpx against its own base URL; writes only its own
        # episodic log/Obsidian report and its own HP, never touches an
        # external network or owner data.
        "list_districts", "test_feature",
        # 2026-09-24 (independent review finding -- HIGH, closing the
        # residual Codex found in the Governor.dispatch() authorization-
        # boundary work): Governor.dispatch()'s new fail-closed check only
        # gated FORBIDDEN/YELLOW/RED -- 627 of core/city/governor.py's 659
        # DISTRICT_TASK_MAP route keys were classified UNKNOWN (passes
        # through unchecked when Governor.dispatch() is called directly,
        # bypassing PermissionGateway.execute()'s own fail-closed UNKNOWN
        # handling). Every one of those 627 was traced to its real handler
        # code (exact `task_type ==`/`action ==` branch match, or a real
        # Swarm-style keyword-dispatch for districts like coding/ops/
        # content that route by TASK_ROLE_MAP score rather than exact
        # match) rather than classified by name alone -- several looked
        # dangerous by keyword but resolve to no real branch at all (e.g.
        # "bash_execute"/"run_command"/"credentials"/"api_keys"/"notify"
        # are present only in a `self.capabilities = [...]` list used for
        # agent SELECTION, never matched in the real `run()` if/elif
        # chain, and fall through to a safe default/error/status branch).
        # These GREEN additions are the ~581 routes confirmed read-only,
        # analysis/reporting/generation-for-review, purely informational,
        # or with no real backing handler at that exact string at all
        # (in which case GREEN is correct since nothing dangerous is
        # actually reachable under that name). The genuinely dangerous
        # ones (real trade execution, real shell/code-index writes, real
        # peer broadcast, real infra deploy/restart/backup) are classified
        # RED/YELLOW below instead -- see those lists' own 2026-09-24
        # comments.
        "ab_test", "ab_test_design", "ab_test_variant", "academic_research", "academic_search",
        "accessibility", "ad_image_generate", "ads_apple_audit", "ads_audit", "ads_bidding",
        "ads_budget", "ads_budget_alloc", "ads_competitor", "ads_competitor_research", "ads_copy",
        "ads_create", "ads_creative", "ads_creative_audit", "ads_dna", "ads_full_audit",
        "ads_generate", "ads_google_audit", "ads_keywords", "ads_landing", "ads_landing_analysis",
        "ads_linkedin_audit", "ads_math", "ads_meta", "ads_microsoft_audit", "ads_multi_audit",
        "ads_pdf_report", "ads_performance", "ads_photoshoot", "ads_plan", "ads_report",
        "ads_strategy", "ads_test", "ads_tiktok_audit", "ads_youtube_audit", "aeo",
        "agent_interview", "agentic_search", "ai_citation", "ai_news", "aircraft", "ais",
        "alpha_beta", "alpha_discovery", "alternative_invest", "amazon_ads", "amazon_audit",
        "ambient", "ambient_status", "analytics", "anomaly_prediction",
        "api_health", "api_keys", "api_reference", "api_review", "api_test", "apply_patch",
        "architect", "arxiv", "assamese", "asyncio_review", "attendance", "attribution_audit",
        "audit_log", "audit_search", "audit_tail", "audit_verify", "auto_chain", "auto_draft",
        "background_remove", "bash_execute", "behavior_detect", "behavior_pattern",
        "benchmark", "bengali", "black_scholes", "blast_radius", "blog", "bond_pricing",
        "bottleneck", "brain_summary", "brand_dna", "break_even", "broken_links", "budget",
        "budget_alert", "budget_check", "budget_record", "budget_status", "bug", "build_graph",
        "build_ontology", "cad", "call", "call_flow", "call_screen", "campaign_brief",
        "capi_check", "causal_query", "causal_simulate", "cctv", "check_inbox", "check_url",
        "chemistry", "chief", "citation_score", "classify_emergency", "classify_error",
        "cloud_safety", "cluster_problems", "cms_push_seo", "code", "code_accuracy_test",
        "code_hardcoded_check", "code_inject_check",
        "code_intelligence", "code_map", "code_path_check", "code_review_addy",
        "code_review_obra", "code_search", "code_secret_check", "code_ssrf_check",
        "code_vuln_check", "codebase_health", "cold_outreach", "comfyui_prompt",
        "communication_style", "competitive_analysis", "competitive_intelligence",
        "competitor_profile", "competitor_research", "competitor_spy", "compliance",
        "component", "compress_context", "consent_mode", "consistency_check", "contact",
        "content_creator", "content_schedule", "conversion_optimization", "conversion_rate",
        "coordinate", "corporate_finance", "cost_report", "council", "course",
        "covariance_matrix", "crawl", "create_video", "credentials", "credit_risk", "cro",
        "daily_video", "dashboard_build", "data_audit", "data_contract", "data_flow",
        "data_pipeline", "data_quality", "data_redact", "data_remediation", "data_viz",
        "db_optimize", "dcf", "dcf_analysis", "dead_code", "decision",
        "derivatives", "design_tokens", "detect_anomaly",
        "developer_advocate", "devops", "directive", "drawdown", "dx_audit", "econ_analysis",
        "editorial_calendar", "email", "email_brief", "email_search", "email_thread",
        "emergency", "emergency_alert", "endpoint_review", "epistemic_summary",
        "equity_research", "error_type", "escalate_emergency", "etl", "evening_brief",
        "events near", "evidence", "executive_brief", "experiment", "experiments",
        "explain_file", "explore_code", "factor_model", "fastapi_review", "fatigue",
        "federation", "feedback", "fetch_dynamic", "fetch_page", "fetch_stealth", "file_edit",
        "find", "find_papers", "find_symbol", "finrl_train", "fires", "fixed_income",
        "flights", "forecast", "fpa", "frontend", "frontline", "fundamental_analysis",
        "funnel", "funnel_diagnosis", "funnel_drop", "gdpr", "generate_changelog",
        "generate_docs", "generate_i2i", "generate_image", "generate_personas",
        "generate_report", "generate_video", "geo_optimize", "geo_optimizer", "geo_score",
        "geopolitics_analysis", "get_email", "github_ml", "global intel",
        "global summary", "gmail", "goal_summary", "google_ads", "google_ads_audit",
        "google_ads_copy", "google_ads_landing", "greeks_calc", "grep_code", "grep_search",
        "growth", "growth_status", "ha_status", "habit_analysis", "habit_status",
        "hand_disable", "hand_enable", "hand_list", "hand_run", "hand_status", "health",
        "hf_dataset", "hindi", "html_to_markdown", "hypothesis",
        "identify_habits", "image", "image_prompt", "impact_analysis",
        "index", "intel report", "internet outage",
        "investment_analysis", "investor_analysis", "japanese", "job_search", "journey_map",
        "karpathy", "keyword", "keyword_research", "kiit", "knowledge_links",
        "knowledge_query", "landing_page_analyze", "landing_page_optimize",
        "language_coach", "learn", "linkedin", "lip_sync", "list_emails", "literature_review",
        "llm_cost", "load_skill", "loop_status", "macro_analysis", "malware",
        "map_workflow", "maritime", "market_intelligence", "market_landscape",
        "market_research", "market_scan", "mastery", "mcp_stdio", "media_status", "memory",
        "message", "meta_ads", "meta_ads_audience", "meta_ads_audit", "meta_ads_creative",
        "meta_ads_performance", "metrics", "mine_social", "minimal_diff", "mitre_attack",
        "ml_audit", "ml_plan", "ml_research", "model_qa", "molecule", "money",
        "monitor_system", "monte_carlo", "morning_brief", "motivation", "multi_edit",
        "multiedit", "mvp", "nanogpt", "nasa firms", "new_email", "news", "news near",
        "newsletter", "north_star", "notify", "nudge", "onboard_repo", "opportunity_spot",
        "optimize", "optimize_content", "options_analysis", "order_history", "osint_collect",
        "outages", "outreach", "page_not_converting", "pagespeed", "paper", "paper_trade",
        "parse_email", "parse_html", "pep8_review", "performance_report", "persona",
        "physics", "pii_check", "pipeline", "portfolio_management",
        "portfolio_optimize", "ppc_calculator", "prd",
        "predict", "prediction_store", "privacy_check", "product_brief", "profile",
        "project", "proposal", "prototype", "provider_scan", "prune_context", "publish_post",
        "pubmed", "pydantic_review", "python_review", "qa_check", "qualify_lead",
        "quant_backtest", "quant_model", "rapid_prototype", "rate_check", "read_email",
        "read_file_tool", "reality_check", "recall", "recon satellite", "recover_session",
        "recruitment", "redact", "regime_detect",
        "relationship", "remove_bg", "repo_scan", "research", "research_news",
        "research_quick", "research_report", "resume",
        "review", "review_fastapi", "review_python", "rice_score", "risk_analysis",
        "roadmap", "roi", "run_command", "run_pending_posts", "run_simulation", "runbook",
        "sales", "satellites", "scaffold_component", "scan", "scan_prompt",
        "scenario_analysis", "schema_markup", "science", "scrape", "scrape_stealth",
        "scrape_url", "sd_prompt", "search", "search_replace", "sector_analysis", "security",
        "security_scan", "semantic_scholar", "semantic_search", "seo", "seo_analysis",
        "seo_audit", "seo_followup", "seo_geo", "seo_improve_page", "seo_investigate_drop",
        "seo_onboard", "seo_portfolio", "seo_portfolio_review", "seo_weekly_review",
        "session_persist", "session_repair", "sgtm_health", "shadow_account", "sharpe_ratio",
        "siem", "sigma_rule", "silent_failure", "simulate", "simulation_report",
        "skill_gap", "skill_map", "skill_run", "sleep", "slo", "slow_query", "social_media",
        "social_simulate", "solana_holdings", "sox", "spider_crawl", "ssrf_check",
        "stealth_scrape", "stealth_search", "stealth_snapshot", "strategic_gap",
        "strategy_recommend", "surveillance camera", "swallowed_error", "symbol_lookup",
        "synthesize_feedback", "taint_check", "tdd", "technical_analysis", "test_analysis",
        "test_coverage", "threat", "threat_detection", "time_series", "title_card",
        "todo_add", "todo_list", "token_price", "token_search", "token_usage",
        "tool_evaluate", "track aircraft", "track plane", "track ship", "track_experiment",
        "trading_analysis", "train_model", "transcribe", "trending", "ttfhw", "tutorial",
        "twitter", "type_hints_review", "ui_design", "upload_video", "upscale", "uptime",
        "url_inspect", "url_inspection", "ux_research", "valuation",
        "valuation_model", "var_calc", "vc_context", "vc_context_search", "vc_flow",
        "vc_graph_circular", "vc_graph_query", "vc_health", "vc_impact",
        "vc_projects", "vc_search", "vc_status", "vc_symbol", "vc_symbols", "vc_visualize",
        "vectorcode", "vectorcode_comms", "venture_pipeline", "verify_output",
        "vessels", "video", "viral_loop", "vote", "vt_export", "vt_research", "vt_skills",
        "vt_swarm", "war zone", "wcag", "web_scrape", "weekly_summary",
        "what_if", "whatsapp", "wildfire", "workflow_optimize", "write_code",
        "write_file_tool", "write_tests", "yield_curve", "youtube_transcript",
        "zettelkasten", "zk",
        # 2026-09-30 (owner-requested skills section for VECTOR): SkillBuilder writes a
        # real SKILL.md into data/vector_skills/<slug>/ from caller-supplied, already-
        # stable pattern records (deterministic threshold re-check + formatting only, no
        # LLM call, no path traversal -- slug is derived via a bounded a-z0-9/hyphen
        # slugify). Same GREEN classification already given to ZKSteward's zettelkasten/zk
        # actions above, which write real files into the owner's own vault -- this agent's
        # writes are strictly less invasive (a new, dedicated, isolated directory only).
        "learned_pattern_brief", "learned_pattern_build",
        # 2026-09-24: transcription omissions caught by re-running the
        # zero-remaining-UNKNOWN verification after the additions above --
        # same classification reasoning (read-only/analysis/local, no real
        # dangerous handler at that exact string), just missed copying the
        # first time.
        "execution_flow", "cache_tracker", "kv_cache", "schedule_task",
        "session_recovery", "smart_fetch", "batch_scrape", "finance",
        "backtest_strategy", "conflicts", "content_generate", "voice_respond",
        "subconscious", "subconscious_loop", "deep_research", "deep_dive",
        "placement", "variance", "nexus", "context_compress", "cleanup",
        # 2026-09-25 (owner-approved tier proposals, VECTOR_TECHNICAL_KNOWLEDGE/PHASE4_TIER_COVERAGE_REPORT.md): manifest
        # capabilities that were UNKNOWN (blocked). Each handler was traced and is read-only or analysis-only (reads, local
        # computation, local-model prompts, in-memory agent lessons). Mutating handlers are YELLOW, including alert_anomaly,
        # which rewrites persisted thresholds and awards HP.
        "active_alerts", "analyze_competitor", "analyze_financials", "analyze_gaps",
        "ast_analysis", "calculate_indicators", "check_pep8", "check_valuation", "client_summary", "code_review",
        "compare_to_sector", "deep_code_review", "dependency_trace", "design_architecture", "detect_anomalies",
        "detect_patterns", "dividend_analysis", "estimate_compute", "evaluate", "extract_action_items",
        "extract_concepts", "get_at_risk_clients", "get_client", "get_comparison", "get_metric_summary",
        "get_price_data", "get_progress", "get_top_clients", "get_trend", "get_voices", "hedge_status",
        "identify_improvements", "job_history", "job_queue", "job_status", "list_alerts", "list_clients",
        "list_incidents", "list_models", "list_rules", "list_skills", "log_query", "match_event", "memory_query",
        "obra_review", "order_summary", "portfolio_summary", "prioritize_gaps", "profile_competitor",
        "progress_report", "recommend", "review_security", "root_cause", "security_code_review", "session_report",
        "siem_alerts", "siem_stats", "suggest_learning_path", "suggest_prerequisites", "summarize_transcript",
        "text_to_ssml", "transcribe_audio", "upload_history",
        # 2026-09-25 (Governor untiered-name closure): read-only / local-analysis agent-declared names.
        "cf_status", "scan_bugs", "scan_codebase", "generate_sentences",
        # 2026-09-27 SELF_DEV_P4_DESIGN: new, in-memory design brief/report actions.
        # These are proposals for pending independent review; no existing tier changed.
        "brand_identity", "brand_consistency", "inclusive_visual_review", "inclusive_prompt",
        "ux_architecture", "information_architecture", "visual_storyboard", "visual_narrative",
        "whimsy_design", "microinteraction_audit", "level_design", "level_flow",
        "narrative_design", "narrative_arc", "technical_art", "asset_pipeline",
        "spatial_design", "spatial_comfort", "immersive_design", "immersive_flow",
        "xr_interface", "xr_interaction", "cultural_review", "cultural_brief",
        # 2026-09-29 SELF_DEV_P3_SECURITY: 16 NEW GREEN entries proposed for
        # pending independent review; no existing tier changed. Every handler
        # in districts/security/security_specialists.py is deterministic,
        # in-memory, and read-only apart from standard successful-task HP
        # accounting. In particular, patch proposal/verification
        # never applies a diff, runs code/tests/shell, commits, or merges.
        "patch_proposal_brief", "patch_proposal_check",
        "patch_verification_brief", "patch_verification_check",
        "scan_inventory_brief", "scan_inventory_check",
        "scan_load_brief", "scan_load_check",
        "scan_research_brief", "scan_research_check",
        "scan_verification_brief", "scan_verification_check",
        "identity_trust_brief", "identity_trust_check",
        "automation_governance_brief", "automation_governance_check",
        # 2026-09-30 (self-dev program follow-up, owner-approved "solve 1,2,3,4"): BlockchainSecurityAuditor
        # is read-only, in-memory regex/text pattern analysis over caller-supplied Solidity source (no
        # execution, no live chain/RPC call, no file write) -- same GREEN classification as every other
        # Security specialist in this block. Flagged for the pending independent review.
        "contract_scan_brief", "contract_pattern_check",
        # 2026-09-29 (self-dev program follow-up, owner-approved coverage sweep): SlackArchaeologist is
        # read-only, in-memory analysis over caller-supplied message records (no send, no external call,
        # no file write) -- same GREEN classification as every other Security specialist in this block.
        # Flagged for the pending independent review like the rest of this program.
        "slack_archaeology_brief", "slack_archaeology_check",
        # 2026-09-28 T9-fix-1 (Codex review finding, verified real by Claude): email_agent.py declares mark_read
        # as a capability but it had no tier entry at all, so Governor._is_known_task_type() let it dispatch
        # with zero PermissionGateway involvement -- not even a GREEN classification. mark_read only flips a
        # read/unread flag on an email already in the owner's own local store; no send, no delete, no external
        # effect. New tier entry, flagged here for the pending independent review per SELF_DEV_AGENT_SPEC.md.
        "mark_read",
        # 2026-09-28 (P7/chief_of_staff self-dev package, tier decision closed by Claude): 5 new,
        # distinct product-role capabilities were registered with no tier entry at all -- the same
        # class of gap T9-fix-1 closed for email_agent.py. All 5 are read/analysis-only: caller-supplied
        # or fetched (via the existing GREEN search_web) evidence, routed-LLM synthesis, and a write only
        # to the agent's own in-memory know() cache -- no owner data mutation, no external send. New tier
        # entries, flagged here for the pending independent review per SELF_DEV_AGENT_SPEC.md.
        "product_trend_research", "product_feedback_analysis", "product_requirements",
        "product_sprint_ranking", "product_work_nudge",
        # 2026-09-28 SELF_DEV_P5_MARKETING: 58 NEW GREEN entries (a tier addition, no existing tier changed or loosened),
        # flagged for the pending independent review. Handlers: districts/marketing/marketing_specialists.py. Every one
        # returns an in-memory evidence report or recomputes numbers from caller-supplied data; none posts, spends, sends,
        # or edits anything external. <x>_brief = evidence-completeness brief, <x>_check = deterministic verification.
        "aso_listing_brief", "aso_listing_check", "baidu_seo_brief", "baidu_seo_check",
        "bilibili_content_brief", "bilibili_title_check", "book_coauthor_brief", "book_outline_check",
        "carousel_growth_brief", "carousel_slide_check", "china_ecom_brief", "china_ecom_check",
        "china_localization_brief", "china_localization_check", "cross_border_brief", "cross_border_margin_check",
        "douyin_strategy_brief", "douyin_content_check", "instagram_curation_brief", "instagram_caption_check",
        "kuaishou_strategy_brief", "kuaishou_content_check", "linkedin_content_brief", "linkedin_post_check",
        "livestream_commerce_brief", "livestream_run_check", "podcast_strategy_brief", "podcast_episode_check",
        "private_domain_brief", "private_domain_funnel_check", "reddit_community_brief", "reddit_post_check",
        "short_video_edit_brief", "short_video_edit_check", "tiktok_strategy_brief", "tiktok_caption_check",
        "twitter_engagement_brief", "twitter_post_check", "video_optimization_brief", "video_metadata_check",
        "xiaohongshu_note_brief", "xiaohongshu_note_check", "zhihu_strategy_brief", "zhihu_answer_check",
        "paid_media_audit_brief", "paid_media_account_check", "paid_creative_brief", "paid_creative_check",
        "paid_social_brief", "paid_social_metrics_check", "ppc_strategy_brief", "ppc_budget_check",
        "programmatic_buy_brief", "programmatic_inventory_check", "search_query_brief", "search_query_waste_check",
        "tracking_setup_brief", "tracking_event_check",
        # 2026-09-28/29 (P5/marketing review finding, closed by Claude): task_completion is a real,
        # agent-declared capability (AICitationStrategist.check_agentic_task_completion, the real match
        # for the 'agentic-search-optimizer' persona) with no tier entry at all -- the same class of gap
        # T9-fix-1 closed for email_agent.py. It is a pure deterministic keyword check on caller-supplied
        # text: no network call, no LLM call, no mutation. New tier entry, flagged for the pending
        # independent review per SELF_DEV_AGENT_SPEC.md.
        "task_completion",
        # 2026-09-29 SELF_DEV_P8_MEMORY_FINANCE_OPS: 20 NEW GREEN entries (a tier addition, no
        # existing tier changed or loosened), flagged for the pending independent review.
        # Handlers: districts/memory_curator/memory_curator_specialists.py,
        # districts/ops/ops_specialists.py, districts/legal_compliance/legal_compliance_specialists.py.
        # Every one returns an in-memory evidence report or recomputes deterministically from
        # caller-supplied data (set/dict clustering, ast static parse, date math, dict merge,
        # string search); none calls an LLM, posts, sends, or edits anything external.
        "identity_graph_brief", "identity_dedup_check", "lsp_index_brief", "lsp_symbol_check",
        "hr_onboarding_brief", "hr_onboarding_check", "jira_workflow_brief", "jira_workflow_check",
        "project_shepherd_brief", "project_shepherd_check", "support_response_brief",
        "support_response_check",
        "data_consolidation_brief", "data_consolidation_check", "report_distribution_brief",
        "report_distribution_validate", "training_design_brief", "training_outline_check",
        "legal_compliance_brief", "legal_compliance_check",
        # 2026-09-29 SELF_DEV_P6_FOLLOWUP_SALES_SPECIALISTS: 12 NEW GREEN entries
        # (tier additions only; no existing tier changed or loosened), flagged for
        # the pending independent review. Handlers: districts/agency/agency_specialists.py.
        # Every action is an in-memory brief/check over caller-supplied sales evidence;
        # no LLM call, external send, file write, CRM mutation, or proposal generation.
        "acct_health_brief", "acct_health_check",
        "deal_meddpicc_brief", "deal_meddpicc_check",
        "tech_fit_brief", "tech_fit_check",
        "out_seq_brief", "out_seq_check",
        "pipe_velocity_brief", "pipe_velocity_check",
        "prop_coverage_brief", "prop_coverage_check",
        # 2026-09-30 (self-dev program follow-up, owner-approved "solve 1,2,3,4"): SalesCoach and
        # SalesDataExtractionAgent are read-only, in-memory checks over caller-supplied sales
        # evidence (rubric text match / date-window arithmetic), same GREEN classification as
        # every other Agency specialist above. Flagged for the pending independent review.
        "sales_coaching_brief", "sales_coaching_check",
        "sales_data_extraction_brief", "sales_data_extraction_check",
        # 2026-09-30: LoanOfficerAssistant, PropertyMatchAnalyst, and RecruitmentSpecialist are
        # read-only, in-memory checks over caller-supplied evidence (ratio arithmetic / list
        # matching), same GREEN classification as every other Agency specialist above.
        # LoanOfficerAssistant never approves/denies/advises -- it only reports which
        # caller-defined criteria the supplied numbers meet. Flagged for the pending
        # independent review.
        "loan_eligibility_brief", "loan_eligibility_check",
        "property_match_brief", "property_match_check",
        "recruitment_fit_brief", "recruitment_fit_check",
        # 2026-09-29 SELF_DEV_P2_CODING: 28 NEW GREEN entries (tier additions only;
        # no existing tier changed or loosened), flagged for the pending independent
        # review. Handlers: districts/coding/coding_specialists.py. All actions are
        # in-memory briefs or deterministic parsing/diffing/recomputation over
        # caller-supplied artifacts. They do not edit files, execute commands, call
        # services, or mutate external state.
        "agent_sdk_ts_brief", "agent_sdk_ts_check",
        "business_rules_brief", "business_rules_check",
        "legacy_analysis_brief", "legacy_analysis_check",
        "scaffold_brief", "scaffold_structure_check",
        "uplift_migration_brief", "uplift_migration_check",
        "version_delta_brief", "version_delta_check",
        "ai_data_remediation_brief", "ai_data_remediation_check",
        "autonomous_optimization_brief", "autonomous_optimization_check",
        "cms_implementation_brief", "cms_structure_check",
        "mobile_app_brief", "mobile_project_check",
        "review_comment_brief", "review_comment_check",
        "type_design_brief", "type_design_check",
        "mcp_server_brief", "mcp_manifest_check",
        "terminal_integration_brief", "terminal_contract_check",
        # 2026-09-29 SELF_DEV_P10_SELF_DEV: 14 NEW GREEN entries (tier additions
        # only; no existing tier changed or loosened), flagged for the pending
        # independent review. Handler: districts/self_dev/self_dev_specialists.py.
        # All actions parse or compare caller-supplied VECTOR-tooling artifacts in
        # memory. They do not write files, call services/LLMs, or touch product code.
        "agent_creation_brief", "agent_definition_check",
        "plugin_validation_brief", "plugin_manifest_check",
        "skill_review_brief", "skill_structure_check",
        "skill_analysis_brief", "skill_analysis_check",
        "skill_comparison_brief", "skill_comparison_check",
        "skill_grading_brief", "skill_grade_check",
        "hook_conversation_brief", "hook_candidate_check",
    ])
    yellow: list[str] = Field(default_factory=lambda: [
        # commit_code stays YELLOW deliberately: git commits are local and
        # revertible, and .claude/rules/code_style.md explicitly wants VECTOR
        # auto-committing ("Commit every day — minimum 1 commit before
        # sleep"). Gating it behind a phone tap would break a documented,
        # intended workflow. send_message_routine was moved to RED below.
        "create_calendar_event", "commit_code",
        "set_reminder", "write_note_personal",
        "pc_screenshot",
        "monthly_report", "finance_report", "journal", "weekly_journal",
        "create_project", "add_deadline", "log_exercise",
        # VectorCode read/verify action — low blast radius (runs the test
        # suite, no owner-invisible side effect). code_task/code_generate/
        # code_fix/code_debug moved to RED below (2026-08-04 hardening).
        "run_tests",
        # 2026-09-23 hardening (permission-boundary audit): home_control
        # (smart-home device control via districts/home_assistant/) used to
        # be dispatched by core/voice/ambient_listener.py through a direct
        # HAConnector/VoiceBridge call with ZERO permission-gateway check —
        # a real RULE 3 violation ("Permission Gateway is the ONLY path to
        # real-world actions... Nothing bypasses this"). Now routed through
        # the gateway like every other action_type. YELLOW (not GREEN):
        # controls real physical devices, but the existing owner-voice/
        # owner-typed pre-confirm path (proposed_by in ("api_command",
        # "voice")) already treats the spoken/typed command itself as
        # confirmation, matching how other voice-issued YELLOW actions work.
        "home_control",
        # 2026-09-24 (independent review finding -- closing the Governor.
        # dispatch() UNKNOWN-tier residual, see the matching comment on
        # the green list above for full context): real but reversible/
        # lower-stakes writes -- local code edits, drafts, generated media
        # not yet published, internal memory writes, calendar writes,
        # physical device control, and a confirmed-real chained-dispatch
        # mechanism (autopilot.py's run_chain() re-enters the SAME
        # enforced Governor.dispatch() for every hop, so gating the
        # trigger itself YELLOW is sufficient -- a chain that tries to
        # hop into an ungated RED action gets blocked at that hop, not
        # bypassed).
        "git", "refactor", "minimal_change", "context_artifacts",
        "draft_email", "draft_reply",
        "make_video", "site_video", "website_to_video", "video_pipeline",
        "animate_image", "comfyui", "lipsync", "render_html", "url_capture",
        "smart_home", "chain", "autopilot", "incident", "post_mortem", "retry_check",
        "entity_add", "knowledge_add", "knowledge_relate", "relation_add", "remember",
        "calendar", "deadline", "class", "schedule",
        # 2026-09-24 (round-6 independent review finding -- MEDIUM):
        # place_pin/intel_pin route to VectorIntelAgent, which calls
        # ShadowBroker's real sb.place_pin() -- ShadowBroker itself
        # classifies place_pin among its own WRITE_COMMANDS. Reversible/
        # local-state mutation, not GREEN read-only.
        "place pin", "intel pin",
        # 2026-09-25 (owner-approved): local writes, local media edits/generation, network fetches and scans, plus the four
        # GREEN proposals demoted after tracing their handlers (alert_anomaly/analyze_feedback persist, district_report writes
        # files, health_check makes an outbound request, generate_response calls a routed LLM).
        "acknowledge", "acknowledge_alert", "alert_anomaly", "add_background_music", "add_client", "add_subtitles",
        "add_transitions", "adjust_voice_speed", "analyze_feedback", "blocklist", "build_storyboard", "capture_url",
        "clone_voice", "create_note", "dead_code_cleanup", "detection_rule", "district_report", "download_dataset",
        "export_report", "extract_audio", "fetch_trending", "generate_batch", "generate_captions",
        "generate_config", "generate_highlight_captions", "generate_in_my_voice", "generate_response",
        "generate_subtitles", "generate_tags", "generate_voice", "health_check", "link_notes", "log_step",
        "memory_store", "merge_clips", "network_scan", "organize_notes", "port_scan", "preprocess_data",
        "process_event", "refactor_clean", "remove_metric", "save_note", "scan_artifact", "scan_vulnerabilities",
        "start_run", "title_thumbnail", "tokenize_data", "track_metric", "translate_captions", "trim_video",
        "update_client", "yt_dlp",
        # 2026-09-25 (Governor untiered-name closure): agent-declared names that write locally, edit media,
        # create branches/drafts, or generate files.
        "backup_db", "write", "generate", "create", "create_branch", "update_draft", "generate_tests", "merge",
        "add_call_contact", "add_course",
        # 2026-09-29 SELF_DEV_P9_LEGAL_COMPLIANCE: ten NEW YELLOW entries,
        # explicitly flagged for pending independent review. These handlers
        # are read-only but regulated-advice-adjacent, so the owner-approved
        # YELLOW default applies. No GREEN exception and no existing tier change.
        "healthcare_service_brief", "healthcare_service_check",
        "healthcare_marketing_brief", "healthcare_marketing_check",
        "legal_billing_brief", "legal_billing_check",
        "legal_intake_brief", "legal_intake_check",
        "legal_document_brief", "legal_document_check",
        # 2026-09-28 T9-fix-1 (Codex review finding, verified real by Claude): email_agent.py declares
        # discard_draft and move as capabilities with no tier entry, so Governor._is_known_task_type()
        # let both dispatch with zero PermissionGateway involvement. Both are real, local mutations of the
        # owner's own mailbox state (discarding a draft, moving an email between folders) -- no external
        # send, so RED is not warranted, but they are not read-only either. New tier entries, flagged here
        # for the pending independent review per SELF_DEV_AGENT_SPEC.md.
        "discard_draft", "move",
    ])
    red: list[str] = Field(default_factory=lambda: [
        "send_email", "delete_files", "execute_code",
        "financial_transaction", "push_github", "deploy_production",
        "overwrite_note_personal",
        # OD-22/OD-24/OD-25 (owner decision 2026-10-08): destructive
        # MCP/API operations require explicit owner approval before mutation.
        "memory_clear", "file_delete", "task_delete", "config_reset",
        "worker_reset", "agent_hp_award", "memory_restore",
        # Hand Execution Engine — Hands with requires_approval=True
        # (browser: purchases/forms; content: publishing; clip: upload).
        "hand_browser", "hand_content", "hand_clip",
        # Real money / irreversible outward actions — owner approval ALWAYS
        # (audit 2026-06-21: these previously bypassed the gateway entirely).
        # solana_swap_execute: notifies owner with price + reasoning, signs only on approval.
        "solana_swap_execute", "content_publish",
        # 2026-08-04 hardening (prompt-injection -> unattended-execution audit):
        # moved out of YELLOW. As YELLOW, these auto-executed after a ~10s
        # window with no owner confirmation whenever VECTOR_YELLOW_AUTO_CONFIRM=1
        # (owner's live .env) and the proposing LLM's task_type wasn't rejected —
        # a direct path from ingested untrusted text (email/web/message) ->
        # classify_chat_intent()'s invented task_type -> unattended shell/GUI/
        # code/fetch execution. See permission_gateway.py's RED_INTERACTIVE_TOOLS
        # for how these are gated (owner-typed/voice commands still pre-confirm
        # instantly like they did as YELLOW; anything else always waits for a
        # real Pushover owner approval, fail-closed on timeout, no LLM-council
        # auto-proceed).
        "run_shell_command",                                    # arbitrary shell execution
        "gui_task", "click_screen", "desktop_task",              # VLM-driven desktop control
        # 2026-09-23 (independent review finding): "web_task" is a real,
        # live alias GUIAutomationAgent treats identically to
        # "browser_task" (districts/coding/gui_automation_agent.py's own
        # capabilities list and its run() dispatch both name it
        # explicitly) and Governor routes it to the same "coding"
        # district (core/city/governor.py's DISTRICT_TASK_MAP) -- but it
        # was never added to any tier here, leaving it UNKNOWN and able
        # to reach real browser automation completely unclassified.
        "browser_task", "web_task", "vision_control",             # VLM-driven browser control
        "pc_type", "pc_click", "pc_launch_app", "launch_app",    # synthetic input / app launch
        # Task 58B remediation (VECTOR_TECHNICAL_KNOWLEDGE/58B_FINAGENT_
        # TERMINAL_PERMISSION_REMEDIATION.md): FinAgentAgent.launch_terminal()
        # can trigger a real native cmake/build (auto_build=True) and a real
        # subprocess.Popen() launch of the compiled terminal binary — the
        # same class of consequential, resource-consuming, app-launch side
        # effect launch_app already represents. Was previously unclassified
        # (UNKNOWN → blocked at the gateway, but reachable unguarded via
        # FinAgentAgent.run() directly, which called the launcher with no
        # gateway step at all). NOT added to RED_INTERACTIVE_TOOLS below —
        # unlike launch_app, nothing in the codebase routes an owner-typed/
        # spoken command directly to this action_type; it is only reachable
        # via FinAgentAgent, an agent-internal capability, so the standard
        # owner-approval (Pushover/HUD/council) RED flow is correct, not the
        # interactive bypass.
        "launch_terminal",
        # Task 58C remediation (VECTOR_TECHNICAL_KNOWLEDGE/58C_MLOPS_HF_TRAIN_
        # PERMISSION_REMEDIATION.md): MLOpsAgent.hf_train() submits a caller-
        # supplied Python script for REMOTE execution on HuggingFace Jobs
        # cloud infrastructure, using the owner's HF credentials and
        # incurring real (potentially GPU-tier) billing — a strictly more
        # consequential class than execute_code's local sandboxed execution
        # (comparable in severity to financial_transaction: real external
        # cost, real remote code execution, under the owner's account). Was
        # previously unclassified (UNKNOWN → blocked at the gateway, but
        # reachable unguarded via MLOpsAgent.run() directly, which called
        # the HF Jobs submission helper with no gateway step at all). NOT
        # added to RED_INTERACTIVE_TOOLS below — same reasoning as
        # launch_terminal: nothing routes an owner-typed/spoken command
        # directly to this action_type; it is only reachable via MLOpsAgent,
        # an agent-internal capability, so the standard owner-approval
        # (Pushover/HUD/council) RED flow is correct, not the interactive
        # bypass.
        "hf_train",
        # Task 58D remediation (VECTOR_TECHNICAL_KNOWLEDGE/58D_KARPATHY_
        # AUTORESEARCH_PERMISSION_REMEDIATION.md, closing Task 59 Finding D):
        # AutoresearchRunner.run_experiment_cycle() asks the local reasoning
        # LLM to propose a change to train.py, WRITES that LLM-generated
        # Python straight to disk, and EXECUTES it via a real, unsandboxed
        # subprocess.run() — the same class of ungated local code execution
        # as launch_terminal's build/launch, minus a sandbox boundary
        # (execute_code's VectorSandbox path was not reused here: it has no
        # GPU/CUDA env passthrough or long-running-training support without
        # a larger redesign, which is out of scope for closing this one
        # bypass — see the remediation doc's Remediation Design section).
        # Was previously unclassified (UNKNOWN → blocked at the gateway, but
        # reachable unguarded via AutoresearchRunner.run() directly, which
        # called the write-then-execute loop with no gateway step at all).
        # NOT added to RED_INTERACTIVE_TOOLS below — same reasoning as
        # launch_terminal/hf_train: nothing routes an owner-typed/spoken
        # command directly to this action_type; it is only reachable via
        # AutoresearchRunner, an agent-internal capability, so the standard
        # owner-approval (Pushover/HUD/council) RED flow is correct, not the
        # interactive bypass.
        "run_experiment_cycle",
        # Task 58E remediation (VECTOR_TECHNICAL_KNOWLEDGE/58E_VECTOR_BACKTEST_
        # STRATEGY_PERMISSION_REMEDIATION.md, closing a Task 59 high-risk
        # residual): BacktestAgent.vt_backtest(strategy_code=...) writes
        # caller-supplied Python and invokes the vendored vector_backtest
        # runner, which dynamically imports and instantiates it as a
        # SignalEngine — real local code execution, no PermissionGateway
        # sandbox. Gated unconditionally (not only when strategy_code is
        # given): the runner unconditionally requires code/signal_engine.py
        # to exist and there is no default/fallback engine in the current
        # architecture, so every functional invocation of this capability
        # depends on caller-supplied code reaching that path one way or
        # another — see the remediation doc's Remediation Design section.
        # Was previously unclassified (UNKNOWN → blocked at the gateway, but
        # reachable unguarded via BacktestAgent.run() directly). NOT added
        # to RED_INTERACTIVE_TOOLS below — same reasoning as launch_terminal/
        # hf_train/run_experiment_cycle: nothing routes an owner-typed/
        # spoken command directly to this action_type; it is only reachable
        # via BacktestAgent, an agent-internal capability, so the standard
        # owner-approval (Pushover/HUD/council) RED flow is correct, not the
        # interactive bypass.
        "vt_backtest",
        # Task 58F remediation (VECTOR_TECHNICAL_KNOWLEDGE/58F_INCIDENT_
        # PLAYBOOK_DESTRUCTIVE_ACTION_PERMISSION_REMEDIATION.md, closing the
        # Task 59 incident-playbook residual): IncidentPlaybookRunner's
        # destructive handlers ran real, unsandboxed OS-level operations
        # (netsh firewall rule add/delete; taskkill by PID/name — the latter
        # unrestricted, able to target any process) with caller/evidence-
        # controlled targets and zero PermissionGateway involvement.
        # Reachable via Governor's ordinary exact-match capability routing
        # to IncidentPlaybookRunner ("execute_playbook" is a declared
        # capability) — previously unclassified (UNKNOWN → blocked at the
        # gateway, but reachable unguarded via IncidentPlaybookRunner.
        # execute_playbook()/run() directly, which called these handlers
        # with no gateway step at all). Gated at the individual destructive
        # HANDLER level (not the top-level execute_playbook/run_playbook
        # capability) so the playbook system's read-only/notification steps
        # (log_evidence, notify, capture_process_snapshot,
        # escalate_to_human) — and a future genuinely-autonomous SIEM
        # auto-response pipeline (districts/security/siem_pipeline.py,
        # confirmed dormant/not-currently-bootstrapped this task, but built
        # for exactly this purpose) — are not forced through an owner-
        # approval gate for actions that were never dangerous, per the
        # remediation doc's Phase 2/Chosen Security Boundary sections.
        # isolate_process is not separately listed: it delegates internally
        # to the same kill_process handler, which is now gated once, at the
        # shared implementation, covering both.  NOT added to
        # RED_INTERACTIVE_TOOLS below — same reasoning as every prior
        # 58-series finding: nothing routes an owner-typed/spoken command
        # directly to these action_types; they are only reachable via
        # IncidentPlaybookRunner, an agent-internal capability, so the
        # standard owner-approval (Pushover/HUD/council) RED flow is
        # correct, not the interactive bypass.
        "block_ip", "unblock_ip", "kill_process",
        "code_task", "code_generate", "code_fix", "code_debug",  # code write + execute paths
        "download_file",                                         # arbitrary fetch-to-disk
        # 2026-08-05: moved from YELLOW. This dispatches to the communications
        # district and actually SENDS a message to a real person. As YELLOW it
        # auto-executed after ~10s with no confirmation whenever
        # VECTOR_YELLOW_AUTO_CONFIRM=1 — and as of today the autonomous loop is
        # live again, so an LLM-invented task_type could send something
        # outward, under the owner's name, unattended. Owner-typed/spoken
        # sends still go instantly via the RED_INTERACTIVE_TOOLS bypass; only
        # autonomous ones now wait for a real Pushover approval.
        "send_message_routine",                                  # sends a real message to a real person
        # 2026-09-24 (independent review finding -- closing the Governor.
        # dispatch() UNKNOWN-tier residual, see the matching comment on
        # the green list above for full context): real, hard-to-reverse
        # side effects confirmed by direct trace of the real handler code
        # (not by name alone -- several look dangerous by keyword but
        # resolve to no real branch at all, and were classified GREEN
        # instead; see the green list's own comment). vc_index/vc_update/
        # vc_graph_build/index_codebase: real MCP index/update/graph-build
        # writes (districts/coding/code_intel_agent.py). str_replace: real
        # file write (districts/coding/code_conductor_agent.py) -- kept
        # RED as defense-in-depth even though CodingSwarm's keyword-score
        # routing to this exact handler isn't guaranteed for this literal
        # task_type. execute_trade/place_order/solana_execute/
        # solana_order/hedge_trade/hedge_run: real trade/order execution
        # (districts/investment/execution_engine.py, hedgebot_agent.py) --
        # distinct from the analysis-only agents (StockAnalyst etc.) the
        # "never trades" house rule targets. broadcast/delegate_task: real
        # external peer-send (districts/governance/federation_agent.py).
        # deploy/restart/backup: real subprocess/service actions
        # (districts/ops/devops_automator.py, established earlier this
        # session).
        "vc_index", "vc_update", "vc_graph_build", "index_codebase", "str_replace",
        # 2026-09-24 (round-6 independent review finding -- HIGH):
        # code_index/vc_graph/dependency_graph are real, exact aliases
        # code_intel_agent.py itself routes into the SAME MCP write calls
        # as their already-RED siblings (vc_index, vc_graph_build) --
        # `elif task_type in ("vc_index", "code_index", "index_codebase")`
        # and `elif task_type in ("vc_graph", "vc_graph_build",
        # "dependency_graph", "code_graph")`. vc_watch's own default
        # params.action is "start", which immediately calls the same real
        # index-update path as vc_update, not a passive status check.
        "code_index", "vc_graph", "dependency_graph", "vc_watch",
        "execute_trade", "place_order", "solana_execute", "solana_order",
        "hedge_trade", "hedge_run",
        "broadcast", "delegate_task",
        "deploy", "restart", "backup",
        # 2026-09-24 (round-5 independent review finding -- HIGH): both
        # were classified GREEN in the first pass, but each is real and
        # dangerous ON ITS OWN merits (independent of the params.action
        # dispatch-order bug fixed the same day in code_conductor_agent.py
        # /mlops_agent.py): code_conduct drives a REAL multi-agent
        # code-editing pipeline that writes to disk (this exact danger is
        # already documented in code_conductor_agent.py's own 2026-07-29
        # comment); hf_hub's default hub_action is safe ("list") but the
        # SAME outer type accepts hub_action="delete"/"upload" -- a real
        # remote Hugging Face Hub write under the owner's token -- with no
        # separate outer identity distinguishing safe from dangerous, the
        # same reasoning that already puts hf_train in RED (Task 58C).
        "code_conduct", "hf_hub",
        # 2026-09-25 (owner-approved): publish to public platforms, delete/rollback/prune, external repo writes, autonomous
        # chaining, cross-machine actions, live rule/code reload.
        "autonomous_chaining", "autopilot_trigger", "create_and_upload", "cross_machine", "delete_client",
        "escalate", "execute_scheduled_uploads", "github", "hot_reload", "prune_retention",
        "rollback", "run_pending", "schedule_upload", "upload_instagram", "upload_tiktok", "upload_twitter",
        "upload_youtube",
        # 2026-09-25 (Governor untiered-name closure): agent-declared names that delete files/messages/data, prune
        # retention, or publish/upload to an external destination. execute_playbook is deliberately NOT here: the
        # playbook runner gates every destructive step through the gateway itself.
        "cleanup_logs", "delete", "publish", "upload", "prune",
    ])
    # Trust ladder — earned autonomy for YELLOW actions (core/loop/trust_ladder.py).
    # N consecutive explicit approvals with zero bad outcomes → auto-execute;
    # any rejection or failed execution demotes instantly. RED never participates.
    trust_ladder_enabled: bool = True
    trust_promotion_streak: int = Field(20, ge=3, le=1000)


class CouncilConfig(BaseModel):
    max_per_week: int = Field(10, ge=1, le=100)
    hp_gate: int = Field(700, ge=0, le=1000)
    cost_inr: float = Field(1.60, ge=0)
    # 2026-09-24 (external review, Phase 2): was hardcoded to 5.0s, far too
    # short for a cold Ollama model swap under OLLAMA_MAX_LOADED_MODELS=1 --
    # measured 58% of real deliberations (data/council_log.jsonl) timed out
    # and defaulted to defer. 30s is sized for a realistic cold-load, not a
    # warm-model round trip.
    deliberation_timeout: float = Field(30.0, ge=5.0, le=120.0)


class AgentDeathLoopConfig(BaseModel):
    """2026-09-24 (external review, Phase 3 / KNOWN_ISSUES #81): breaker for an
    agent that keeps dying and respawning (APITester died ~858x/day, once
    every ~63s). After `max_deaths` deaths of the SAME agent name within
    `window_seconds`, its successor is quarantined (not routable) for
    `base_backoff_seconds`, doubling per consecutive quarantine up to
    `max_backoff_seconds`, instead of respawning into the same failure."""
    max_deaths: int = Field(5, ge=2, le=100)
    window_seconds: float = Field(600.0, ge=10.0)
    base_backoff_seconds: float = Field(300.0, ge=1.0)
    max_backoff_seconds: float = Field(3600.0, ge=1.0)


class CostConfig(BaseModel):
    monthly_budget_inr: int = Field(500, ge=0)
    alert_inr: int = Field(400, ge=0)

    @model_validator(mode="after")
    def alert_below_budget(self):
        if self.alert_inr > self.monthly_budget_inr:
            raise ValueError(
                f"alert_inr ({self.alert_inr}) must be ≤ monthly_budget_inr ({self.monthly_budget_inr})"
            )
        return self


class PersonalityConfig(BaseModel):
    enabled: bool = True
    character_card_path: str = ""
    character_version: str = "v1.0"
    sentiment_method: str = "keyword"  # keyword | embedding | llm
    consistency_threshold: float = Field(0.70, ge=0.0, le=1.0)
    consistency_weights: dict[str, float] = Field(default_factory=lambda: {
        "trait": 0.40, "rules": 0.35, "quirks": 0.15, "speech": 0.10,
    })
    learning_enabled: bool = True
    personality_version: str = "1.0"


class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = Field(5, ge=1, le=100)
    recovery_timeout_sec: float = Field(30.0, ge=1.0, le=300.0)
    half_open_max_retries: int = Field(3, ge=1, le=10)
    success_threshold: int = Field(2, ge=1, le=10)


class BulkheadConfig(BaseModel):
    max_concurrent: int = Field(4, ge=1, le=32)
    max_queue: int = Field(10, ge=1, le=100)
    queue_timeout_sec: float = Field(30.0, ge=1.0, le=300.0)


class FailoverConfig(BaseModel):
    secondary_url: str = "http://127.0.0.1:8001"
    heartbeat_interval_sec: float = Field(5.0, ge=1.0, le=60.0)
    max_missed_heartbeats: int = Field(3, ge=1, le=10)


class GracefulDegradationConfig(BaseModel):
    cooldown_sec: float = Field(60.0, ge=10.0, le=600.0)
    enabled: bool = True


class ChaosConfig(BaseModel):
    enabled: bool = False
    schedule_interval_h: int = Field(24, ge=1, le=168)


class ResilienceConfig(BaseModel):
    enabled: bool = True
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    bulkhead: BulkheadConfig = Field(default_factory=BulkheadConfig)
    failover: FailoverConfig = Field(default_factory=FailoverConfig)
    degradation: GracefulDegradationConfig = Field(default_factory=GracefulDegradationConfig)
    chaos: ChaosConfig = Field(default_factory=ChaosConfig)


class VoiceConfig(BaseModel):
    whisper_model: str = "large-v3"
    stt_engine: str = "whisper"
    # Pin STT to one language. Owner speaks English; leaving Whisper on
    # auto-detect made it "hear" Japanese/gibberish in room noise and reply in
    # random languages (2026-07-17). Set to "" for auto-detect (multilingual
    # voice input), or e.g. "hi" for Hindi. Env: VOICE__STT_LANGUAGE
    stt_language: str = "en"
    device: str = "cuda"
    compute_type: str = "float16"
    kokoro_model_dir: str = str(Path(__file__).parent.parent / "models" / "kokoro")
    kokoro_speed: float = Field(0.85, ge=0.1, le=3.0)
    kokoro_voice: str = "bm_george"  # en voice; British male (JARVIS-style). Swap via VOICE__KOKORO_VOICE
    # Utterances shorter than this are never speaker-judged (fail open) — a
    # d-vector from <1s of audio cannot separate the owner from noise.
    speaker_verify_min_seconds: float = 1.0
    wake_threshold: float = Field(0.5, ge=0.0, le=1.0)
    record_duration_sec: float = Field(5.0, ge=1.0, le=120.0)
    sample_rate: int = Field(16000, ge=8000, le=96000)
    wake_phrase: str = "hey_vector"
    vad_threshold: float = Field(0.02, ge=0.001, le=1.0)
    vad_frame_ms: int = Field(30, ge=10, le=100)
    silence_timeout_sec: float = Field(2.0, ge=0.1, le=30.0)
    conversation_timeout_sec: int = Field(30, ge=5, le=300)
    max_concurrent_sessions: int = Field(3, ge=1, le=10)
    streaming_enabled: bool = True
    # LLM chat-vs-action fallback when the regex intent patterns miss.
    # Uses the ambient model (resident, fast); adds <~1s before chat streaming starts.
    llm_intent_fallback: bool = True
    llm_intent_timeout_sec: float = Field(12.0, ge=0.5, le=30.0)
    # Hard budget for the cloud-primary leg of the intent gate; past this the
    # gate abandons cloud and falls back to local focus (voice must not stall).
    llm_intent_cloud_budget_sec: float = Field(8.0, ge=1.0, le=60.0)
    # Voice cloning (voicebox absorption — chatterbox-tts optional install)
    cloning_engine: str = "chatterbox"       # "chatterbox" | "voxcpm"
    cloning_model_dir: str = str(Path(__file__).parent.parent / "models" / "chatterbox")
    cloning_device: str = "cuda"
    cloning_exaggeration: float = Field(0.5, ge=0.0, le=1.0)
    cloning_cfg_weight: float = Field(0.5, ge=0.0, le=1.0)
    default_voice_profile: str = ""          # profile name from voice_profiles collection
    prefer_local_voice: bool = True          # True → local cloning before ElevenLabs cloud
    effects_default: list = Field(default_factory=list)   # default DSP chain for new profiles
    # VoxCPM2 absorption (docs/repo_analysis/VoxCPM.md) — alternate
    # cloning_engine, on-demand load (8GB VRAM), never permanent-resident
    # alongside vector-focus. Apache-2.0, guarded optional install (`pip
    # install voxcpm`). Kept off Hindi by default — vendor's own WER is weak.
    voxcpm_model_dir: str = str(Path(__file__).parent.parent / "models" / "voxcpm")
    voxcpm_inference_timesteps: int = Field(10, ge=1, le=100)
    voxcpm_cfg_value: float = Field(2.0, ge=0.0, le=10.0)
    voice_design_description: str = (
        "A calm, articulate British male voice, mid-30s, measured pace, "
        "warm but precise — like a trusted technical advisor."
    )
    # Supertonic 3 absorption (docs/repo_analysis/supertonic.md) — alternate
    # LIVE-conversation engine (not cloning — that's cloning_engine above).
    # CPU-only, zero VRAM. Kept off by default until an owner A/B confirms
    # it against Kokoro's bf_emma "VECTOR voice" identity.
    live_engine: str = "kokoro"               # "kokoro" | "supertonic"
    supertonic_model_dir: str = ""
    supertonic_total_steps: int = Field(8, ge=1, le=50)
    supertonic_voice_style: str = ""          # path to a Voice-Builder persona JSON
    supertonic_auto_download: bool = False    # ~260MB model weights -- separate explicit owner opt-in
    # Owner-only voice gate (core/voice/speaker_verify.py) — closes the "anyone
    # near the mic is treated as the owner" gap in the wake-word path.
    speaker_verify_enabled: bool = True       # no-op until data/voice_profiles/owner_voiceprint.npz exists
    speaker_verify_threshold: Optional[float] = None  # None = engine default (0.75 resemblyzer / 0.85 fallback)


class SecurityCfg(BaseModel):
    suspicious_ports: list[int] = Field(default_factory=lambda: [
        4444, 6666, 1337, 31337, 9001, 9050,
    ])
    suspicious_process_names: list[str] = Field(default_factory=lambda: [
        "cryptominer", "keylogger", "miner", "rat", "netcat",
        "mimikatz", "cobaltstrike", "metasploit", "ncrack",
        "xmrig", "monero", "cpuminer",
    ])
    entropy_threshold: float = Field(7.5, ge=0.0, le=8.0)


class SecurityConfig(BaseModel):
    siem_enabled: bool = False
    network_monitor_interval_sec: int = 30
    log_aggregator_enabled: bool = True
    detection_rules_enabled: bool = True
    alert_manager_enabled: bool = True
    incident_response_enabled: bool = True
    pushover_enabled: bool = True
    pushover_user_key: str = ""
    pushover_api_token: str = ""
    blocked_domains: list[str] = ["shell_command", "command_line", "python_script"]


class ControlConfig(BaseModel):
    adb_path: str = "adb"
    phone_device_id: Optional[str] = None


class SensingConfig(BaseModel):
    lgbm_model_path: str = "./models/malware_lgbm.txt"
    known_faces_dir: str = "./data/known_faces"
    camera_index: int = Field(0, ge=0)
    screen_ocr_enabled: bool = True
    fatigue_check_interval_sec: int = Field(30, ge=5, le=3600)
    screen_enabled: bool = False
    camera_enabled: bool = False
    # Task B.2 (governor-wiring-and-ambient-perception.md): ADB-phone observe
    # source. Defaults off — owner-hardware-dependent (needs a connected
    # Android device + adb on PATH). PhoneController already degrades
    # gracefully (is_connected()=False, get_notifications()=[]) when absent.
    phone_enabled: bool = False
    # Coding Companion (core/sensing/stuck_detector.py) — proactive help when
    # the owner is stuck in a vectorcode terminal session. Needs screen_enabled.
    stuck_detection_enabled: bool = True
    stuck_min_samples: int = Field(4, ge=2, le=100)      # ~30s OCR samples
    stuck_after_min: float = Field(2.0, ge=0.5, le=120)  # error must persist
    stuck_cooldown_min: float = Field(20.0, ge=1, le=1440)
    # While the owner runs a vectorcode CLI session, VECTOR skips 2 of 3 think
    # ticks — one GPU, OLLAMA_MAX_LOADED_MODELS=1: don't evict the owner's model.
    defer_llm_while_owner_codes: bool = True
    vc_session_marker: str = str(Path.home() / ".vector" / "vc_session.json")
    # Task B.3: wearable (HR/sleep/steps) observe source. Architecture docs
    # name it as a core observe source; zero wiring existed before this.
    # Owner-hardware-dependent (no wearable device/API credentials
    # configured yet) — defaults off. districts/health/wearable_connector.py
    # already degrades gracefully to an empty poll with no sources enabled.
    wearable_enabled: bool = False


class CodingConfig(BaseModel):
    repo_path: str = str(_BASE_DIR)


class VectorCodeConfig(BaseModel):
    enabled: bool = True
    python_path: str = str(_BASE_DIR / "vectorcode" / "python" / "vectorcode")
    mcp_port: int = Field(9001, ge=1024, le=65535)
    base_url: str = "http://127.0.0.1:9001"
    timeout_sec: float = Field(300.0, ge=10.0, le=3600.0)


class VectorCodeCommsConfig(BaseModel):
    local_url: str = "http://127.0.0.1:8080"
    port: int = Field(8080, ge=1024, le=65535)
    timeout_sec: float = Field(10.0, ge=1.0, le=60.0)
    repo_path: str = str(Path(__file__).parent.parent / "vectorcode")


class TursoConfig(BaseModel):
    url: str = ""
    token: str = ""


class KarpathyConfig(BaseModel):
    runs_dir: str = "./data/training_runs"
    data_dir: str = "./data/datasets"
    daily_minutes: int = Field(30, ge=5, le=120)


class AirLLMConfig(BaseModel):
    models_dir: str = "./models/airllm"
    cache_dir: str = "./data/airllm_cache"
    max_gpu_memory_gb: float = Field(11.0, ge=1.0, le=24.0)


class ResearchLabConfig(BaseModel):
    enabled: bool = False
    sandbox_backend: str = "subprocess"
    max_concurrent_experiments: int = 2
    schedule_interval_hours: int = 6
    sandbox_enabled: bool = False


class EventBusConfig(BaseModel):
    enabled: bool = True
    max_queue_size: int = 1000
    worker_pool_size: int = 4


class EmergencyConfig(BaseModel):
    enabled: bool = False
    detector_interval_sec: int = 5
    pushover_enabled: bool = True
    quiet_hours_start: int = 23
    quiet_hours_end: int = 7
    rate_limit_pushover_monthly: int = 10000


class HealthConfig(BaseModel):
    enabled: bool = False
    wearable_poll_interval_minutes: int = 15
    health_analysis_interval_minutes: int = 60
    emergency_detection_interval_seconds: int = 60
    pushover_enabled: bool = True
    retention_days: int = 90


class CodeIntelConfig(BaseModel):
    project_id: str = "vector-codebase-main"
    qdrant_url: str = "http://127.0.0.1:6333"
    embedding_provider: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "nomic-embed-text"
    chunk_size: int = Field(100, ge=10, le=500)
    chunk_overlap: int = Field(10, ge=0, le=50)
    max_file_size_mb: float = Field(5.0, ge=0.1, le=50.0)
    dist_path: str = "vectorcode/code_intel/dist/index.js"


class TrainingConfig(BaseModel):
    adapters_dir: str = "models/adapters"
    models_dir: str = "models"
    unsloth_enabled: bool = False
    eval_results_dir: str = "data/evaluations"
    self_improvement_enabled: bool = True
    self_improvement_interval_hours: int = 168
    distillation_enabled: bool = True
    training_enabled: bool = False
    # Post-training (SFT/DPO on VECTOR's own reasoning_chains + counterfactual
    # rejections — see plans/post-training-pipeline.md). Off by default;
    # enabling is a deliberate owner choice, not a silent default flip.
    post_training_enabled: bool = False
    post_training_min_chain_reward: float = 0.7
    post_training_min_examples: int = 50
    post_training_base_model: str = "vector-coder"


class PredictiveAnalyticsConfig(BaseModel):
    enabled: bool = False
    forecast_interval_minutes: int = 15
    simulation_interval_minutes: int = 60
    retention_days: int = 90
    pushover_enabled: bool = True
    max_metrics: int = 14


class HomeAssistantConfig(BaseModel):
    enabled: bool = False
    host: str = "homeassistant.local"
    port: int = 8123
    token: str = ""
    use_ssl: bool = False
    rate_limit_per_sec: int = 10


class SidecarsConfig(BaseModel):
    # Paths to sidecar applications that VECTOR can launch alongside itself.
    # Leave empty ("") to use the default location under the parent of the
    # VECTOR codebase (i.e. <codebase-parent>/GitHub/<AppName>).
    # Set a non-empty path to point at wherever you cloned/installed the app.
    #
    # ComfyUI: local Stable-Diffusion node UI; runs from the sibling install.
    #   Default: <codebase-parent>/ComfyUI  (the real install)
    #   Override: set VECTOR_COMFYUI_PATH env var.
    comfyui_path: str = ""
    #
    # hyperframes: local Node media-frame server; must be cloned locally.
    #   Default: <codebase-parent>/GitHub/hyperframes-main
    #   Override: set VECTOR_HYPERFRAMES_PATH env var.
    hyperframes_path: str = ""


class AdsConfig(BaseModel):
    scripts_path: str = "districts/marketing/ads/scripts"
    references_path: str = "districts/marketing/ads/references"
    templates_path: str = "districts/marketing/ads/templates"
    image_provider_order: list[str] = Field(default_factory=lambda: ["gemini", "openai", "stability", "replicate"])
    pdf_output_dir: str = "output/ads_reports"
    screenshot_dir: str = "output/ads_screenshots"
    max_concurrent_audits: int = Field(6, ge=1, le=10)


# ── Main settings (reads from .env) ───────────────────────────────────────────

class VectorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BASE_DIR / ".env",
        extra="ignore",
        case_sensitive=False,
        # Nested overrides from .env, e.g. SENSING__SCREEN_ENABLED=true or
        # VOICE__LLM_INTENT_FALLBACK=false. Only vars containing "__" are
        # affected — flat keys (ANTHROPIC_API_KEY, ...) behave exactly as before.
        env_nested_delimiter="__",
    )

    def _mapping_value(self, key: str, default=None):
        if not hasattr(self, key):
            return default
        value = getattr(self, key)
        if isinstance(value, BaseModel):
            return value.model_dump()
        return value

    def get(self, key: str, default=None):
        return self._mapping_value(key, default)

    def __getitem__(self, key: str):
        if not hasattr(self, key):
            raise KeyError(key)
        return self._mapping_value(key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and hasattr(self, key)

    # Core — mapped from env var names
    VECTOR_ENV: str = "development"
    VECTOR_DEBUG: bool = False
    VECTOR_VAULT_PATH: str = str(Path.home() / "V.E.C.T.O.R Brain")
    OLLAMA_HOST: str = "http://127.0.0.1:11434"
    # 2026-08-05 (concurrency-bound fix): OLLAMA_MAX_LOADED_MODELS=1 on this
    # 12GB RTX 5070 Ti (.claude/rules/models.md) means the Ollama daemon holds
    # exactly ONE model resident and serves requests against a single decode
    # slot; nothing on VECTOR's side ever bounded how many requests it fired
    # at Ollama concurrently, and two brain processes were once observed
    # holding 90 simultaneous connections against it — dozens of requests
    # queued against something inherently serial, risking VRAM/KV-cache
    # thrash. Default=2: 1 would fully serialize every Ollama call in the
    # process (including background warm_models() calls racing a live chat
    # request) with no benefit, since Ollama's OWN default OLLAMA_NUM_PARALLEL
    # is 4 request-slots time-sliced over the one resident model; 2 keeps a
    # small amount of real overlap (e.g. an embedding call alongside a chat
    # call) while cutting the worst observed blowup (90) by >40x. Override via
    # OLLAMA_MAX_CONCURRENT in .env if VRAM headroom changes (e.g. bigger GPU).
    OLLAMA_MAX_CONCURRENT: int = Field(2, ge=1, le=16)
    # 2026-08-06 (loop-stall root-cause fix, KNOWN_ISSUES #0): grace window
    # added on top of the caller's `timeout` in
    # core/inference/vectorcode_llm.py::chat() before its background-thread
    # future is given up on. See that call site for why the executor is no
    # longer used as a context manager (the old `with` form's blocking
    # shutdown() defeated this timeout entirely).
    VC_LLM_THREAD_GRACE_SEC: float = Field(15.0, ge=0.0, le=120.0)
    # 2026-08-06 (loop-stall root-cause hunt, KNOWN_ISSUES #0): bounds
    # core/loop/permission_gateway.py's `download_file` action, which calls
    # SSRFGuard(resolve_dns=True) -> socket.getaddrinfo() synchronously.
    # getaddrinfo has no built-in timeout and runs directly on whatever
    # thread calls it (the asyncio event-loop thread here) — a hung/
    # unreachable DNS resolver would freeze the whole loop indefinitely with
    # 0% CPU. See permission_gateway.py's download_file handler.
    SSRF_DNS_RESOLVE_TIMEOUT_SEC: float = Field(5.0, ge=0.5, le=30.0)
    # 2026-08-06 (KNOWN_ISSUES #0 Part 1 follow-up): core/inference/ollama_safe.py's
    # module-level threading.Semaphore (bound = OLLAMA_MAX_CONCURRENT) used to be
    # acquired via `with _OLLAMA_SYNC_SEMAPHORE:`, which blocks forever with no
    # timeout. That was ranked secondary in the original hunt because it needs a
    # slot-holder to already be stuck — but fccdeb91f proved a holder CAN hang
    # indefinitely (the exact ThreadPoolExecutor-shutdown bug it fixed one layer
    # up), so a hang here would queue every other Ollama caller behind it too,
    # turning one stuck call into many. Default 60s: comfortably above a normal
    # chat() call (default timeout=8s) and above chat_stream()'s documented
    # deliberate full-duration slot hold, while still bounding a genuinely stuck
    # holder instead of blocking forever.
    OLLAMA_SEMAPHORE_TIMEOUT_SEC: float = Field(60.0, ge=1.0, le=300.0)
    # 2026-08-06 (KNOWN_ISSUES #0 Part 2): core/inference/vectorcode_llm.py's
    # chat() is a plain sync function; called from a thread that owns a RUNNING
    # asyncio event loop (i.e. from inside an async `run()` without `await`/
    # `asyncio.to_thread`) it blocks that loop for up to timeout+grace seconds.
    # ~112 files do this today. Default False = warn-only (loud, rate-limited
    # per call site) so production isn't turned into a mass outage by flipping
    # 112 call sites into exceptions overnight; set True (or env
    # VC_LLM_LOOP_GUARD_STRICT=1) in tests/CI to fail fast instead and prevent
    # the antipattern from growing.
    VC_LLM_LOOP_GUARD_STRICT: bool = False
    # How often (seconds) the same call site is allowed to re-log the blocking-
    # call warning above. Per-site, not global — a new offender is always caught
    # on its first hit; a hot, already-known offender doesn't drown the logs.
    VC_LLM_LOOP_GUARD_COOLDOWN_SEC: float = Field(300.0, ge=0.0, le=3600.0)
    # Task 89B (event-fanout remediation): per-edge cooldown in
    # core/loop/autonomous_loop.py::_fanout_handler. An "edge" is
    # (source_event_type, target_district, target_task_type); firing an
    # edge starts this cooldown regardless of the downstream dispatch's
    # outcome (success/failure/no_agents all consume it identically). Not
    # persisted — a process restart resets all cooldowns by design.
    FANOUT_EDGE_COOLDOWN_SEC: float = Field(120.0, ge=0.0, le=3600.0)
    # Task 91 (R6) — candidate-selection staleness-only diversity guard.
    # core/loop/decision_engine.py::_select_staleness_aware_winner(). A
    # candidate identity (canonical situation_hash, same one policy_memory
    # already keys on) that has been the actual evaluate() winner for this
    # many CONSECUTIVE calls is considered stale; the next distinct,
    # already-scored candidate is chosen instead if one exists — nothing is
    # ever invented. Small default: low enough to actually engage during
    # normal operation (the think loop runs on a short fixed cadence against
    # a fairly static goal/candidate set, so 5 consecutive repeats of the
    # exact same pick is genuine repetition, not legitimate persistence),
    # high enough that ordinary short tests/one-off evaluate() calls never
    # trigger it. Not persisted — process-local only, resets on restart by
    # design (same rationale as FANOUT_EDGE_COOLDOWN_SEC above).
    CANDIDATE_STALENESS_STREAK: int = Field(5, ge=1, le=1000)
    # R8/R9 follow-up — bounds core/loop/decision_engine.py::_correction_penalty()'s
    # EpisodicMemory.recall() call (a real FTS5 query, potentially slow against
    # a large production DB) so it can never block the synchronous per-candidate
    # scoring hot path past this deadline. Same bounded-wait pattern as R1's
    # core/inference/ollama_safe.py::_multi_backend_fallback fix. On timeout,
    # the candidate is scored as if no correction lesson matched (0.0 penalty)
    # -- an honest degrade, never a crash, never a false penalty.
    CORRECTION_PENALTY_TIMEOUT_SEC: float = Field(1.5, ge=0.05, le=10.0)
    VECTOR_DB_KEY: SecretStr = SecretStr("")

    # API keys — SecretStr prevents values leaking into logs or repr()
    ANTHROPIC_KEY: SecretStr = SecretStr("")
    GEMINI_KEY: SecretStr = SecretStr("")
    GITHUB_TOKEN: SecretStr = SecretStr("")
    GITHUB_USERNAME: str = "arghyadeep-deb"
    PUSHOVER_TOKEN: SecretStr = SecretStr("")
    PUSHOVER_USER: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: SecretStr = SecretStr("")
    # Deployed Cloudflare Worker health endpoint (D1 command queue lives behind it).
    # Full /health URL to match existing district usage (ops/sre health probes).
    CF_WORKER_URL: str = "https://vector-api.arghyadeepdeb020703.workers.dev/health"
    VIRUSTOTAL_KEY: SecretStr = SecretStr("")
    NEWSAPI_KEY: SecretStr = SecretStr("")
    STRIPE_KEY: SecretStr = SecretStr("")
    KIIT_USERNAME: str = ""
    KIIT_PASSWORD: SecretStr = SecretStr("")
    GOOGLE_CREDENTIALS_PATH: str = ""
    YOUTUBE_CHANNEL_ID: str = ""
    # Repo integration (docs/repo_analysis/youtube-automation-agent.md):
    # read-only Data API key for trending/competitor lookups — separate from
    # GOOGLE_CREDENTIALS_PATH's OAuth flow (uploads only need OAuth).
    YOUTUBE_DATA_API_KEY: SecretStr = SecretStr("")
    INSTAGRAM_ACCESS_TOKEN: SecretStr = SecretStr("")
    INSTAGRAM_ACCOUNT_ID: str = ""
    ELEVENLABS_KEY: SecretStr = SecretStr("")
    ELEVENLABS_VOICE_ID: str = "pNInz6obpgDQGcFmaJgB"
    OPENROUTER_KEY: SecretStr = SecretStr("")
    MISTRAL_KEY: SecretStr = SecretStr("")
    CONTENT_NICHE: str = "AI"
    VIDEO_UPLOAD_DELAY_MINUTES: int = 30
    # MUAPI_API_KEY removed 2026-07-04 — paid cloud video deleted, local-only.
    WAN2GP_URL: str = ""
    PAGESPEED_API_KEY: SecretStr = SecretStr("")
    HASS_URL: str = ""
    HASS_TOKEN: SecretStr = SecretStr("")

    # LLM provider keys used by absorbed vectorcode/src/ (naming: _API_KEY suffix used there)
    GROQ_API_KEY: SecretStr = SecretStr("")
    XAI_API_KEY: SecretStr = SecretStr("")
    MINIMAX_API_KEY: SecretStr = SecretStr("")
    TAVILY_API_KEY: SecretStr = SecretStr("")
    FIRECRAWL_API_KEY: SecretStr = SecretStr("")
    HONCHO_API_KEY: SecretStr = SecretStr("")
    DEEPGRAM_API_KEY: SecretStr = SecretStr("")
    OLLAMA_API_KEY: SecretStr = SecretStr("")
    AZURE_ANTHROPIC_KEY: SecretStr = SecretStr("")
    AZURE_FOUNDRY_API_KEY: SecretStr = SecretStr("")
    GOOGLE_API_KEY: SecretStr = SecretStr("")
    OPENAI_CODEX_API_KEY: SecretStr = SecretStr("")
    HINDSIGHT_API_KEY: SecretStr = SecretStr("")
    BROWSERBASE_API_KEY: SecretStr = SecretStr("")
    # Runtime vars used by absorbed vectorcode/src/
    VECTOR_HOME: str = str(Path.home() / ".vector")
    VECTOR_TIMEZONE: str = "Asia/Kolkata"
    VECTOR_ALLOW_SHELL_EXEC: bool = False
    VECTOR_WRITE_SAFE_ROOT: str = ""
    VECTOR_ALLOW_PRIVATE_URLS: bool = False
    VECTOR_ALLOW_COMMIT_DRIFT: bool = False

    # Network
    VECTOR_OFP_SECRET: SecretStr = SecretStr("")
    VECTOR_OFP_CERT: str = ""
    VECTOR_OFP_KEY: str = ""
    VECTOR_PEERS: str = ""
    VECTOR_CLOUD_API_URL: str = ""
    VECTOR_BRAIN_URL: str = ""
    VECTOR_BRAIN_API_KEY: SecretStr = SecretStr("")
    VECTOR_OAUTH_REDIRECT_BASE: str = "http://localhost:7788"

    # Collections engine (PocketBase-style data layer) — JWT auth secret
    VECTOR_JWT_SECRET: SecretStr = SecretStr("")

    # Telemetry
    SENTRY_DSN: str = ""
    VECTOR_BUILD_SHA: str = "dev"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    # Infrastructure
    VLLM_BASE_URL: str = "http://localhost:8000/v1"
    CLOUDFLARE_ACCOUNT_ID: str = ""
    SSL_CERT_FILE: str = ""
    SSL_CERT_DIR: str = ""
    ACP_LOGGING_ENABLED: bool = False

    # Sidecar app paths (overrides SidecarsConfig defaults)
    VECTOR_COMFYUI_PATH: str = ""
    VECTOR_HYPERFRAMES_PATH: str = ""

    # Research engine
    LDR_DATA_DIR: str = ""
    LDR_LOG_SETTINGS: str = "none"

    # OAuth
    OAUTH_GITHUB_CLIENT_ID: str = ""
    OAUTH_GITHUB_CLIENT_SECRET: SecretStr = SecretStr("")
    OAUTH_GOOGLE_CLIENT_ID: str = ""
    OAUTH_GOOGLE_CLIENT_SECRET: SecretStr = SecretStr("")

    # Trading
    VECTOR_TRADING_RESULTS_DIR: str = "logs"
    VECTOR_TRADING_CACHE_DIR: str = "cache"
    VECTOR_TRADING_MEMORY_LOG_PATH: str = "memory/trading_memory.md"

    # CORS — overridable via env var as a JSON array
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ])

    # Turso — overridable via env vars
    TURSO_URL: str = ""
    TURSO_TOKEN: SecretStr = SecretStr("")

    # Structured sub-configs — validated by their own models
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    model_router: ModelRouterConfig = Field(default_factory=ModelRouterConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    permission: PermissionConfig = Field(default_factory=PermissionConfig)
    council: CouncilConfig = Field(default_factory=CouncilConfig)
    agent_death_loop: AgentDeathLoopConfig = Field(default_factory=AgentDeathLoopConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    personality: PersonalityConfig = Field(default_factory=PersonalityConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    security: SecurityCfg = Field(default_factory=SecurityCfg)
    siem: SecurityConfig = Field(default_factory=SecurityConfig)
    control: ControlConfig = Field(default_factory=ControlConfig)
    sensing: SensingConfig = Field(default_factory=SensingConfig)
    coding: CodingConfig = Field(default_factory=CodingConfig)
    comms: VectorCodeCommsConfig = Field(default_factory=VectorCodeCommsConfig)
    turso: TursoConfig = Field(default_factory=TursoConfig)
    karpathy: KarpathyConfig = Field(default_factory=KarpathyConfig)
    airllm: AirLLMConfig = Field(default_factory=AirLLMConfig)
    vectorcode: VectorCodeConfig = Field(default_factory=VectorCodeConfig)
    predictive_analytics: PredictiveAnalyticsConfig = Field(default_factory=PredictiveAnalyticsConfig)
    sidecars: SidecarsConfig = Field(default_factory=SidecarsConfig)
    ads: AdsConfig = Field(default_factory=AdsConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    emergency: EmergencyConfig = Field(default_factory=EmergencyConfig)
    code_intel: CodeIntelConfig = Field(default_factory=CodeIntelConfig)
    event_bus: EventBusConfig = Field(default_factory=EventBusConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    research_lab: ResearchLabConfig = Field(default_factory=ResearchLabConfig)
    home_assistant: HomeAssistantConfig = Field(default_factory=lambda: HomeAssistantConfig(
        # os.getenv intentional — lambda can't access self
        enabled=bool(os.getenv("HASS_TOKEN")),
        host=(os.getenv("HASS_URL") or "homeassistant.local").replace("http://", "").replace("https://", "").split(":")[0],
        token=os.getenv("HASS_TOKEN", ""),
    ))

    def get_env(self, key: str, default: str | None = None) -> str | None:
        return os.getenv(key, default)


# ── Instantiate: validation failure is fatal at startup ───────────────────────

try:
    _s = VectorSettings()
    logger.info("[VECTOR][config] Pydantic BaseSettings validated OK")
except Exception as _cfg_err:
    logger.critical(f"[VECTOR][config] Config validation FAILED: {_cfg_err}")
    raise SystemExit(1) from _cfg_err


# ── CONFIG dict — same structure as before, 100% backward compatible ──────────

class _Redacted(str):
    """String subclass whose repr redacts the value.

    FLAG FOR OWNER (Phase 3 audit, 2026-10-02): this only redacts repr()/!r
    (debugger/pretty-print display) — str(), f"{...}", "{}".format(...), and
    loguru's own "{}" placeholder all call __str__/__format__, which are NOT
    overridden here and return the real plaintext value (verified: a
    _Redacted instance is a true str subclass, so str()/f-string formatting
    reads the underlying character buffer directly). Every one of the ~30
    real credentials wrapped via _secret() below (every API key, the DB key,
    the OFP network secret, both OAuth client secrets) has this same gap.
    NOT fixed here: at least one real call site (core/inference/
    vectorcode_llm.py:337, `str(CONFIG["api_keys"]["anthropic_key"])`)
    explicitly relies on str() returning the REAL value to make actual API
    calls -- overriding __str__/__format__ to redact would silently break
    every such real integration (confirmed: at least 3 more files use the
    identical str(CONFIG[...]) extraction pattern for non-secret config,
    same mechanism). A safe fix needs a separate, explicit "real value"
    accessor (mirroring pydantic's own SecretStr.get_secret_value()
    pattern, already used two lines above this class for the underlying
    settings object) with every current str(CONFIG[...]) consumer migrated
    to it before __str__/__format__ can safely redact -- a cross-cutting
    change touching an unknown number of call sites repo-wide, not a
    same-session narrow patch. No currently-logged leak found (checked the
    known consumers), but this is a latent footgun: a single future
    `logger.info(f"... {CONFIG['api_keys']['x']} ...")` anywhere in the
    codebase would leak a real credential while appearing safe.
    """
    def __repr__(self) -> str:
        return f"***({len(self)}chars)***"


def _secret(value: str) -> "_Redacted":
    return _Redacted(value)


def _normalize_base_url(value: str, default: str = "http://127.0.0.1:11434") -> str:
    value = (value or default).strip()
    if not value:
        return default
    if "://" not in value:
        value = f"http://{value}"
    return value.rstrip("/")


def _normalize_supabase_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if "://" in value:
        return value
    if "." not in value and "/" not in value:
        return f"https://{value}.supabase.co"
    return f"https://{value}"


def _normalize_turso_http_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith("libsql://"):
        return "https://" + value[len("libsql://"):]
    return value


CONFIG: dict = {
    "owner_name": "Arghyadeep",
    # Owner's primary email — used as the from-address for VECTOR-composed mail.
    # Override with VECTOR_OWNER_EMAIL. Defaults to the owner's Gmail (the active
    # email path; see docs/EMAIL_SETUP.md).
    "owner_email": os.environ.get("VECTOR_OWNER_EMAIL", "arghyadeepdeb020703@gmail.com"),
    "system_name": "VECTOR",
    "version": "1.0.0",
    "env": _s.VECTOR_ENV,
    "debug": _s.VECTOR_DEBUG,
    "location": os.environ.get("VECTOR_LOCATION", "home"),
    "ofp_secret": _secret(_s.VECTOR_OFP_SECRET.get_secret_value()),
    "peers": _s.VECTOR_PEERS,
    "ofp_cert": _s.VECTOR_OFP_CERT,
    "ofp_key": _s.VECTOR_OFP_KEY,
    "cloud_api_url": _s.VECTOR_CLOUD_API_URL,
    "cloud": {
        "brain_url": _s.VECTOR_BRAIN_URL,
        "api_key": _secret(_s.VECTOR_BRAIN_API_KEY.get_secret_value()),
    },
    "wake": {
        "legion_node_id": os.environ.get("LEGION_NODE_ID", "legion-heavy-node"),
        "legion_wifi_mac": os.environ.get("LEGION_WIFI_MAC", ""),
        "legion_ethernet_mac": os.environ.get("LEGION_ETHERNET_MAC", ""),
        "legion_wake_broadcast": os.environ.get("LEGION_WAKE_BROADCAST", "255.255.255.255"),
        "legion_wake_port": int(os.environ.get("LEGION_WAKE_PORT", "9")),
    },
    # core/email/sender.py (SMTP) + core/email/receiver.py (IMAP) read these exact
    # top-level keys. The primary, owner-connected path is Gmail OAuth (see
    # docs/EMAIL_SETUP.md) via districts/communications/email_intelligence.py --
    # these cover the separate raw SMTP/IMAP transport that districts/communications/
    # email_agent.py's poll_inbox()/send_reply() already call unconditionally.
    # Before this entry existed, CONFIG never defined these keys at all, so both
    # files' CONFIG.get(...) always fell through to "" regardless of .env --
    # IMAP polling and SMTP sending silently no-op'd no matter how .env was set.
    "SMTP_HOST": os.environ.get("SMTP_HOST", ""),
    "SMTP_PORT": int(os.environ.get("SMTP_PORT", "587")),
    "SMTP_USER": os.environ.get("SMTP_USER", ""),
    "SMTP_PASS": _get_secret("SMTP_PASS"),
    "IMAP_HOST": os.environ.get("IMAP_HOST", ""),
    "IMAP_USER": os.environ.get("IMAP_USER", ""),
    "IMAP_PASS": _get_secret("IMAP_PASS"),
    "EMAIL_ADDRESS": os.environ.get("EMAIL_ADDRESS", ""),
    "oauth_redirect_base": _s.VECTOR_OAUTH_REDIRECT_BASE,
    "sentry_dsn": _s.SENTRY_DSN,
    "sentry_env": _s.VECTOR_ENV,
    "otel_endpoint": _s.OTEL_EXPORTER_OTLP_ENDPOINT,
    "vllm_base_url": _s.VLLM_BASE_URL,
    "cloudflare_account_id": _s.CLOUDFLARE_ACCOUNT_ID,
    "ssl_cert_file": _s.SSL_CERT_FILE,
    "ssl_cert_dir": _s.SSL_CERT_DIR,
    "acp_logging_enabled": _s.ACP_LOGGING_ENABLED,
    "build_sha": _s.VECTOR_BUILD_SHA,
    "ldr_data_dir": _s.LDR_DATA_DIR,
    "search_response_limit": int(os.environ.get("VECTOR_SEARCH_LIMIT", "500")),
    "policy_default_score": float(os.environ.get("VECTOR_POLICY_DEFAULT", "0.5")),
    # ── LLM routing policy (simple→cloud keys, heavy-security→local Ollama) ──
    # prefer_local_for_heavy=False → COMPLEX/REASONING go cloud-premium first (speed);
    #   set VECTOR_PREFER_LOCAL_HEAVY=1 to route heavy tasks to local gemma4:26b first.
    # distribute_simple=True → round-robin simple tasks across configured cloud providers.
    "routing": {
        "prefer_local_for_heavy": os.environ.get("VECTOR_PREFER_LOCAL_HEAVY", "0") in ("1", "true", "True"),
        "distribute_simple": os.environ.get("VECTOR_DISTRIBUTE_SIMPLE", "1") in ("1", "true", "True"),
    },
    # ── Avatar presence / trigger mode ────────────────────────────────────────
    # mode: proactive | hybrid | reactive  (see core/loop/presence.py)
    "presence": {
        "mode": os.environ.get("VECTOR_PRESENCE_MODE", "proactive"),
        "dnd_start_hour": int(os.environ.get("VECTOR_DND_START", "23")),
        "dnd_end_hour":   int(os.environ.get("VECTOR_DND_END",   "8")),
        "allowed_proactive_agents": ["nudge_engine", "chief_of_staff", "daily_reviewer"],
        "wake_keywords": ["hey vector", "vector", "ok vector"],
    },
    "vector_home": _s.VECTOR_HOME,
    "vector_timezone": _s.VECTOR_TIMEZONE,
    "allow_shell_exec": _s.VECTOR_ALLOW_SHELL_EXEC,
    "write_safe_root": _s.VECTOR_WRITE_SAFE_ROOT,
    "allow_private_urls": _s.VECTOR_ALLOW_PRIVATE_URLS,
    "allow_commit_drift": _s.VECTOR_ALLOW_COMMIT_DRIFT,
    "decision_weights": {},     # override keys: goal, conf, policy, urgency, timing, cost
    "hp_tiers": {},             # override keys: elite, strong, healthy, weak
    "llm_pricing": {},          # override per-model pricing for budget tracking
    "vault_path": Path(_s.VECTOR_VAULT_PATH),
    "db_path": _BASE_DIR / "vector_memory.db",
    "db_key": _secret(_s.VECTOR_DB_KEY.get_secret_value()),
    "ollama_host": _normalize_base_url(_s.OLLAMA_HOST),
    # Process-wide bound on concurrent in-flight requests to the Ollama
    # daemon — see OLLAMA_MAX_CONCURRENT field comment on VectorSettings for
    # the full rationale. Consumed by core/inference/ollama_safe.py (sync
    # threading.Semaphore) and core/inference/provider_client.py (async
    # asyncio.Semaphore) — two separate primitives sized off this one number,
    # not one shared lock (see comments at each call site for why).
    "ollama_max_concurrent": _s.OLLAMA_MAX_CONCURRENT,
    "vc_llm_thread_grace_sec": _s.VC_LLM_THREAD_GRACE_SEC,
    "ollama_semaphore_timeout_sec": _s.OLLAMA_SEMAPHORE_TIMEOUT_SEC,
    "vc_llm_loop_guard_strict": _s.VC_LLM_LOOP_GUARD_STRICT,
    "vc_llm_loop_guard_cooldown_sec": _s.VC_LLM_LOOP_GUARD_COOLDOWN_SEC,
    "ssrf_dns_resolve_timeout_sec": _s.SSRF_DNS_RESOLVE_TIMEOUT_SEC,
    "fanout_edge_cooldown_sec": _s.FANOUT_EDGE_COOLDOWN_SEC,
    "candidate_staleness_streak": _s.CANDIDATE_STALENESS_STREAK,
    "correction_penalty_timeout_sec": _s.CORRECTION_PENALTY_TIMEOUT_SEC,
    "allowed_origins": _s.ALLOWED_ORIGINS,
    "cf_worker_url": _s.CF_WORKER_URL,
    "oauth": {
        "github_client_id": _s.OAUTH_GITHUB_CLIENT_ID,
        "github_client_secret": _secret(_s.OAUTH_GITHUB_CLIENT_SECRET.get_secret_value()),
        "google_client_id": _s.OAUTH_GOOGLE_CLIENT_ID,
        "google_client_secret": _secret(_s.OAUTH_GOOGLE_CLIENT_SECRET.get_secret_value()),
    },
    # Sub-configs as plain dicts — all existing CONFIG["x"]["y"] access works
    "models": _s.models.model_dump(),
    "model_router": _s.model_router.model_dump(),
    "api_keys": {
        "anthropic_key":          _secret(_s.ANTHROPIC_KEY.get_secret_value()),
        "gemini_key":             _secret(_s.GEMINI_KEY.get_secret_value()),
        "github_token":           _secret(_s.GITHUB_TOKEN.get_secret_value()),
        "github_username":        _s.GITHUB_USERNAME,
        # Keyring-first: PUSHOVER_TOKEN/PUSHOVER_USER are plain pydantic
        # SecretStr/str fields (env/.env only, no keyring fallback), but
        # scripts/migrate_secrets_to_keyring.py explicitly migrates both of
        # these and documents ".env can be deleted once all secrets are in
        # keyring." Without this fallback, every Pushover call site
        # (permission_gateway.py RED-tier owner approval, emergency
        # escalation, health/security alerts) silently goes dark the moment
        # the owner follows that script's own documented workflow.
        "pushover_token":         _secret(_get_secret("PUSHOVER_TOKEN", _s.PUSHOVER_TOKEN.get_secret_value())),
        "pushover_user":          _get_secret("PUSHOVER_USER", _s.PUSHOVER_USER),
        "supabase_url":           _normalize_supabase_url(_s.SUPABASE_URL),
        "supabase_key":           _secret(_s.SUPABASE_KEY.get_secret_value()),
        "virustotal_key":         _secret(_s.VIRUSTOTAL_KEY.get_secret_value()),
        "newsapi_key":            _secret(_s.NEWSAPI_KEY.get_secret_value()),
        "stripe_key":             _secret(_s.STRIPE_KEY.get_secret_value()),
        "kiit_username":          _s.KIIT_USERNAME,
        "kiit_password":          _secret(_s.KIIT_PASSWORD.get_secret_value()),
        "google_credentials_path": _s.GOOGLE_CREDENTIALS_PATH,
        "youtube_channel_id":     _s.YOUTUBE_CHANNEL_ID,
        "youtube_data_api_key":   _secret(_s.YOUTUBE_DATA_API_KEY.get_secret_value()),
        "instagram_access_token": _secret(_s.INSTAGRAM_ACCESS_TOKEN.get_secret_value()),
        "instagram_account_id":   _s.INSTAGRAM_ACCOUNT_ID,
        "elevenlabs_key":         _secret(_s.ELEVENLABS_KEY.get_secret_value()),
        "elevenlabs_voice_id":    _s.ELEVENLABS_VOICE_ID,
        "openrouter_key":         _secret(_s.OPENROUTER_KEY.get_secret_value()),
        "mistral_key":            _secret(_s.MISTRAL_KEY.get_secret_value()),
        "pagespeed_api_key":      _secret(_s.PAGESPEED_API_KEY.get_secret_value()),
        "hass_url":               _s.HASS_URL,
        "hass_token":             _secret(_s.HASS_TOKEN.get_secret_value()),
        "openai_api_key":         os.environ.get("OPENAI_API_KEY", ""),
        "groq_api_key":           _secret(_s.GROQ_API_KEY.get_secret_value()),
        "xai_api_key":            _secret(_s.XAI_API_KEY.get_secret_value()),
        "minimax_api_key":        _secret(_s.MINIMAX_API_KEY.get_secret_value()),
        "tavily_api_key":         _secret(_s.TAVILY_API_KEY.get_secret_value()),
        "firecrawl_api_key":      _secret(_s.FIRECRAWL_API_KEY.get_secret_value()),
        "honcho_api_key":         _secret(_s.HONCHO_API_KEY.get_secret_value()),
        "deepgram_api_key":       _secret(_s.DEEPGRAM_API_KEY.get_secret_value()),
        "ollama_api_key":         _secret(_s.OLLAMA_API_KEY.get_secret_value()),
        "azure_anthropic_key":    _secret(_s.AZURE_ANTHROPIC_KEY.get_secret_value()),
        "azure_foundry_api_key":  _secret(_s.AZURE_FOUNDRY_API_KEY.get_secret_value()),
        "google_api_key":         _secret(_s.GOOGLE_API_KEY.get_secret_value()),
        "openaicodex_api_key":    _secret(_s.OPENAI_CODEX_API_KEY.get_secret_value()),
        "hindsight_api_key":      _secret(_s.HINDSIGHT_API_KEY.get_secret_value()),
        "browserbase_api_key":    _secret(_s.BROWSERBASE_API_KEY.get_secret_value()),
    },
    "media": {
        "wan2gp_url": _s.WAN2GP_URL,
        "use_lipsync_avatar": False,
        "portrait_image": "",   # set to a portrait photo path to enable lipsync avatar
    },
    "content_niche": _s.CONTENT_NICHE,
    "video_upload_delay_minutes": _s.VIDEO_UPLOAD_DELAY_MINUTES,
    # Top-level aliases so CONFIG.get("pushover_token") works (permission_gateway uses this)
    "pushover_token": _get_secret("PUSHOVER_TOKEN", _s.PUSHOVER_TOKEN.get_secret_value()),
    "pushover_user": _get_secret("PUSHOVER_USER", _s.PUSHOVER_USER),
    "elevenlabs_key": _s.ELEVENLABS_KEY.get_secret_value(),
    "loop": _s.loop.model_dump(),
    "permission": _s.permission.model_dump(),
    "council": _s.council.model_dump(),
    "agent_death_loop": _s.agent_death_loop.model_dump(),
    "cost": _s.cost.model_dump(),
    "personality": _s.personality.model_dump(),
    "resilience": _s.resilience.model_dump(),
    "voice": _s.voice.model_dump(),
    "security": _s.security.model_dump(),
    "siem": _s.siem.model_dump(),
    "control": _s.control.model_dump(),
    "sensing": _s.sensing.model_dump(),
    "coding": {
        "github_token": _s.GITHUB_TOKEN.get_secret_value(),
        "repo_path": _s.coding.repo_path,
    },
    "comms": {
        "local_url": _s.comms.local_url,
        "port": _s.comms.port,
        "timeout_sec": _s.comms.timeout_sec,
        "repo_path": _s.comms.repo_path,
    },
    "turso_url": _normalize_turso_http_url(_s.TURSO_URL or _s.turso.url),
    "turso_token": _s.TURSO_TOKEN.get_secret_value() or _s.turso.token,
    "karpathy": {
        "runs_dir": _s.karpathy.runs_dir,
        "data_dir": _s.karpathy.data_dir,
        "daily_minutes": _s.karpathy.daily_minutes,
    },
    "airllm": {
        "models_dir": _s.airllm.models_dir,
        "cache_dir": _s.airllm.cache_dir,
        "max_gpu_memory_gb": _s.airllm.max_gpu_memory_gb,
    },
    "vectorcode": {
        "enabled": _s.vectorcode.enabled,
        "python_path": _s.vectorcode.python_path,
        "mcp_port": _s.vectorcode.mcp_port,
        "base_url": _s.vectorcode.base_url,
        "timeout_sec": _s.vectorcode.timeout_sec,
    },
    "obsidian": {
        "vault_path": _s.VECTOR_VAULT_PATH,
        "lightrag_working_dir": "./data/lightrag_vault",
        "lightrag_llm_model": "gemma4:e2b",   # plain base model: vector-ambient is a JSON intent classifier + thinking model (empty extraction)
        "watch_debounce_sec": 30,
        "ingest_on_startup": True,
        "protected_paths": ["CLAUDE.md", "GOALS.md", "VECTOR", "graphify-out", ".obsidian"],
        "vector_write_folders": ["Daily", "Reflections", "Council", "Agent HP", "Research", "Interviews", "Journals", "Reviews", "Health", "Finance", "Projects"],
        "personal_write_folders": ["00 Notes", "01 Journals", "02 Projects", "03 Reviews", "04 Skills", "wiki"],
    },
    "vector_finagent": {
        "terminal_binary": str(Path.home() / ".vector" / "vector_finagent" / "FinceptTerminal.exe"),
        "alpha_vantage_key": os.environ.get("ALPHA_VANTAGE_KEY", ""),
        "fred_api_key":      os.environ.get("FRED_API_KEY", ""),
        "polygon_key":       os.environ.get("POLYGON_API_KEY", ""),
        "edgar_api_key":     os.environ.get("EDGAR_API_KEY", ""),
        "data_cache_dir":    str(Path.home() / ".vector" / "vector_finagent" / "cache"),
    },
    # ── Investment Safety Controls ────────────────────────────────────────────
    # CRITICAL: paper_trading=True is the safe default. Set False ONLY after
    # verifying all gateway/kill-switch checks pass. kill_switch=True halts
    # ALL trade execution across every investment district immediately.
    "investment": {
        "paper_trading":       True,    # True = simulate only, never sends real orders
        "kill_switch":         False,   # True = halt ALL execution immediately
        "max_position_size":   10000,   # Maximum position size in ₹ (base currency)
        "daily_loss_cap":      5000,    # Maximum daily loss in ₹ before auto-halt
        "max_trades_per_day":  10,      # Maximum number of live trades per calendar day
    },
    "trading": {
        # Ollama is VECTOR's primary local-first runtime (RULE 11). The trading
        # graph's OpenAI-compatible client routes "ollama" to
        # http://localhost:11434/v1 with no API key required (see
        # core/trading/llm_clients/openai_client.py + api_key_env.py). Leaving
        # this as "openai" broke every analysis with "Missing credentials"
        # since model names below (vector-reasoning/vector-focus) are Ollama
        # custom models, not real OpenAI models.
        "llm_provider":        os.environ.get("TRADING_LLM_PROVIDER", "ollama"),
        "deep_think_llm":      os.environ.get("DEEP_THINK_LLM", "vector-reasoning"),
        "quick_think_llm":     os.environ.get("QUICK_THINK_LLM", "vector-focus"),
        "max_debate_rounds":   1,
        "max_risk_rounds":     1,
        "checkpoint_enabled":  False,
        "output_language":     "English",
        "data_vendors": {
            "core_stock_apis":       "yfinance",
            "technical_indicators":  "yfinance",
            "fundamental_data":      "yfinance",
            "news_data":             "yfinance",
        },
        "results_dir":         str(Path.home() / ".vector" / "trading" / "logs"),
        "cache_dir":           str(Path.home() / ".vector" / "trading" / "cache"),
        "memory_log_path":     str(Path.home() / ".vector" / "trading" / "memory" / "trading_memory.md"),
    },
    "vector_hedgebot": {
        "openai_api_key":       os.environ.get("OPENAI_API_KEY", ""),
        "exa_api_key":          os.environ.get("EXA_API_KEY", ""),
        "jupiter_api_key":      os.environ.get("JUPITER_API_KEY", ""),
        "solana_private_key":   os.environ.get("SOLANA_PRIVATE_KEY", ""),
        "massive_api_key":      os.environ.get("MASSIVE_API_KEY", ""),
        "director_model":       os.environ.get("AUTOHEDGE_DIRECTOR_MODEL", "vector-reasoning"),
        "fast_model":           os.environ.get("AUTOHEDGE_FAST_MODEL", "vector-focus"),
        "output_dir":           str(Path.home() / ".vector" / "vector_hedgebot" / "outputs"),
        "logs_dir":             str(Path.home() / ".vector" / "vector_hedgebot" / "logs"),
        "live_trading":         False,      # set True + SOLANA_PRIVATE_KEY to enable execution
    },
    "vector_backtest": {
        "langchain_provider":  os.environ.get("LANGCHAIN_PROVIDER", "openai"),
        "langchain_model":     os.environ.get("LANGCHAIN_MODEL", "gpt-4.1"),
        "tushare_token":       os.environ.get("TUSHARE_TOKEN", ""),
        "ccxt_exchange":       os.environ.get("CCXT_EXCHANGE", "binance"),
        "token_threshold":     int(os.environ.get("TOKEN_THRESHOLD", "40000")),
        "workspace_dir":       str(Path.home() / ".vector" / "vector_backtest" / "workspace"),
        "memory_dir":          str(Path.home() / ".vector" / "vector_backtest" / "memory"),
        "runs_dir":            str(Path.home() / ".vector" / "vector_backtest" / "runs"),
        "skills_user_dir":     str(Path.home() / ".vector" / "vector_backtest" / "skills"),
        "enable_shell_tools":  False,
    },
    "vector_mlops": {
        "hf_token":          os.environ.get("HF_TOKEN", ""),
        "github_token":      os.environ.get("GITHUB_TOKEN", ""),
        "slack_bot_token":   os.environ.get("SLACK_BOT_TOKEN", ""),
        "slack_channel_id":  os.environ.get("SLACK_CHANNEL_ID", ""),
        "model_name":        os.environ.get("ML_INTERN_MODEL", "anthropic/claude-opus-4-6"),
        "yolo_mode":         False,
        "reasoning_effort":  "high",
        "save_sessions":     True,
        "tool_runtime":      "local",
        "sandbox_enabled":   False,
        "sessions_dir":      str(Path.home() / ".vector" / "vector_mlops" / "sessions"),
    },
    "vector_social_sim": {
        "llm_api_key":          os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", "")),
        "llm_base_url":         os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        "llm_model_name":       os.environ.get("LLM_MODEL_NAME", "gpt-4.1"),
        "llm_boost_api_key":    os.environ.get("LLM_BOOST_API_KEY", ""),
        "llm_boost_base_url":   os.environ.get("LLM_BOOST_BASE_URL", ""),
        "llm_boost_model_name": os.environ.get("LLM_BOOST_MODEL_NAME", ""),
        "zep_api_key":          os.environ.get("ZEP_API_KEY", ""),
        "uploads_dir":          str(Path.home() / ".vector" / "vector_social_sim" / "uploads"),
        "reports_dir":          str(Path.home() / ".vector" / "vector_social_sim" / "reports"),
        "simulations_dir":      str(Path.home() / ".vector" / "vector_social_sim" / "simulations"),
    },
    "smart_routing": {
        "enabled":        True,
        "default_profile": "auto",    # free | eco | auto | premium
        "proxy_port":     8402,
        "cache_ttl_sec":  30,
        "compress_min_chars": 2000,   # min message size to trigger compression
        "confidence_threshold": 0.70, # below this → LLM classifier fallback
    },
    "code_conductor": {
        "max_files":       20,        # max files for orchestrator to read per task
        "similarity_threshold": 0.8,  # git eval hunk match threshold
    },
    "stealth_browser": {
        "port":       9377,
        "api_key":    os.environ.get("STEALTH_BROWSER_API_KEY", ""),
        "admin_key":  os.environ.get("STEALTH_BROWSER_ADMIN_KEY", ""),
        "timeout_sec": 30,
    },
    "browser": {
        # Named Playwright auth profiles (login-once, reuse-later)
        "auth_profiles_dir": os.environ.get(
            "VECTOR_BROWSER_AUTH_DIR",
            str(Path.home() / ".vector" / "browser_auth"),
        ),
        # DOM pruner — max interactive elements kept per observation (18k→~500 tokens)
        "dom_pruner_max_elements": 20,
        # PII scrubber switches
        "pii_scrub_enabled":      True,
        "pii_scrub_screenshot":   True,
        "pii_scrub_network":      True,
        "pii_scrub_console":      True,
        "pii_scrub_replacement":  "[REDACTED]",
        "pii_scrub_patterns":     "",   # empty = all default patterns (excludes noisy generic_hex_token)
        "pii_scrub_audit_report": True,
    },
    "vision_control": {
        "max_loop":  25,
        "factors":   [1000, 1000],   # coordinate normalization (VLM outputs 0-1000 range)
        "loop_interval_sec": 0.5,
    },
    "comfyui": {
        "path": os.environ.get("COMFYUI_PATH", ""),  # Override ComfyUI install path (default: <repo-parent>/ComfyUI)
        "url": os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"),
        "output_dir": os.environ.get("COMFYUI_OUTPUT_DIR", str(Path.home() / ".vector" / "comfyui" / "output")),
        "timeout": 120.0,
        "poll_interval": 1.5,
    },
    "task_queue": {
        "max_concurrent": 8,
    },
    "intent_matcher": {
        "enabled": True,
        "examples_path": "data/intent_examples.json",
        "similarity_threshold": 0.85,
        "embedding_model": "nomic-embed-text",
        "cache_embeddings": True,
    },
    "memory_tree": {
        # A full read/parse/rewrite of the whole tree file on every single
        # EpisodicMemory.store() call was a real ~90+s hang under concurrent
        # writes — these bound the derived MemoryTree index the same way
        # episodic.py's own _memory_buffer is already bounded.
        "max_chunks_per_topic": 2000,
        "save_every_n_ingests": 20,
        "save_interval_seconds": 15,
        "retention_days": 90,
    },
    # Autonomous Growth Engine (districts/growth/). All outward actions gated;
    # nothing publishes or opens signups until the owner flips these on.
    "growth": {
        "enabled": True,                  # master switch — orchestrator no-ops until True (flipped 2026-07-27, owner request)
        "auto_publish": False,            # never auto-post without per-action approval
        "brand_line": "VECTOR — Arghyadeep's personal AI Intelligence",
        "youtube_handle": "VectorSyss",   # @VectorSyss (channel: Arghyadeep Deb)
        "instagram_handle": "vector.syss",
        "instagram_mode": "phone",        # "manual" (human-in-loop) | "graph_api" | "phone" (drive the app on the connected device)
        "youtube_mode": "phone",          # "phone" (drive the app — no OAuth) | "api" (official Data API, needs Google OAuth creds)
        "post_cadence": "daily",
        # Ban-safety (see core/control/social_safety.py). Protects new accounts:
        # warm the account before posting, cap volume, jitter timing so it never
        # looks machine-scheduled. account_created_iso is per-handle in growth state.
        "warmup_days": 10,                # no posting until the account is this old
        "max_posts_per_day": 1,           # hard daily cap per account
        "min_hours_between_posts": 6,     # spacing floor
        "content_dedup_hours": 72,        # refuse to re-post identical media+caption within this window (2026-07-30 audit fix)
        "post_jitter_minutes": 90,        # randomize scheduled time by ±this
        "voice_profile": "bm_george",     # Kokoro JARVIS voice (male — owner rule 2026-07-15)
        "hud_viewport": [1080, 1920],     # 9:16 vertical for Reels/Shorts
        "signup_form_url": "",
        "consent_text": (
            "By signing up you consent to VECTOR storing your email locally "
            "(encrypted) to notify you about the private beta. No data is shared "
            "with third parties. You can request deletion at any time."
        ),
        "review_loop_max_iterations": 5,  # ARM B reviewer↔fix cap before escalation
    },
    # Agency / client ops (districts/agency/wa_assistant.py — WhatsApp Business replies)
    "agency": {
        "wa_autosend": False,           # OFF: VECTOR drafts, owner sends. Keep OFF for
                                        # early clients (a bad auto-reply loses a client).
        "wa_send_tap": [1000, 1830],    # WhatsApp Send-arrow coords; recalibrate if it moves
    },
    "training": _s.training.model_dump(),
    "event_bus": _s.event_bus.model_dump(),
    "research_lab": _s.research_lab.model_dump(),
    "health": {
        "enabled": _s.health.enabled,
        "wearable_poll_interval_minutes": _s.health.wearable_poll_interval_minutes,
        "health_analysis_interval_minutes": _s.health.health_analysis_interval_minutes,
        "emergency_detection_interval_seconds": _s.health.emergency_detection_interval_seconds,
        "pushover_enabled": _s.health.pushover_enabled,
        "retention_days": _s.health.retention_days,
    },
    "emergency": {
        "enabled": _s.emergency.enabled,
        "detector_interval_sec": _s.emergency.detector_interval_sec,
        "pushover_enabled": _s.emergency.pushover_enabled,
        "quiet_hours_start": _s.emergency.quiet_hours_start,
        "quiet_hours_end": _s.emergency.quiet_hours_end,
        "rate_limit_pushover_monthly": _s.emergency.rate_limit_pushover_monthly,
    },
    "code_intel": {
        "project_id":        _s.code_intel.project_id,
        "qdrant_url":        _s.code_intel.qdrant_url,
        "embedding_provider":_s.code_intel.embedding_provider,
        "ollama_url":        _s.code_intel.ollama_url,
        "embedding_model":   _s.code_intel.embedding_model,
        "chunk_size":        _s.code_intel.chunk_size,
        "chunk_overlap":     _s.code_intel.chunk_overlap,
        "max_file_size_mb":  _s.code_intel.max_file_size_mb,
        "dist_path":         _s.code_intel.dist_path,
    },
    "predictive_analytics": {
        "enabled":                    _s.predictive_analytics.enabled,
        "forecast_interval_minutes":  _s.predictive_analytics.forecast_interval_minutes,
        "simulation_interval_minutes":_s.predictive_analytics.simulation_interval_minutes,
        "retention_days":             _s.predictive_analytics.retention_days,
        "pushover_enabled":           _s.predictive_analytics.pushover_enabled,
        "max_metrics":                _s.predictive_analytics.max_metrics,
    },
    "ads": {
        "scripts_path":          _s.ads.scripts_path,
        "references_path":       _s.ads.references_path,
        "templates_path":        _s.ads.templates_path,
        "image_provider_order":  _s.ads.image_provider_order,
        "pdf_output_dir":        _s.ads.pdf_output_dir,
        "screenshot_dir":        _s.ads.screenshot_dir,
        "max_concurrent_audits": _s.ads.max_concurrent_audits,
        "gemini_key":            os.environ.get("GEMINI_API_KEY", ""),
        "openai_key":            os.environ.get("OPENAI_API_KEY", ""),
        "stability_key":         os.environ.get("STABILITY_API_KEY", ""),
        "replicate_key":         os.environ.get("REPLICATE_API_TOKEN", ""),
        "pagespeed_key":         _s.PAGESPEED_API_KEY.get_secret_value(),
    },
    "home_assistant": _s.home_assistant.model_dump(),
    # ── Collections engine (PocketBase absorption) ───────────────────────────
    "collections": {
        "enabled": os.environ.get("VECTOR_COLLECTIONS_ENABLED", "1") in ("1", "true", "True"),
        "storage": {
            "backend":       os.environ.get("VECTOR_COLLECTIONS_BACKEND", "local"),  # local | s3
            "local_root":    os.environ.get("VECTOR_COLLECTIONS_ROOT",
                                            str(Path(_s.VECTOR_HOME) / "collections_files")),
            "s3_bucket":     os.environ.get("VECTOR_S3_BUCKET", ""),
            "s3_region":     os.environ.get("VECTOR_S3_REGION", ""),
            "s3_endpoint":   os.environ.get("VECTOR_S3_ENDPOINT", ""),
            "s3_access_key": os.environ.get("VECTOR_S3_ACCESS_KEY", ""),
            "s3_secret_key": os.environ.get("VECTOR_S3_SECRET_KEY", ""),
            "s3_public_base": os.environ.get("VECTOR_S3_PUBLIC_BASE", ""),
        },
        "jwt": {
            "secret":          _s.VECTOR_JWT_SECRET.get_secret_value(),
            "access_ttl_sec":  int(os.environ.get("VECTOR_JWT_ACCESS_TTL", "900")),
            "refresh_ttl_sec": int(os.environ.get("VECTOR_JWT_REFRESH_TTL", "1209600")),
        },
    },
    "knowledge": {
        # Output directory for domain-context.json and assembled-graph.json files
        "output_dir": os.environ.get("VECTOR_KNOWLEDGE_OUTPUT_DIR",
                                     str(Path(_s.VECTOR_HOME) / "knowledge_graphs")),
        # Maximum output JSON size in bytes (default 512 KB)
        "max_output_bytes": int(os.environ.get("VECTOR_KNOWLEDGE_MAX_BYTES", str(512 * 1024))),
        # Karpathy wiki root (Obsidian brain vault)
        "wiki_root": os.environ.get("VECTOR_WIKI_ROOT",
                                    str(Path(_s.VECTOR_HOME).parent / "V.E.C.T.O.R. Brain")),
    },
    # ── Sidecar app paths ─────────────────────────────────────────────────────
    # These apps have no pip/npm package; they must be cloned locally.
    # Defaults point to <codebase-parent>/GitHub/<AppName> — the conventional
    # layout used when all repos live next to each other.
    # Override any path via the corresponding env var or .env key so that the
    # cloned repos can live anywhere (or be deleted entirely — VECTOR silently
    # skips sidecars whose directory does not exist).
    #
    #   VECTOR_COMFYUI_PATH     — ComfyUI clone    (python main.py)
    #   VECTOR_HYPERFRAMES_PATH — hyperframes clone (node packages/producer/dist/server.js)
    "sidecars": {
        "comfyui_path":     _s.VECTOR_COMFYUI_PATH or _s.sidecars.comfyui_path,
        "hyperframes_path": _s.VECTOR_HYPERFRAMES_PATH or _s.sidecars.hyperframes_path,
    },
}

# ── Afterburner: inject CONFIG values into os.environ for absorbed code ──────
# vectorcode/src/ legacy imports use os.getenv() directly (~1500 calls).
# Instead of editing 330+ files, we pre-populate os.environ with CONFIG values
# at startup. Existing os.getenv() calls automatically pick up CONFIG settings.
# Shell env takes precedence (setdefault, not set).

_CFG = CONFIG  # local alias for lazy closures


def _resolve_cfg(path: str, default: str = "") -> str:
    """Resolve a dotted CONFIG path like 'api_keys.anthropic_key' to a value."""
    val: object = _CFG
    for part in path.split("."):
        if isinstance(val, dict):
            val = val.get(part, default)
        else:
            return default
    if isinstance(val, str):
        return val
    if isinstance(val, bool):
        return "1" if val else "0"
    return default


# Maps: target env var name → CONFIG dotted path
_ENV_ALIASES: dict[str, str] = {
    # Naming mismatches: CONFIG uses shorter keys, vectorcode/src/ uses _API_KEY suffix
    "ANTHROPIC_API_KEY":     "api_keys.anthropic_key",
    "GEMINI_API_KEY":        "api_keys.gemini_key",
    "MISTRAL_API_KEY":       "api_keys.mistral_key",
    "OPENROUTER_API_KEY":    "api_keys.openrouter_key",
    "ELEVENLABS_API_KEY":    "api_keys.elevenlabs_key",
    "OPENAI_API_KEY":        "api_keys.openai_api_key",
    "GROQ_API_KEY":          "api_keys.groq_api_key",
    "XAI_API_KEY":           "api_keys.xai_api_key",
    "MINIMAX_API_KEY":       "api_keys.minimax_api_key",
    "TAVILY_API_KEY":        "api_keys.tavily_api_key",
    "FIRECRAWL_API_KEY":     "api_keys.firecrawl_api_key",
    "HONCHO_API_KEY":        "api_keys.honcho_api_key",
    "DEEPGRAM_API_KEY":      "api_keys.deepgram_api_key",
    "OLLAMA_API_KEY":        "api_keys.ollama_api_key",
    "AZURE_ANTHROPIC_KEY":   "api_keys.azure_anthropic_key",
    "AZURE_FOUNDRY_API_KEY": "api_keys.azure_foundry_api_key",
    "GOOGLE_API_KEY":        "api_keys.google_api_key",
    "OPENAI_CODEX_API_KEY":  "api_keys.openaicodex_api_key",
    "HINDSIGHT_API_KEY":     "api_keys.hindsight_api_key",
    "BROWSERBASE_API_KEY":   "api_keys.browserbase_api_key",
    # Runtime vars with different CONFIG key names
    "VECTOR_HOME":            "vector_home",
    "VECTOR_TIMEZONE":        "vector_timezone",
    "VECTOR_ALLOW_SHELL_EXEC":"allow_shell_exec",
    "VECTOR_WRITE_SAFE_ROOT": "write_safe_root",
    "VECTOR_ALLOW_PRIVATE_URLS": "allow_private_urls",
    "VECTOR_ALLOW_COMMIT_DRIFT": "allow_commit_drift",
    "VECTOR_DB_KEY":          "db_key",
    # Duplicate api_keys entries with top-level keys for broad coverage
    "GITHUB_TOKEN":           "api_keys.github_token",
    "ELEVENLABS_KEY":         "api_keys.elevenlabs_key",
    "HASS_TOKEN":             "api_keys.hass_token",
    "HASS_URL":               "api_keys.hass_url",
    "NEWSAPI_KEY":            "api_keys.newsapi_key",
    "VIRUSTOTAL_KEY":         "api_keys.virustotal_key",
    "STRIPE_KEY":             "api_keys.stripe_key",
    "SUPABASE_KEY":           "api_keys.supabase_key",
    "PUSHOVER_TOKEN":         "api_keys.pushover_token",
    "PUSHOVER_USER":          "api_keys.pushover_user",
    "INSTAGRAM_ACCESS_TOKEN":  "api_keys.instagram_access_token",
    "KIIT_USERNAME":          "api_keys.kiit_username",
    "KIIT_PASSWORD":          "api_keys.kiit_password",
    "PAGESPEED_API_KEY":      "api_keys.pagespeed_api_key",
    "ELEVENLABS_VOICE_ID":    "api_keys.elevenlabs_voice_id",
    "YOUTUBE_CHANNEL_ID":     "api_keys.youtube_channel_id",
    "YOUTUBE_DATA_API_KEY":   "api_keys.youtube_data_api_key",
    "INSTAGRAM_ACCOUNT_ID":   "api_keys.instagram_account_id",
}


def inject_env() -> None:
    """Populate os.environ with CONFIG values. Uses setdefault so shell env wins."""
    for env_key, cfg_path in _ENV_ALIASES.items():
        val = _resolve_cfg(cfg_path)
        if val:
            os.environ.setdefault(env_key, val)


inject_env()

# ── Helpers ────────────────────────────────────────────────────────────────────

def get(key: str, default=None):
    return CONFIG.get(key, default)


def print_status() -> None:
    logger.info(f"Owner: {CONFIG['owner_name']}")
    logger.info(f"Environment: {CONFIG['env']}")
    logger.info(f"Ollama Host: {CONFIG['ollama_host']}")
    non_empty = sum(1 for v in CONFIG["api_keys"].values() if v)
    logger.info(f"Non-empty API keys: {non_empty}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print_status()
    # Validate all sub-model types are correct
    assert isinstance(CONFIG["loop"]["observe_interval_sec"], float)
    assert isinstance(CONFIG["permission"]["green"], list)
    assert isinstance(CONFIG["voice"]["sample_rate"], int)
    assert isinstance(CONFIG["models"]["focus"], str)
    assert "pushover_token" in CONFIG
    assert "allowed_origins" in CONFIG
    assert "obsidian" in CONFIG
    assert "write_note_personal" in CONFIG["permission"]["yellow"]
    assert "overwrite_note_personal" in CONFIG["permission"]["red"]
    print("✅ config.py OK")
