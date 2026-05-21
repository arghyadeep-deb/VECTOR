"""VECTOR local launcher.

This is the single command entrypoint for the local VECTOR spine. It can run a
quick smoke check, start the autonomous loop, or launch the FastAPI server.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger

# ── Telemetry init (Sentry + OpenTelemetry) — must happen before anything else ──
def _init_telemetry() -> None:
    try:
        from core.engine.telemetry.sentry_bridge import init_sentry
        from core.engine.telemetry.otel_bridge import get_telemetry
        sentry = init_sentry()
        sentry.set_user("arghyadeep-deb", "arghyadeep")
        sentry.set_tag("component", "run_vector")
        sentry.set_tag("phase", "1")
        tel = get_telemetry()
        logger.info("[VECTOR][telemetry] Sentry active={} OTEL active={}", sentry.is_active, tel._otel_available)
    except Exception as e:
        logger.debug("[VECTOR][telemetry] init skipped: {}", e)

_init_telemetry()


# ── Global exception handlers — catch stray coroutine failures ────────────────
def _global_excepthook(exc_type, exc_value, exc_tb):
    """Catch unhandled exceptions that escape all try/except blocks."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical(
        "[VECTOR][unhandled] {exc_type.__name__}: {exc_value}",
        exc_type=exc_type, exc_value=exc_value,
    )
    try:
        from core.engine.telemetry.sentry_bridge import init_sentry
        init_sentry().capture_exception(exc_value)
    except Exception:
        pass

sys.excepthook = _global_excepthook


def _asyncio_exception_handler(loop, context):
    """Catch unhandled exceptions in async tasks that weren't awaited."""
    exc = context.get("exception")
    msg = context.get("message", "")
    future = context.get("future")
    if exc:
        logger.critical(
            "[VECTOR][async-unhandled] {exc_type.__name__}: {exc} — {msg}",
            exc_type=type(exc), exc=exc, msg=msg,
        )
        try:
            from core.engine.telemetry.sentry_bridge import init_sentry
            init_sentry().capture_exception(exc)
        except Exception:
            pass
    elif future:
        try:
            future.exception()
        except Exception as e:
            logger.critical("[VECTOR][async-future] {exc_type.__name__}: {e}", exc_type=type(e), e=e)
    else:
        logger.critical("[VECTOR][async-unhandled] {msg}", msg=msg)


try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
loop.set_exception_handler(_asyncio_exception_handler)


CORE_DISTRICTS = (
    ("governance-001", "GovernorCouncil", "governance"),
    ("coding-001", "CodeDistrict", "coding"),
    ("calendar-001", "CalendarDistrict", "time_calendar"),
    ("security-001", "SecurityDistrict", "security"),
    ("research-001", "ResearchDistrict", "research"),
    ("memory-001", "MemoryCuratorDistrict", "memory_curator"),
    ("health-001", "HealthDistrict", "health"),
    ("finance-001", "FinanceDistrict", "finance"),
    ("projects-001", "ProjectsDistrict", "projects"),
    ("reflection-001", "ReflectionDistrict", "reflection"),
)


