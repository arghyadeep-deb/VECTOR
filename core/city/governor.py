import sys
import asyncio
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


# RED-tier task types that require LLM Council review before execution.
# Mirrors the RED permission tier in critical_rules.md.
_COUNCIL_TASK_TYPES: frozenset[str] = frozenset({
    "push_github",
    "deploy_production",
    "delete_files",
    "financial_transaction",
    "send_email",
    "execute_code",
    "overwrite_note_personal",
    "create_pr",
})

DISTRICT_TASK_MAP: dict[str, str] = {
    "code": "coding",
    "git": "coding",
    "git_status": "coding",
    "review": "coding",
    "bug": "coding",
    "refactor": "coding",
    "architect": "coding",
    # coding_assistant tools (core/coding_assistant/)
    "search_replace": "coding",
    "apply_patch": "coding",
    "bash_execute": "coding",
    "run_command": "coding",
    "grep_code": "coding",
    "grep_search": "coding",
    "read_file_tool": "coding",
    "write_file_tool": "coding",
    "write_code": "coding",
    "read_code": "coding",
    "todo_add": "coding",
    "todo_list": "coding",
    "file_edit": "coding",
    "code_search": "coding",
    "load_skill": "coding",
    "skill_run": "coding",
    # core/jcode/ tools (ported from high-performance agent harness)
    "multiedit": "coding",
    "multi_edit": "coding",
    "apply_patch": "coding",
    "cache_tracker": "coding",
    "kv_cache": "coding",
    # ambient scheduler (core/jcode/ambient_scheduler.py)
    "ambient": "governance",
    "directive": "governance",
    "schedule_task": "governance",
    "ambient_status": "governance",
    # session persistence (core/jcode/session_persistence.py)
    "session_persist": "memory_curator",
    "recover_session": "memory_curator",
    "session_recovery": "memory_curator",
    # core/audit/ — Merkle audit chain
    "audit_log": "governance",
    "audit_verify": "governance",
    "audit_search": "governance",
    "audit_tail": "governance",
    # core/metering/ — budget + rate limiting
    "budget_check": "governance",
    "budget_status": "governance",
    "rate_check": "governance",
    "budget_record": "governance",
    # core/security/ — injection, SSRF, taint
    "scan_prompt": "security",
    "ssrf_check": "security",
    "taint_check": "security",
    "security_scan": "security",
    "check_url": "security",
    # core/memory/knowledge_graph.py
    "knowledge_add": "memory_curator",
    "knowledge_query": "memory_curator",
    "knowledge_relate": "memory_curator",
    "entity_add": "memory_curator",
    "relation_add": "memory_curator",
    # core/loop/loop_guard.py
    "loop_status": "governance",
    "session_repair": "governance",
    # agents/hands/ — autonomous hands
    "hand_run": "governance",
    "hand_status": "governance",
    "hand_enable": "governance",
    "hand_disable": "governance",
    "hand_list": "governance",
    "calendar": "time_calendar",
    "schedule": "time_calendar",
    "deadline": "time_calendar",
    "kiit": "time_calendar",
    "attendance": "time_calendar",
    "check_attendance": "time_calendar",
    "class": "time_calendar",
    "message": "communications",
    "email": "communications",
    "notify": "communications",
    "whatsapp": "communications",
    "vectorcode_comms": "communications",
    "vectorcode": "communications",
    "search": "research",
    "research": "research",
    "paper": "research",
    "search_arxiv": "research",
    "search_web": "research",
    "daily_digest": "research",
    "news": "research",
    "find": "research",
    # core/scraper/ — VECTOR web scraper (adaptive, stealth, spider)
    "scrape": "research",
    "scrape_url": "research",
    "scrape_stealth": "research",
    "web_scrape": "research",
    "crawl": "research",
    "spider_crawl": "research",
    "fetch_page": "research",
    "fetch_stealth": "research",
    "fetch_dynamic": "research",
    "smart_fetch": "research",
    "html_to_markdown": "research",
    "parse_html": "research",
    "batch_scrape": "research",
    "threat": "security",
    "malware": "security",
    "security": "security",
    "scan": "security",
    "memory": "memory_curator",
    "remember": "memory_curator",
    "recall": "memory_curator",
    "consolidate": "memory_curator",
    "vote": "governance",
    "council": "governance",
    "decision": "governance",
    "health": "health",
    "sleep": "health",
    "fatigue": "health",
    "check_fatigue": "health",
    "finance": "finance",
    "budget": "finance",
    "money": "finance",
    "monthly_report": "finance",
    "learn": "learning",
    "video": "learning",
    "course": "learning",
    "daily_review": "reflection",
    "reflect": "reflection",
    "journal": "reflection",
    "project": "projects",
    "deadline_check": "projects",
    "progress": "projects",
    # Trading intelligence (multi-agent investment analysis)
    "investment_analysis":  "investment",
    "trading_analysis":     "investment",
    "market_research":      "investment",
    # Fincept financial intelligence suite
    "investor_analysis":    "investment",
    "corporate_finance":    "investment",
    "alpha_discovery":      "investment",
    "geopolitics_analysis": "investment",
    "quant_backtest":       "investment",
    "launch_terminal":      "investment",
    # VECTOR Hedge — autonomous multi-agent hedge fund pipeline
    "hedge_run":            "investment",
    "hedge_trade":          "investment",
    "solana_order":         "investment",
    "solana_execute":       "investment",
    "solana_holdings":      "investment",
    "token_search":         "investment",
    "token_price":          "investment",
    # VECTOR Quant Research — 9-engine backtest, shadow account, 29 swarm presets, 74 skills
    "vt_research":          "investment",
    "vt_backtest":          "investment",
    "shadow_account":       "investment",
    "vt_swarm":             "investment",
    "vt_skills":            "investment",
    "vt_export":            "investment",
    # Code conductor (multi-agent coding orchestrator)
    "code_conduct":         "coding",
    "code_map":             "coding",
    "code_accuracy_test":   "coding",
    "str_replace":          "coding",
    # Stealth browser (anti-detection research)
    "stealth_scrape":     "research",
    "stealth_search":     "research",
    "youtube_transcript": "research",
    "stealth_snapshot":   "research",
    # Vision control (VLM-driven GUI automation)
    "gui_task":        "coding",
    "vision_control":  "coding",
    "desktop_task":    "coding",
    "click_screen":    "coding",
    "browser_task":    "coding",
    "web_task":        "coding",
    "image": "content",
    "generate_image": "content",
    "generate_i2i": "content",
    "generate_video": "content",
    "animate_image": "content",
    "lipsync": "content",
    "lip_sync": "content",
    "background_remove": "content",
    "upscale": "content",
    "media_status": "content",
    "comfyui": "content",
    "script": "content",
    # SEO / marketing routes (toprank absorption)
    "seo_audit":            "marketing",
    "seo_analysis":         "marketing",
    "seo_portfolio":        "marketing",
    "seo_onboard":          "marketing",
    "seo_weekly_review":    "marketing",
    "seo_improve_page":     "marketing",
    "seo_portfolio_review": "marketing",
    "seo_investigate_drop": "marketing",
    "keyword_research":     "marketing",
    "broken_links":         "marketing",
    "pagespeed":            "marketing",
    "schema_markup":        "marketing",
    "geo_optimize":         "marketing",
    "url_inspect":          "marketing",
    "url_inspection":       "marketing",
    "cms_push_seo":         "marketing",
    "seo_followup":         "marketing",
    # Google Ads routes
    "google_ads_audit":     "marketing",
    "google_ads":           "marketing",
    "google_ads_copy":      "marketing",
    "google_ads_landing":   "marketing",
    "ads_performance":      "marketing",
    "ads_keywords":         "marketing",
    "ads_copy":             "marketing",
    # Meta Ads routes
    "meta_ads_audit":       "marketing",
    "meta_ads":             "marketing",
    "meta_ads_performance": "marketing",
    "meta_ads_creative":    "marketing",
    "meta_ads_audience":    "marketing",
    "ads_meta":             "marketing",
    "make_video": "content",
    "create_video": "content",
    "upload_video": "content",
    "video_pipeline": "content",
    "daily_video": "content",
    "website_to_video": "content",
    "url_capture": "content",
    "site_video": "content",
    "title_card": "content",
    "data_viz": "content",
    "render_html": "content",
    "remove_bg": "content",
    "background_remove": "content",
    # ops
    "slo": "ops",
    "uptime": "ops",
    "incident": "ops",
    "deploy": "ops",
    "devops": "ops",
    "monitor_system": "ops",
    "backup": "ops",
    "restart": "ops",
    "post_mortem": "ops",
    # data_analytics
    "analytics": "data_analytics",
    "benchmark": "data_analytics",
    "metrics": "data_analytics",
    "performance_report": "data_analytics",
    # personal_growth
    "nudge": "personal_growth",
    "motivation": "personal_growth",
    "zettelkasten": "personal_growth",
    "zk": "personal_growth",
    "knowledge_links": "personal_growth",
    # documentation
    "write_docs": "documentation",
    "api_reference": "documentation",
    "changelog": "documentation",
    "weekly_summary": "documentation",
    "generate_doc": "documentation",
    # qa
    "reality_check": "qa",
    "evidence": "qa",
    "map_workflow": "qa",
    "verify_output": "qa",
    "qa_check": "qa",
    # chief_of_staff
    "executive_brief": "chief_of_staff",
    "morning_brief": "chief_of_staff",
    "evening_brief": "chief_of_staff",
    "chief": "chief_of_staff",
    "coordinate": "chief_of_staff",
    # new coding agents
    "frontend": "coding",
    "dashboard_build": "coding",
    "scaffold_component": "coding",
    "db_optimize": "coding",
    "slow_query": "coding",
    "index": "coding",
    # deep research engine (core/research_engine/)
    "deep_research": "research",
    "research_report": "research",
    "generate_report": "research",
    "research_papers": "research",
    "research_news": "research",
    "research_quick": "research",
    "arxiv": "research",
    "pubmed": "research",
    "semantic_scholar": "research",
    "academic_search": "research",
    "find_papers": "research",
    "literature_review": "research",
    "market_research": "research",
    "deep_dive": "research",
    # email intelligence + email agent (agentic-inbox)
    "email_brief": "communications",
    "gmail": "communications",
    "parse_email": "communications",
    "list_emails": "communications",
    "get_email": "communications",
    "read_email": "communications",
    "draft_reply": "communications",
    "draft_email": "communications",
    "send_email": "communications",
    "email_thread": "communications",
    "email_search": "communications",
    "check_inbox": "communications",
    "new_email": "communications",
    "auto_draft": "communications",
    # qa additions
    "test_analysis": "qa",
    "api_health": "qa",
    "api_test": "qa",
    # interview_prep additions
    "recruitment": "interview_prep",
    "placement": "interview_prep",
    "job_search": "interview_prep",
    "resume": "interview_prep",
    "cold_outreach": "interview_prep",
    # personal_growth additions
    "feedback": "personal_growth",
    "synthesize_feedback": "personal_growth",
    # projects additions
    "experiment": "projects",
    "ab_test": "projects",
    "hypothesis": "projects",
    # marketing district (new)
    "seo": "marketing",
    "keyword": "marketing",
    "optimize_content": "marketing",
    "growth": "marketing",
    "viral_loop": "marketing",
    "north_star": "marketing",
    "funnel": "marketing",
    "social_media": "marketing",
    "linkedin": "marketing",
    "twitter": "marketing",
    "content_creator": "marketing",
    "editorial_calendar": "marketing",
    "newsletter": "marketing",
    "blog": "marketing",
    "ai_citation": "marketing",
    "aeo": "marketing",
    "agentic_search": "marketing",
    # design district (new)
    "ui_design": "design",
    "design_tokens": "design",
    "component": "design",
    "ux_research": "design",
    "persona": "design",
    "journey_map": "design",
    "image_prompt": "design",
    "comfyui_prompt": "design",
    "sd_prompt": "design",
    # coding additions
    "minimal_change": "coding",
    "minimal_diff": "coding",
    "onboard_repo": "coding",
    "repo_scan": "coding",
    "rapid_prototype": "coding",
    "mvp": "coding",
    "prototype": "coding",
    # security additions
    "threat_detection": "security",
    "sigma_rule": "security",
    "mitre_attack": "security",
    "siem": "security",
    # data_analytics additions
    "data_pipeline": "data_analytics",
    "etl": "data_analytics",
    "data_contract": "data_analytics",
    "data_quality": "data_analytics",
    "data_remediation": "data_analytics",
    # qa additions
    "accessibility": "qa",
    "wcag": "qa",
    "tool_evaluate": "qa",
    "workflow_optimize": "qa",
    "model_qa": "qa",
    "ml_audit": "qa",
    # finance additions
    "dcf": "finance",
    "valuation": "finance",
    "scenario_analysis": "finance",
    "break_even": "finance",
    "fpa": "finance",
    "variance": "finance",
    "forecast": "finance",
    # agency additions
    "sales": "agency",
    "pipeline": "agency",
    "qualify_lead": "agency",
    "proposal": "agency",
    "roi": "agency",
    "outreach": "agency",
    # governance additions
    "prd": "governance",
    "roadmap": "governance",
    "rice_score": "governance",
    "product_brief": "governance",
    "credentials": "governance",
    "api_keys": "governance",
    "provider_scan": "governance",
    "autopilot": "governance",
    "chain": "governance",
    "auto_chain": "governance",
    "nexus": "governance",
    "federation": "governance",
    "delegate_task": "governance",
    "broadcast": "governance",
    "mcp_stdio": "governance",
    # finance additions (vectorcode_llm)
    "llm_cost": "finance",
    "token_usage": "finance",
    "cost_report": "finance",
    "budget_alert": "finance",
    # memory_curator additions
    "compress_context": "memory_curator",
    "context_compress": "memory_curator",
    "prune_context": "memory_curator",
    # security additions (vectorcode_llm)
    "redact": "security",
    "pii_check": "security",
    "cloud_safety": "security",
    "data_redact": "security",
    # ops additions
    "classify_error": "ops",
    "error_type": "ops",
    "retry_check": "ops",
    # prompt-agent backed district additions
    "refactor": "coding",
    "dead_code": "coding",
    "cleanup": "coding",
    "silent_failure": "qa",
    "swallowed_error": "qa",
    "code_review_addy": "coding",
    "code_review_obra": "coding",
    "explore_code": "coding",
    "explain_file": "coding",
    "optimize": "data_analytics",
    "profile": "data_analytics",
    "bottleneck": "data_analytics",
    "write_tests": "qa",
    "test_coverage": "qa",
    "tdd": "qa",
    "compliance": "governance",
    "gdpr": "governance",
    "sox": "governance",
    "developer_advocate": "coding",
    "ttfhw": "coding",
    "dx_audit": "coding",
    "tutorial": "coding",
}