def preflight_checks() -> None:
    """Verify critical runtime dependencies before starting the loop."""
    from pathlib import Path as _P
    from core.config import CONFIG as _cfg

    # 1. Ollama reachability
    try:
        import httpx as _httpx
        r = _httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            logger.info(f"[VECTOR][preflight] Ollama OK — {len(models)} models")
            if not any("vector-focus" in m or "gemma4" in m for m in models):
                logger.warning(
                    "[VECTOR][preflight] vector-focus model missing — "
                    "run: ollama create vector-focus -f modelfiles/vector-focus.modelfile"
                )
            # 1a. Warm the parallel-execution pool so the first per-district
            # request is instant (matches OLLAMA_MAX_LOADED_MODELS=4 daemon config).
            try:
                from core.inference.ollama_safe import warm_models
                warm_models()
            except Exception as warm_err:
                logger.warning(f"[VECTOR][preflight] warm-pool init failed: {warm_err}")
        else:
            logger.warning("[VECTOR][preflight] Ollama returned non-200 — run: ollama serve")
    except Exception:
        logger.warning(
            "[VECTOR][preflight] Ollama unreachable at 127.0.0.1:11434 — "
            "run: ollama serve"
        )

    # 2. VectorCode available
    vc_entry = _P(__file__).parent / "vectorcode" / "vector.py"
    if vc_entry.exists():
        logger.info(f"[VECTOR][preflight] VectorCode found at {vc_entry.parent}")
    else:
        logger.warning(
            f"[VECTOR][preflight] VectorCode entry not found at {vc_entry} — "
            "coding tasks will fall back to built-in district agents"
        )

    # 3. Obsidian vault
    vault = _P(str(_cfg.get("vault_path", "")))
    if vault.exists():
        logger.info(f"[VECTOR][preflight] Obsidian vault OK at {vault}")
    else:
        logger.warning(
            f"[VECTOR][preflight] Obsidian vault not found at {vault} — "
            "Obsidian sync inactive"
        )

    # 4. SQLite DB dir writable
    db_path = _P(str(_cfg.get("db_path", "vector_memory.db")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[VECTOR][preflight] DB dir writable: {db_path.parent}")


def bootstrap_agents() -> int:
    """Register all real district agents at startup."""
    from core.city.agent_registry import get_registry

    registry = get_registry()
    created = 0

    # ── VectorCode bridge ─────────────────────────────────────────────────────
    try:
        from districts.coding.vectorcode_bridge import get_bridge as _get_vc_bridge
        _vc = _get_vc_bridge()
        if _vc.is_available():
            logger.info("[bootstrap] VectorCode bridge ready")
        else:
            logger.warning("[bootstrap] VectorCode bridge unavailable — check vectorcode/vector.py")
    except Exception as e:
        logger.warning(f"[bootstrap] VectorCode bridge: {e}")

    def _reg(agent):
        if not registry.get(agent.id):
            registry.register(agent)
            return 1
        return 0

    # ── Coding ────────────────────────────────────────────────────────────────
    try:
        from districts.coding.git_bot import GitBot
        created += _reg(GitBot())
    except Exception as e:
        logger.warning(f"[bootstrap] GitBot: {e}")

    # ── Research ──────────────────────────────────────────────────────────────
    try:
        from districts.research.research_hub import ResearchHub
        created += _reg(ResearchHub())
    except Exception as e:
        logger.warning(f"[bootstrap] ResearchHub: {e}")
    try:
        from districts.research.reddit_miner import RedditMiner
        created += _reg(RedditMiner())
    except Exception as e:
        logger.warning(f"[bootstrap] RedditMiner: {e}")
    try:
        from districts.research.news_aggregator import NewsAggregator
        created += _reg(NewsAggregator())
    except Exception as e:
        logger.warning(f"[bootstrap] NewsAggregator: {e}")
    try:
        from districts.research.paper_reader import PaperReader
        created += _reg(PaperReader())
    except Exception as e:
        logger.warning(f"[bootstrap] PaperReader: {e}")
    try:
        from districts.research.web_scout import WebScout
        created += _reg(WebScout())
    except Exception as e:
        logger.warning(f"[bootstrap] WebScout: {e}")

    # ── Governance ────────────────────────────────────────────────────────────
    try:
        from districts.governance.llm_council import LLMCouncil
        created += _reg(LLMCouncil())
    except Exception as e:
        logger.warning(f"[bootstrap] LLMCouncil: {e}")

    # ── Reflection ────────────────────────────────────────────────────────────
    try:
        from districts.reflection.daily_reviewer import DailyReviewer
        created += _reg(DailyReviewer())
    except Exception as e:
        logger.warning(f"[bootstrap] DailyReviewer: {e}")
    try:
        from districts.reflection.journal_writer import JournalWriter
        created += _reg(JournalWriter())
    except Exception as e:
        logger.warning(f"[bootstrap] JournalWriter: {e}")
    try:
        from districts.reflection.growth_analyst import GrowthAnalyst
        created += _reg(GrowthAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] GrowthAnalyst: {e}")

    # ── Finance ───────────────────────────────────────────────────────────────
    try:
        from districts.finance.expense_tracker import ExpenseTracker
        created += _reg(ExpenseTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] ExpenseTracker: {e}")
    try:
        from districts.finance.budget_analyst import BudgetAnalyst
        created += _reg(BudgetAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] BudgetAnalyst: {e}")
    try:
        from districts.finance.upi_parser import UPIParser
        created += _reg(UPIParser())
    except Exception as e:
        logger.warning(f"[bootstrap] UPIParser: {e}")
    try:
        from districts.finance.tax_calendar import TaxCalendar
        created += _reg(TaxCalendar())
    except Exception as e:
        logger.warning(f"[bootstrap] TaxCalendar: {e}")

    # ── Health ────────────────────────────────────────────────────────────────
    try:
        from districts.health.fatigue_monitor import FatigueMonitor
        created += _reg(FatigueMonitor())
    except Exception as e:
        logger.warning(f"[bootstrap] FatigueMonitor: {e}")
    try:
        from districts.health.sleep_tracker import SleepTracker
        created += _reg(SleepTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] SleepTracker: {e}")
    try:
        from districts.health.exercise_logger import ExerciseLogger
        created += _reg(ExerciseLogger())
    except Exception as e:
        logger.warning(f"[bootstrap] ExerciseLogger: {e}")

    # ── Memory Curator ────────────────────────────────────────────────────────
    try:
        from districts.memory_curator.consolidation_bot import ConsolidationBot
        created += _reg(ConsolidationBot())
    except Exception as e:
        logger.warning(f"[bootstrap] ConsolidationBot: {e}")
    try:
        from districts.memory_curator.pattern_finder import PatternFinder
        created += _reg(PatternFinder())
    except Exception as e:
        logger.warning(f"[bootstrap] PatternFinder: {e}")

    # ── Projects ──────────────────────────────────────────────────────────────
    try:
        from districts.projects.deadline_watcher import DeadlineWatcher
        created += _reg(DeadlineWatcher())
    except Exception as e:
        logger.warning(f"[bootstrap] DeadlineWatcher: {e}")
    try:
        from districts.projects.progress_tracker import ProgressTracker
        created += _reg(ProgressTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] ProgressTracker: {e}")
    try:
        from districts.projects.doc_writer import DocWriter
        created += _reg(DocWriter())
    except Exception as e:
        logger.warning(f"[bootstrap] DocWriter: {e}")
    try:
        from districts.projects.project_planner import ProjectPlanner
        created += _reg(ProjectPlanner())
    except Exception as e:
        logger.warning(f"[bootstrap] ProjectPlanner: {e}")

    # ── Security ──────────────────────────────────────────────────────────────
    try:
        from districts.security.threat_scout import ThreatScout
        created += _reg(ThreatScout())
    except Exception as e:
        logger.warning(f"[bootstrap] ThreatScout: {e}")
    try:
        from districts.security.node_guard import NodeGuard
        created += _reg(NodeGuard())
    except Exception as e:
        logger.warning(f"[bootstrap] NodeGuard: {e}")
    try:
        from districts.security.malware_hunter import MalwareHunter
        created += _reg(MalwareHunter())
    except Exception as e:
        logger.warning(f"[bootstrap] MalwareHunter: {e}")

    # ── Time/Calendar ─────────────────────────────────────────────────────────
    try:
        from districts.time_calendar.kiit_scraper import KIITScraper
        created += _reg(KIITScraper())
    except Exception as e:
        logger.warning(f"[bootstrap] KIITScraper: {e}")
    try:
        from districts.time_calendar.deadline_manager import DeadlineManager
        created += _reg(DeadlineManager())
    except Exception as e:
        logger.warning(f"[bootstrap] DeadlineManager: {e}")
    try:
        from districts.time_calendar.time_blocker import TimeBlocker
        created += _reg(TimeBlocker())
    except Exception as e:
        logger.warning(f"[bootstrap] TimeBlocker: {e}")

    # ── Coding sub-agents ─────────────────────────────────────────────────────
    try:
        from districts.coding.code_reviewer import CodeReviewer
        created += _reg(CodeReviewer())
    except Exception as e:
        logger.warning(f"[bootstrap] CodeReviewer: {e}")
    try:
        from districts.coding.architect_bot import ArchitectBot
        created += _reg(ArchitectBot())
    except Exception as e:
        logger.warning(f"[bootstrap] ArchitectBot: {e}")
    try:
        from districts.coding.bug_hunter import BugHunter
        created += _reg(BugHunter())
    except Exception as e:
        logger.warning(f"[bootstrap] BugHunter: {e}")
    try:
        from districts.coding.test_writer import TestWriter
        created += _reg(TestWriter())
    except Exception as e:
        logger.warning(f"[bootstrap] TestWriter: {e}")

    # ── Relationships ─────────────────────────────────────────────────────────
    try:
        from districts.relationships.contact_manager import ContactManager
        created += _reg(ContactManager())
    except Exception as e:
        logger.warning(f"[bootstrap] ContactManager: {e}")
    try:
        from districts.relationships.communication_analyst import CommunicationAnalyst
        created += _reg(CommunicationAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] CommunicationAnalyst: {e}")

    # ── Privacy ───────────────────────────────────────────────────────────────
    try:
        from districts.privacy.privacy_enforcer import PrivacyEnforcer
        created += _reg(PrivacyEnforcer())
    except Exception as e:
        logger.warning(f"[bootstrap] PrivacyEnforcer: {e}")
    try:
        from districts.privacy.data_flow_auditor import DataFlowAuditor
        created += _reg(DataFlowAuditor())
    except Exception as e:
        logger.warning(f"[bootstrap] DataFlowAuditor: {e}")

    # ── Pattern Detective ─────────────────────────────────────────────────────
    try:
        from districts.pattern_detective.habit_finder import HabitFinder
        created += _reg(HabitFinder())
    except Exception as e:
        logger.warning(f"[bootstrap] HabitFinder: {e}")
    try:
        from districts.pattern_detective.behavior_analyst import BehaviorAnalyst
        created += _reg(BehaviorAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] BehaviorAnalyst: {e}")

    # ── Intelligence (VectorIntel / Shadowbroker) ────────────────────────────
    try:
        from districts.intelligence.vectorintel_agent import VectorIntelAgent
        created += _reg(VectorIntelAgent())
    except Exception as e:
        logger.warning(f"[bootstrap] VectorIntelAgent: {e}")

    # ── News & Trends ─────────────────────────────────────────────────────────
    try:
        from districts.news_trends.ai_news_bot import AINewsBot
        created += _reg(AINewsBot())
    except Exception as e:
        logger.warning(f"[bootstrap] AINewsBot: {e}")
    try:
        from districts.news_trends.market_trends_bot import MarketTrendsBot
        created += _reg(MarketTrendsBot())
    except Exception as e:
        logger.warning(f"[bootstrap] MarketTrendsBot: {e}")
    try:
        from districts.news_trends.opportunity_spotter import OpportunitySpotter
        created += _reg(OpportunitySpotter())
    except Exception as e:
        logger.warning(f"[bootstrap] OpportunitySpotter: {e}")

    # ── Learning ──────────────────────────────────────────────────────────────
    try:
        from districts.learning.course_tracker import CourseTracker
        created += _reg(CourseTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] CourseTracker: {e}")
    try:
        from districts.learning.video_ingestor import VideoIngestor
        created += _reg(VideoIngestor())
    except Exception as e:
        logger.warning(f"[bootstrap] VideoIngestor: {e}")

    # ── Startups ──────────────────────────────────────────────────────────────
    try:
        from districts.startups.market_scanner import MarketScanner
        created += _reg(MarketScanner())
    except Exception as e:
        logger.warning(f"[bootstrap] MarketScanner: {e}")
    try:
        from districts.startups.idea_validator import IdeaValidator
        created += _reg(IdeaValidator())
    except Exception as e:
        logger.warning(f"[bootstrap] IdeaValidator: {e}")
    try:
        from districts.startups.competitor_spy import CompetitorSpy
        created += _reg(CompetitorSpy())
    except Exception as e:
        logger.warning(f"[bootstrap] CompetitorSpy: {e}")
    try:
        from districts.startups.revenue_modeler import RevenueModeler
        created += _reg(RevenueModeler())
    except Exception as e:
        logger.warning(f"[bootstrap] RevenueModeler: {e}")

    # ── Calls ─────────────────────────────────────────────────────────────────
    try:
        from districts.calls.call_screener import CallScreener
        created += _reg(CallScreener())
    except Exception as e:
        logger.warning(f"[bootstrap] CallScreener: {e}")

    # ── Karpathy Lab ──────────────────────────────────────────────────────────
    try:
        from districts.karpathy_lab.autoresearch_runner import AutoresearchRunner
        created += _reg(AutoresearchRunner())
    except Exception as e:
        logger.warning(f"[bootstrap] AutoresearchRunner: {e}")
    try:
        from districts.karpathy_lab.code_typer import CodeTyper
        created += _reg(CodeTyper())
    except Exception as e:
        logger.warning(f"[bootstrap] CodeTyper: {e}")

    # ── Languages ─────────────────────────────────────────────────────────────
    try:
        from districts.languages.japanese_coach import JapaneseCoach
        created += _reg(JapaneseCoach())
    except Exception as e:
        logger.warning(f"[bootstrap] JapaneseCoach: {e}")

    # ── Interview Prep ────────────────────────────────────────────────────────
    try:
        from districts.interview_prep.mock_interviewer import MockInterviewer
        created += _reg(MockInterviewer())
    except Exception as e:
        logger.warning(f"[bootstrap] MockInterviewer: {e}")
    try:
        from districts.interview_prep.company_researcher import CompanyResearcher
        created += _reg(CompanyResearcher())
    except Exception as e:
        logger.warning(f"[bootstrap] CompanyResearcher: {e}")

    # ── Agency ────────────────────────────────────────────────────────────────
    try:
        from districts.agency.content_strategist import ContentStrategist
        created += _reg(ContentStrategist())
    except Exception as e:
        logger.warning(f"[bootstrap] ContentStrategist: {e}")

    # ── Investment ────────────────────────────────────────────────────────────
    try:
        from districts.investment.stock_analyst import StockAnalyst
        created += _reg(StockAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] StockAnalyst: {e}")
    try:
        from districts.investment.sentiment_bot import SentimentBot
        created += _reg(SentimentBot())
    except Exception as e:
        logger.warning(f"[bootstrap] SentimentBot: {e}")

    # ── Content ───────────────────────────────────────────────────────────────
    try:
        from districts.content.script_generator import ScriptGenerator
        created += _reg(ScriptGenerator())
    except Exception as e:
        logger.warning(f"[bootstrap] ScriptGenerator: {e}")
    try:
        from districts.content.comfyui_adapter import ComfyUIAdapter
        created += _reg(ComfyUIAdapter())
    except Exception as e:
        logger.warning(f"[bootstrap] ComfyUIAdapter: {e}")

    # ── Skills ────────────────────────────────────────────────────────────────
    try:
        from districts.skills.skill_mapper import SkillMapper
        created += _reg(SkillMapper())
    except Exception as e:
        logger.warning(f"[bootstrap] SkillMapper: {e}")
    try:
        from districts.skills.mastery_tracker import MasteryTracker
        created += _reg(MasteryTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] MasteryTracker: {e}")

    # ── Absorbed modules: templates, recipes, vc_system ──────────────────────
    try:
        from vectorcode.src.vc_templates import discover_templates
        templates = discover_templates()
        logger.info(f"[bootstrap] {len(templates) if templates else 0} agent templates available")
    except Exception as e:
        logger.debug(f"[bootstrap] vc_templates unavailable: {e}")
    try:
        from vectorcode.src.recipes import discover_recipes
        recipes = discover_recipes()
        if recipes:
            logger.info(f"[bootstrap] {len(recipes)} recipes discovered")
    except Exception as e:
        logger.debug(f"[bootstrap] recipes unavailable: {e}")
    try:
        from vectorcode.src.vc_system import VectorSystem, SystemBuilder
        logger.info("[bootstrap] vc_system (VectorSystem/SystemBuilder) available")
    except Exception as e:
        logger.debug(f"[bootstrap] vc_system unavailable: {e}")

    # ── Python agent bulk registration — district Python agents not yet registered ──
    created += bulk_register_python_districts(registry)

    # ── PromptAgent bulk registration — all .md-defined agents across districts/ ──
    created += bulk_register_md_districts(registry)

    logger.info(f"[VECTOR][bootstrap] {created} agents registered across all districts")

    # ── Agent-to-Agent event wiring — auto-subscribe by district name ─────
    try:
        from core.event_bus.wiring import auto_subscribe_all as _wire_events
        _wire_events()
    except Exception as e:
        logger.warning(f"[bootstrap] event wiring skipped: {e}")

    return created


def bulk_register_python_districts(registry=None) -> int:
    """Auto-register all Python AgentBase subclasses in districts/ not yet in the registry.

    Scans every .py file directly inside districts/{district}/ (depth=2),
    imports it, finds AgentBase subclasses, and registers any that aren't
    already in the registry. Skips __init__.py and __main__.py.
    """
    import importlib.util
    from core.city.agent_registry import get_registry
    from core.city.agent_base import AgentBase

    if registry is None:
        registry = get_registry()

    districts_root = Path(__file__).parent / "districts"
    registered = 0
    skipped_dup = 0
    failed = 0

    for py_file in sorted(districts_root.rglob("*.py")):
        rel = py_file.relative_to(districts_root)
        # Only district-level files: districts/{district}/{file}.py
        if len(rel.parts) != 2:
            continue
        if py_file.name.startswith("__"):
            continue

        district_name = rel.parts[0]
        module_name = f"districts.{district_name}.{py_file.stem}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.debug(f"[bootstrap] skip {module_name}: {e}")
            failed += 1
            continue

        # Find AgentBase subclasses in this module
        for attr_name in dir(module):
            try:
                obj = getattr(module, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, AgentBase)
                    and obj is not AgentBase
                    and obj.__module__ == module_name
                ):
                    # Generate a deterministic ID from class name
                    agent_id = f"{attr_name.lower()}_auto_001"
                    if registry.get(agent_id):
                        skipped_dup += 1
                        continue
                    try:
                        agent = obj()
                        if registry.get(agent.id):
                            skipped_dup += 1
                            continue
                        registry.register(agent)
                        registered += 1
                    except Exception as e:
                        logger.debug(f"[bootstrap] {attr_name} instantiation failed: {e}")
                        failed += 1
            except Exception:
                continue

    logger.info(
        "[bootstrap] Python auto-register: {} agents, {} dupes skipped, {} failed",
        registered, skipped_dup, failed,
    )
    return registered


def bulk_register_md_districts(registry=None) -> int:
    """Register every .md agent file in districts/ as a live PromptAgent citizen.

    Scans districts/ recursively, creates an anonymous PromptAgent subclass for
    each .md file (skipping docs/READMEs), and registers it in the agent registry.
    Already-registered IDs are skipped to avoid duplicates from mixed districts.
    """
    from core.city.agent_registry import get_registry
    from core.city.prompt_agent import PromptAgent

    if registry is None:
        registry = get_registry()

    districts_root = Path(__file__).parent / "districts"

    # Districts with their own Swarm loader — skip .md bulk registration (swarm handles it)
    SWARM_DISTRICTS = {
        "engineering", "testing", "product", "coding", "qa", "research", "finance",
        "security", "governance", "marketing", "specialized",
        "sales", "design", "project_management", "support",
        "spatial_computing", "academic", "game_development",
        "paid_media", "communications", "documentation",
        "data_analytics", "startups", "skills", "content",
        "languages", "learning", "news_trends", "intelligence",
        "pattern_detective", "personal_growth", "privacy",
        "reflection", "relationships", "memory_curator",
        "health", "projects", "time_calendar", "calls",
        "agency", "investment", "interview_prep", "karpathy_lab",
    }

    # Non-agent docs to skip explicitly
    SKIP_NAMES = {
        "readme.md", "__init__.md", "index.md",
        "executive-brief.md", "quickstart.md", "nexus-strategy.md",
        "changelogs.md", "architecture.md", "contributing.md",
    }

    registered = 0
    skipped_dup = 0
    skipped_doc = 0

    for md_file in sorted(districts_root.rglob("*.md")):
        if md_file.name.lower() in SKIP_NAMES:
            skipped_doc += 1
            continue

        # Skip districts managed by their own Swarm loader
        if md_file.parent.name in SWARM_DISTRICTS:
            skipped_doc += 1
            continue

        # Derive district from the immediate parent folder of the .md file
        district_name = md_file.parent.name

        # Skip .md files nested deep inside tool sub-packages (e.g. districts/investment/vector_finagent/docs/*.md)
        # Only register .md files that sit directly inside a district folder (depth = districts/{district}/*.md)
        try:
            rel = md_file.relative_to(districts_root)
            if len(rel.parts) != 2:
                # Not at districts/{district}/{file}.md — skip (it's inside a sub-package)
                skipped_doc += 1
                continue
        except ValueError:
            skipped_doc += 1
            continue

        agent_id = md_file.stem.replace("-", "_").lower() + "_001"

        if registry.get(agent_id):
            skipped_dup += 1
            continue

        class_name = "".join(w.capitalize() for w in md_file.stem.replace("-", " ").split())

        try:
            md_path_str = str(md_file)
            AgentClass = type(
                class_name,
                (PromptAgent,),
                {
                    "__init__": lambda self, _p=md_path_str, _i=agent_id, _d=district_name:
                        PromptAgent.__init__(self, _p, _i, _d)
                },
            )
            agent = AgentClass()
            registry.register(agent)
            registered += 1
        except Exception as e:
            logger.warning(f"[bootstrap] PromptAgent {md_file.name}: {e}")

    logger.info(
        "[bootstrap] PromptAgent: {} .md agents registered, {} dupes skipped, {} docs skipped",
        registered, skipped_dup, skipped_doc,
    )
    return registered


async def smoke_test() -> dict:
    """Verify the local spine can initialize and make one decision safely."""
    from core.brain.goal_system import GoalSystem
    from core.loop.context_engine import ContextEngine
    from core.loop.decision_engine import Candidate, DecisionEngine
    from core.memory.episodic import EpisodicMemory

    created = bootstrap_agents()
    memory = EpisodicMemory()
    memory.store(
        event_type="startup_smoke",
        content="VECTOR smoke test started from run_vector.py",
        tags=["startup", "smoke"],
        source="run_vector",
    )

    context_prompt = ContextEngine().session_hydration_prompt({"mode": "smoke"})
    actions = GoalSystem().generate_immediate_actions(limit=4)
    candidates = [
        Candidate(
            action_type=a["action"],
            params={"goal_id": a["goal_id"], "title": a["title"]},
            goal_ids=[a["goal_id"]],
            urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(a.get("urgency"), 0.5),
            confidence=0.7,
            source="run_vector_smoke",
        )
        for a in actions
    ]
    decision = await DecisionEngine().evaluate(candidates)
    stats = memory.get_stats()

    return {
        "status": "ok",
        "agents_bootstrapped": created,
        "hydration_chars": len(context_prompt),
        "candidates_evaluated": decision.evaluated,
        "winner": decision.winner.action_type,
        "winner_score": decision.winner.total_score,
        "memory_stats": stats,
    }


async def _start_background_services() -> None:
    """Start lightweight background services that augment VECTOR's capabilities."""
    import asyncio

    # Session persistence — recover crashed sessions + register current run
    try:
        from core.jcode.session_persistence import SessionPersistence
        _sp = SessionPersistence()
        crashed = _sp.recover_crashed_sessions()
        if crashed:
            logger.warning(
                "[VECTOR][startup] {} crashed session(s) recovered from prior run",
                len(crashed),
            )
        logger.info("[VECTOR][startup] SessionPersistence active — crash recovery enabled")
    except Exception as e:
        logger.debug("[VECTOR][startup] SessionPersistence skipped: {}", e)

    # OAuth server (port 51201) — provides token exchange for 119 integrations
    try:
        from core.engine.oauth.server import create_oauth_app
        import uvicorn
        oauth_app = create_oauth_app()
        config = uvicorn.Config(oauth_app, host="127.0.0.1", port=51201, log_level="warning")
        server = uvicorn.Server(config)
        asyncio.create_task(server.serve())
        logger.info("[VECTOR][startup] OAuth server started at http://127.0.0.1:51201")
    except Exception as e:
        logger.debug("[VECTOR][startup] OAuth server skipped: {}", e)

    # Channel runtime — wires inbound messages → governor dispatch
    try:
        from core.engine.channels.runtime import ChannelRuntime
        _runtime = ChannelRuntime(max_in_flight=5)
        asyncio.create_task(_runtime.start())
        logger.info("[VECTOR][startup] ChannelRuntime dispatch loop started")
    except Exception as e:
        logger.debug("[VECTOR][startup] ChannelRuntime skipped: {}", e)


async def run_loop() -> None:
    """Start the autonomous loop. This is intended to run until interrupted."""
    preflight_checks()
    bootstrap_agents()
    await _start_background_services()
    from core.loop.autonomous_loop import AutonomousLoop

    await AutonomousLoop().run_forever()


def run_api(host: str, port: int) -> None:
    """Start the local FastAPI server using the modular API over HTTPS."""
    import uvicorn
    from core.api import create_app

    # Generate self-signed cert if not present
    cert_file, key_file = _ensure_ssl_cert()

    app = create_app()
    if cert_file and key_file:
        logger.info(f"[VECTOR][api] Starting HTTPS server at https://{host}:{port}")
        uvicorn.run(app, host=host, port=port, reload=False,
                    ssl_certfile=str(cert_file), ssl_keyfile=str(key_file))
    else:
        logger.warning("[VECTOR][api] SSL cert generation failed — falling back to HTTP")
        uvicorn.run(app, host=host, port=port, reload=False)


def _ensure_ssl_cert():
    """Generate a self-signed SSL cert for localhost if not already present."""
    from pathlib import Path as _P
    cert_dir = _P(__file__).parent / "certs"
    cert_dir.mkdir(exist_ok=True)
    cert_file = cert_dir / "vector.crt"
    key_file = cert_dir / "vector.key"

    if cert_file.exists() and key_file.exists():
        logger.info(f"[VECTOR][ssl] Using existing cert at {cert_file}")
        return cert_file, key_file

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"VECTOR"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName(u"localhost"),
                x509.IPAddress(__import__("ipaddress").IPv4Address("127.0.0.1")),
            ]), critical=False)
            .sign(key, hashes.SHA256())
        )
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_file.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
        logger.info(f"[VECTOR][ssl] Self-signed cert generated at {cert_file}")
        return cert_file, key_file
    except ImportError:
        logger.warning("[VECTOR][ssl] cryptography package not installed — run: pip install cryptography")
        return None, None
    except Exception as e:
        logger.error(f"[VECTOR][ssl] Cert generation failed: {e}")
        return None, None


def ha_startup() -> bool:
    """Initialize Home Assistant district connector if enabled in config."""
    from core.config import CONFIG as _cfg
    ha_cfg = _cfg.get("home_assistant", {})
    if not ha_cfg.get("enabled", False):
        logger.info("[VECTOR][ha] Home Assistant disabled (set HASS_TOKEN to enable)")
        return False
    try:
        from districts.home_assistant.connector import HAConfig, HAConnector
        cfg = HAConfig(
            host=ha_cfg.get("host", "homeassistant.local"),
            port=ha_cfg.get("port", 8123),
            token=ha_cfg.get("token", ""),
            use_ssl=ha_cfg.get("use_ssl", False),
        )
        if not cfg.token:
            logger.warning("[VECTOR][ha] No token configured — HA disabled")
            return False
        connector = HAConnector(cfg)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ok = loop.run_until_complete(connector.connect())
        loop.run_until_complete(connector.disconnect())
        loop.close()
        if ok:
            logger.info("[VECTOR][ha] Home Assistant connection verified")
            return True
        logger.warning("[VECTOR][ha] Home Assistant connection failed")
        return False
    except Exception as e:
        logger.warning(f"[VECTOR][ha] Startup failed: {e}")
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VECTOR local launcher")
    parser.add_argument(
        "mode",
        nargs="?",
        default="loop",
        choices=("loop", "api", "smoke"),
        help="Default is loop. Use smoke for a one-shot startup check.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ha", action="store_true", help="Enable Home Assistant district integration")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger.info(f"[VECTOR][launcher] mode={args.mode}")

    if args.ha:
        ha_startup()

    if args.mode == "api":
        run_api(args.host, args.port)
        return 0

    if args.mode == "smoke":
        result = asyncio.run(smoke_test())
        print(result)
        return 0 if result["status"] == "ok" else 1

    try:
        asyncio.run(run_loop())
        return 0
    except KeyboardInterrupt:
        logger.info("[VECTOR][launcher] stopped by owner")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