class Governor:
    """
    VECTOR's task orchestrator. Routes tasks to the right district agent.
    RULE 9 — HP wired to actual outcomes: success → +50 HP, failure → -30 HP.
    Never crashes — every exception caught internally.
    """

    def __init__(self):
        self._registry = None
        self._memory = None
        self._active_tasks: dict[str, dict] = {}
        logger.info("[VECTOR][governor] initialized")

    def _get_registry(self):
        if self._registry is None:
            from core.city.agent_registry import get_registry
            self._registry = get_registry()
        return self._registry

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def route_task(self, task_type: str) -> str:
        """Determine which district should handle this task type.
        First tries keyword matching (fast, free). Falls back to LLM classification."""
        task_lower = task_type.lower()
        for keyword, district in DISTRICT_TASK_MAP.items():
            if keyword in task_lower:
                return district
        # LLM fallback for natural language task types
        return self._llm_classify(task_type)

    def _llm_classify(self, task_type: str) -> str:
        """Use vector-ambient (fast, local) to classify task into a district."""
        try:
            from core.inference.ollama_safe import chat
            from core.config import CONFIG
            # RULE 1: session_hydration_prompt() before every LLM call
            try:
                from core.loop.context_engine import ContextEngine
                hydration = ContextEngine().session_hydration_prompt()
            except Exception:
                hydration = ""
            districts = list(set(DISTRICT_TASK_MAP.values()))
            prompt = (
                f"Classify this task into exactly one district name from this list: {districts}\n"
                f"Task: {task_type}\n"
                "Reply with only the district name, nothing else."
            )
            messages = []
            if hydration:
                messages.append({"role": "system", "content": hydration})
            messages.append({"role": "user", "content": prompt})
            result = chat(
                model=CONFIG["models"]["ambient"],
                messages=messages,
                timeout=5.0,
            ).strip().lower()
            # Validate the response is a known district
            if result in districts:
                logger.info(f"[VECTOR][governor] LLM classified '{task_type}' → {result}")
                return result
        except Exception as e:
            logger.warning(f"[VECTOR][governor] LLM classify failed: {e}")
        logger.warning(f"[VECTOR][governor] unknown task '{task_type}' → defaulting to research")
        return "research"

    async def _should_convene_council(self, task: dict) -> bool:
        """Return True if this task type warrants LLM Council review (RED-tier actions only)."""
        return task.get("type", "") in _COUNCIL_TASK_TYPES

    async def _run_council_review(self, task: dict, agent) -> dict | None:
        """Convene the LLM Council for a high-stakes task.

        Returns the verdict dict on success, or None if the council is
        unavailable (import error, timeout, any exception).  The caller
        MUST NOT block task execution on a None return.
        """
        try:
            from agents.districts.governance.llm_council import LLMCouncil
            council = LLMCouncil()
            hp = agent.health_points if agent else 500
            result = await council.convene(
                question=(
                    f"Should VECTOR execute this task: {task.get('type')} "
                    f"with params {task.get('params', {})}?"
                ),
                stakes="high",
                requester_hp=hp,
            )
            logger.info(
                f"[VECTOR][governor] Council verdict for {task.get('type')}: "
                f"{str(result.get('verdict', ''))[:80]}"
            )
            return result
        except Exception as e:
            logger.warning(
                f"[VECTOR][governor] Council review failed: {e} — proceeding without review"
            )
            return None

    async def dispatch(self, task: dict) -> dict:
        """
        Dispatch task to appropriate district agent.
        RULE 9 — HP wired to actual outcome after every dispatch.
        """
        task_id = f"task_{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"
        task_type = task.get("type", "unknown")
        district = task.get("district") or self.route_task(task_type)

        logger.info(f"[VECTOR][governor] dispatch {task_id} → {district} ({task_type})")

        # ── Rate limit check (GCRA per district, 500 tokens/min) ────────────────
        try:
            from core.metering.rate_limiter import get_rate_limiter
            rl = get_rate_limiter()
            allowed, wait_ms = rl.check(f"district_{district}", "tool_call")
            if not allowed:
                logger.warning(
                    "[VECTOR][governor] rate limit hit district={} wait={:.0f}ms",
                    district, wait_ms,
                )
                if wait_ms > 10_000:
                    return {"status": "rate_limited", "wait_ms": wait_ms,
                            "district": district, "task_id": task_id}
        except Exception:
            pass

        # ── Taint tracking — tag and check user-supplied content ──────────────
        task_content = str(task.get("params", {}).get("content", ""))
        if task_content:
            try:
                from core.security.taint_tracker import get_taint_tracker, TaintLabel, TaintSink
                tt = get_taint_tracker()
                tainted = tt.tag_user(task_content)
                # Check before shell/network sinks
                if task_type in ("bash", "shell", "exec", "run_code"):
                    v = tt.check_sink(tainted, TaintSink.SHELL_EXEC)
                    if v:
                        logger.warning("[VECTOR][governor] taint violation task={}: {}", task_id, v)
                elif task_type in ("web_fetch", "scrape", "crawl"):
                    v = tt.check_sink(tainted, TaintSink.NET_FETCH)
                    if v:
                        logger.warning("[VECTOR][governor] taint violation task={}: {}", task_id, v)
            except Exception:
                pass

        # ── Prompt injection scan ─────────────────────────────────────────────
        if task_content:
            try:
                from core.security.prompt_injection import scan_text
                scan_result = scan_text(task_content, context=f"governor.{task_type}")
                if not scan_result.clean:
                    logger.warning(
                        f"[VECTOR][governor] prompt injection blocked task {task_id}: {scan_result}"
                    )
                    return {"status": "blocked", "reason": "prompt_injection", "task_id": task_id, "district": district}
            except Exception:
                pass

        # ── Budget check before dispatch (non-blocking — just warns) ──────────
        try:
            from core.metering.budget_meter import get_budget_meter
            meter = get_budget_meter()
            allowed, budget_reason = meter.check_quota(f"district_{district}")
            if not allowed:
                logger.warning(f"[VECTOR][governor] budget warning for {district}: {budget_reason}")
        except Exception:
            pass

        # Audit log — record dispatch
        try:
            from core.audit.merkle_chain import get_audit_chain
            get_audit_chain().log(
                agent_id=f"governor_{district}",
                action="dispatch",
                district=district,
                payload={"task_type": task_type, "task_id": task_id},
            )
        except Exception:
            pass

        # OTel: open a trace span for this dispatch
        try:
            from core.engine.telemetry.otel_bridge import get_telemetry
            _tel = get_telemetry()
            _span_ctx = _tel.span(f"governor.dispatch.{district}",
                                  {"task_type": task_type, "district": district, "task_id": task_id})
            _span_ctx.__enter__()
        except Exception:
            _span_ctx = None

        self._active_tasks[task_id] = {
            "task": task,
            "district": district,
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        result: dict = {}
        agent = None

        try:
            # ── Council review for RED-tier task types ────────────────────────────
            # Must happen BEFORE we touch any agent so we can pass the best-HP
            # agent to the council (or fall back to hp=500 if no agents yet).
            # Council failure / timeout never blocks execution — task proceeds.
            if await self._should_convene_council(task):
                _pre_agents = self._get_registry().get_by_district(district)
                _council_agent = max(_pre_agents, key=lambda a: a.health_points) if _pre_agents else None
                council_result = await self._run_council_review(task, _council_agent)
                if council_result:
                    verdict = council_result.get("verdict", "")
                    confidence = float(council_result.get("confidence", 0.5))
                    task.setdefault("params", {})["council_verdict"] = verdict
                    task["params"]["council_confidence"] = confidence
                    if confidence < 0.4:
                        logger.warning(
                            f"[VECTOR][governor] Council rejected '{task_type}' "
                            f"(confidence={confidence:.2f} < 0.4) — proceeding with caution"
                        )
                    else:
                        logger.info(
                            f"[VECTOR][governor] Council approved '{task_type}' "
                            f"(confidence={confidence:.2f}): {str(verdict)[:60]}"
                        )

            agents = self._get_registry().get_by_district(district)

            if not agents:
                logger.warning(f"[VECTOR][governor] no agents in {district}")
                result = {"status": "no_agents", "district": district}
            else:
                agent = max(agents, key=lambda a: a.health_points)

                if hasattr(agent, "run"):
                    result = await agent.run(task)
                else:
                    result = {"status": "stub", "agent": agent.name}

            # RULE 9 — HP wired to actual task outcomes
            if agent is not None:
                if result.get("status") == "ok":
                    agent.award_points(50, "task_completed_by_governor")
                elif result.get("status") in ("error", "failed"):
                    agent.deduct_points(30, "task_failed_by_governor")

            self._get_memory().store(
                event_type="governor_dispatch",
                content=f"type={task_type} district={district} status={result.get('status')}",
                tags=["governor", district, task_type],
                source="governor",
            )

        except Exception as e:
            logger.error(f"[VECTOR][governor] dispatch error {task_id}: {e}")
            # Sentry: capture with district + task context
            try:
                from core.engine.telemetry.sentry_bridge import init_sentry
                init_sentry().capture_exception(e, context={
                    "task_id": task_id, "task_type": task_type,
                    "district": district, "component": "governor.dispatch",
                })
            except Exception:
                pass
            if agent is not None:
                agent.deduct_points(30, "exception_during_task")
            result = {"status": "error", "error": str(e)}
        finally:
            self._active_tasks.pop(task_id, None)
            # Close OTel span
            if _span_ctx is not None:
                try:
                    _span_ctx.__exit__(None, None, None)
                except Exception:
                    pass

        return {**result, "task_id": task_id, "district": district}

    def get_active_tasks(self) -> list[dict]:
        return list(self._active_tasks.values())

    def get_district_summary(self) -> dict:
        """Agent count and avg HP per district."""
        reg = self._get_registry()
        summary = {}
        for district, count in reg.count_by_district().items():
            agents = reg.get_by_district(district)
            if agents:
                avg_hp = sum(a.health_points for a in agents) / len(agents)
                summary[district] = {"agents": count, "avg_hp": round(avg_hp)}
        return summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from core.city.agent_base import AgentBase
    from core.city.agent_registry import get_registry

    reg = get_registry()
    a = AgentBase("gov_test_001", "CodeBot", "coding")
    reg.register(a)

    gov = Governor()
    route = gov.route_task("review my git code")
    result = asyncio.run(gov.dispatch({"type": "code_review", "file": "core/main.py"}))
    summary = gov.get_district_summary()

    ok = route == "coding" and "task_id" in result and "coding" in summary
    print(
        f"✅ governor OK — route={route}, "
        f"dispatch status={result.get('status')}, districts={len(summary)}"
        if ok else "❌ FAILED"
    )
