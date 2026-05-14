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
        else:
            logger.warning("[VECTOR][preflight] Ollama returned non-200 — run: ollama serve")
    except Exception:
        logger.warning(
            "[VECTOR][preflight] Ollama unreachable at 127.0.0.1:11434 — "
            "run: ollama serve"
        )

    # 2. Hermes repo present
    hermes_repo = _P(_cfg.get("hermes", {}).get(
        "repo_path",
        "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/NousResearch_hermes-agent/repo",
    ))
    if hermes_repo.exists():
        logger.info(f"[VECTOR][preflight] Hermes repo found at {hermes_repo}")
    else:
        logger.warning(
            f"[VECTOR][preflight] Hermes repo missing at {hermes_repo} — "
            "District 6 comms will be unavailable"
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

    def _reg(agent):
        if not registry.get(agent.id):
            registry.register(agent)
            return 1
        return 0

    # ── Coding ────────────────────────────────────────────────────────────────
    try:
        from agents.districts.coding.git_bot import GitBot
        created += _reg(GitBot())
    except Exception as e:
        logger.warning(f"[bootstrap] GitBot: {e}")

    # ── Research ──────────────────────────────────────────────────────────────
    try:
        from agents.districts.research.research_hub import ResearchHub
        created += _reg(ResearchHub())
    except Exception as e:
        logger.warning(f"[bootstrap] ResearchHub: {e}")
    try:
        from agents.districts.research.reddit_miner import RedditMiner
        created += _reg(RedditMiner())
    except Exception as e:
        logger.warning(f"[bootstrap] RedditMiner: {e}")
    try:
        from agents.districts.research.news_aggregator import NewsAggregator
        created += _reg(NewsAggregator())
    except Exception as e:
        logger.warning(f"[bootstrap] NewsAggregator: {e}")
    try:
        from agents.districts.research.paper_reader import PaperReader
        created += _reg(PaperReader())
    except Exception as e:
        logger.warning(f"[bootstrap] PaperReader: {e}")
    try:
        from agents.districts.research.web_scout import WebScout
        created += _reg(WebScout())
    except Exception as e:
        logger.warning(f"[bootstrap] WebScout: {e}")

    # ── Governance ────────────────────────────────────────────────────────────
    try:
        from agents.districts.governance.llm_council import LLMCouncil
        created += _reg(LLMCouncil())
    except Exception as e:
        logger.warning(f"[bootstrap] LLMCouncil: {e}")

    # ── Reflection ────────────────────────────────────────────────────────────
    try:
        from agents.districts.reflection.daily_reviewer import DailyReviewer
        created += _reg(DailyReviewer())
    except Exception as e:
        logger.warning(f"[bootstrap] DailyReviewer: {e}")
    try:
        from agents.districts.reflection.journal_writer import JournalWriter
        created += _reg(JournalWriter())
    except Exception as e:
        logger.warning(f"[bootstrap] JournalWriter: {e}")
    try:
        from agents.districts.reflection.growth_analyst import GrowthAnalyst
        created += _reg(GrowthAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] GrowthAnalyst: {e}")

    # ── Finance ───────────────────────────────────────────────────────────────
    try:
        from agents.districts.finance.expense_tracker import ExpenseTracker
        created += _reg(ExpenseTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] ExpenseTracker: {e}")
    try:
        from agents.districts.finance.budget_analyst import BudgetAnalyst
        created += _reg(BudgetAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] BudgetAnalyst: {e}")
    try:
        from agents.districts.finance.upi_parser import UPIParser
        created += _reg(UPIParser())
    except Exception as e:
        logger.warning(f"[bootstrap] UPIParser: {e}")
    try:
        from agents.districts.finance.tax_calendar import TaxCalendar
        created += _reg(TaxCalendar())
    except Exception as e:
        logger.warning(f"[bootstrap] TaxCalendar: {e}")

    # ── Health ────────────────────────────────────────────────────────────────
    try:
        from agents.districts.health.fatigue_monitor import FatigueMonitor
        created += _reg(FatigueMonitor())
    except Exception as e:
        logger.warning(f"[bootstrap] FatigueMonitor: {e}")
    try:
        from agents.districts.health.sleep_tracker import SleepTracker
        created += _reg(SleepTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] SleepTracker: {e}")
    try:
        from agents.districts.health.exercise_logger import ExerciseLogger
        created += _reg(ExerciseLogger())
    except Exception as e:
        logger.warning(f"[bootstrap] ExerciseLogger: {e}")

    # ── Memory Curator ────────────────────────────────────────────────────────
    try:
        from agents.districts.memory_curator.consolidation_bot import ConsolidationBot
        created += _reg(ConsolidationBot())
    except Exception as e:
        logger.warning(f"[bootstrap] ConsolidationBot: {e}")
    try:
        from agents.districts.memory_curator.pattern_finder import PatternFinder
        created += _reg(PatternFinder())
    except Exception as e:
        logger.warning(f"[bootstrap] PatternFinder: {e}")

    # ── Projects ──────────────────────────────────────────────────────────────
    try:
        from agents.districts.projects.deadline_watcher import DeadlineWatcher
        created += _reg(DeadlineWatcher())
    except Exception as e:
        logger.warning(f"[bootstrap] DeadlineWatcher: {e}")
    try:
        from agents.districts.projects.progress_tracker import ProgressTracker
        created += _reg(ProgressTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] ProgressTracker: {e}")
    try:
        from agents.districts.projects.doc_writer import DocWriter
        created += _reg(DocWriter())
    except Exception as e:
        logger.warning(f"[bootstrap] DocWriter: {e}")
    try:
        from agents.districts.projects.project_planner import ProjectPlanner
        created += _reg(ProjectPlanner())
    except Exception as e:
        logger.warning(f"[bootstrap] ProjectPlanner: {e}")

    # ── Security ──────────────────────────────────────────────────────────────
    try:
        from agents.districts.security.threat_scout import ThreatScout
        created += _reg(ThreatScout())
    except Exception as e:
        logger.warning(f"[bootstrap] ThreatScout: {e}")
    try:
        from agents.districts.security.node_guard import NodeGuard
        created += _reg(NodeGuard())
    except Exception as e:
        logger.warning(f"[bootstrap] NodeGuard: {e}")
    try:
        from agents.districts.security.malware_hunter import MalwareHunter
        created += _reg(MalwareHunter())
    except Exception as e:
        logger.warning(f"[bootstrap] MalwareHunter: {e}")

    # ── Time/Calendar ─────────────────────────────────────────────────────────
    try:
        from agents.districts.time_calendar.kiit_scraper import KIITScraper
        created += _reg(KIITScraper())
    except Exception as e:
        logger.warning(f"[bootstrap] KIITScraper: {e}")
    try:
        from agents.districts.time_calendar.deadline_manager import DeadlineManager
        created += _reg(DeadlineManager())
    except Exception as e:
        logger.warning(f"[bootstrap] DeadlineManager: {e}")
    try:
        from agents.districts.time_calendar.time_blocker import TimeBlocker
        created += _reg(TimeBlocker())
    except Exception as e:
        logger.warning(f"[bootstrap] TimeBlocker: {e}")

    # ── Coding sub-agents ─────────────────────────────────────────────────────
    try:
        from agents.districts.coding.code_reviewer import CodeReviewer
        created += _reg(CodeReviewer())
    except Exception as e:
        logger.warning(f"[bootstrap] CodeReviewer: {e}")
    try:
        from agents.districts.coding.architect_bot import ArchitectBot
        created += _reg(ArchitectBot())
    except Exception as e:
        logger.warning(f"[bootstrap] ArchitectBot: {e}")
    try:
        from agents.districts.coding.bug_hunter import BugHunter
        created += _reg(BugHunter())
    except Exception as e:
        logger.warning(f"[bootstrap] BugHunter: {e}")
    try:
        from agents.districts.coding.test_writer import TestWriter
        created += _reg(TestWriter())
    except Exception as e:
        logger.warning(f"[bootstrap] TestWriter: {e}")

    # ── Relationships ─────────────────────────────────────────────────────────
    try:
        from agents.districts.relationships.contact_manager import ContactManager
        created += _reg(ContactManager())
    except Exception as e:
        logger.warning(f"[bootstrap] ContactManager: {e}")
    try:
        from agents.districts.relationships.communication_analyst import CommunicationAnalyst
        created += _reg(CommunicationAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] CommunicationAnalyst: {e}")

    # ── Privacy ───────────────────────────────────────────────────────────────
    try:
        from agents.districts.privacy.privacy_enforcer import PrivacyEnforcer
        created += _reg(PrivacyEnforcer())
    except Exception as e:
        logger.warning(f"[bootstrap] PrivacyEnforcer: {e}")
    try:
        from agents.districts.privacy.data_flow_auditor import DataFlowAuditor
        created += _reg(DataFlowAuditor())
    except Exception as e:
        logger.warning(f"[bootstrap] DataFlowAuditor: {e}")

    # ── Pattern Detective ─────────────────────────────────────────────────────
    try:
        from agents.districts.pattern_detective.habit_finder import HabitFinder
        created += _reg(HabitFinder())
    except Exception as e:
        logger.warning(f"[bootstrap] HabitFinder: {e}")
    try:
        from agents.districts.pattern_detective.behavior_analyst import BehaviorAnalyst
        created += _reg(BehaviorAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] BehaviorAnalyst: {e}")

    # ── News & Trends ─────────────────────────────────────────────────────────
    try:
        from agents.districts.news_trends.ai_news_bot import AINewsBot
        created += _reg(AINewsBot())
    except Exception as e:
        logger.warning(f"[bootstrap] AINewsBot: {e}")
    try:
        from agents.districts.news_trends.market_trends_bot import MarketTrendsBot
        created += _reg(MarketTrendsBot())
    except Exception as e:
        logger.warning(f"[bootstrap] MarketTrendsBot: {e}")
    try:
        from agents.districts.news_trends.opportunity_spotter import OpportunitySpotter
        created += _reg(OpportunitySpotter())
    except Exception as e:
        logger.warning(f"[bootstrap] OpportunitySpotter: {e}")

    # ── Learning ──────────────────────────────────────────────────────────────
    try:
        from agents.districts.learning.course_tracker import CourseTracker
        created += _reg(CourseTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] CourseTracker: {e}")
    try:
        from agents.districts.learning.video_ingestor import VideoIngestor
        created += _reg(VideoIngestor())
    except Exception as e:
        logger.warning(f"[bootstrap] VideoIngestor: {e}")

    # ── Startups ──────────────────────────────────────────────────────────────
    try:
        from agents.districts.startups.market_scanner import MarketScanner
        created += _reg(MarketScanner())
    except Exception as e:
        logger.warning(f"[bootstrap] MarketScanner: {e}")
    try:
        from agents.districts.startups.idea_validator import IdeaValidator
        created += _reg(IdeaValidator())
    except Exception as e:
        logger.warning(f"[bootstrap] IdeaValidator: {e}")
    try:
        from agents.districts.startups.competitor_spy import CompetitorSpy
        created += _reg(CompetitorSpy())
    except Exception as e:
        logger.warning(f"[bootstrap] CompetitorSpy: {e}")
    try:
        from agents.districts.startups.revenue_modeler import RevenueModeler
        created += _reg(RevenueModeler())
    except Exception as e:
        logger.warning(f"[bootstrap] RevenueModeler: {e}")

    # ── Calls ─────────────────────────────────────────────────────────────────
    try:
        from agents.districts.calls.call_screener import CallScreener
        created += _reg(CallScreener())
    except Exception as e:
        logger.warning(f"[bootstrap] CallScreener: {e}")

    # ── Karpathy Lab ──────────────────────────────────────────────────────────
    try:
        from agents.districts.karpathy_lab.autoresearch_runner import AutoresearchRunner
        created += _reg(AutoresearchRunner())
    except Exception as e:
        logger.warning(f"[bootstrap] AutoresearchRunner: {e}")
    try:
        from agents.districts.karpathy_lab.code_typer import CodeTyper
        created += _reg(CodeTyper())
    except Exception as e:
        logger.warning(f"[bootstrap] CodeTyper: {e}")

    # ── Languages ─────────────────────────────────────────────────────────────
    try:
        from agents.districts.languages.japanese_coach import JapaneseCoach
        created += _reg(JapaneseCoach())
    except Exception as e:
        logger.warning(f"[bootstrap] JapaneseCoach: {e}")

    # ── Interview Prep ────────────────────────────────────────────────────────
    try:
        from agents.districts.interview_prep.mock_interviewer import MockInterviewer
        created += _reg(MockInterviewer())
    except Exception as e:
        logger.warning(f"[bootstrap] MockInterviewer: {e}")
    try:
        from agents.districts.interview_prep.company_researcher import CompanyResearcher
        created += _reg(CompanyResearcher())
    except Exception as e:
        logger.warning(f"[bootstrap] CompanyResearcher: {e}")

    # ── Agency ────────────────────────────────────────────────────────────────
    try:
        from agents.districts.agency.content_strategist import ContentStrategist
        created += _reg(ContentStrategist())
    except Exception as e:
        logger.warning(f"[bootstrap] ContentStrategist: {e}")

    # ── Investment ────────────────────────────────────────────────────────────
    try:
        from agents.districts.investment.stock_analyst import StockAnalyst
        created += _reg(StockAnalyst())
    except Exception as e:
        logger.warning(f"[bootstrap] StockAnalyst: {e}")
    try:
        from agents.districts.investment.sentiment_bot import SentimentBot
        created += _reg(SentimentBot())
    except Exception as e:
        logger.warning(f"[bootstrap] SentimentBot: {e}")

    # ── Content ───────────────────────────────────────────────────────────────
    try:
        from agents.districts.content.script_generator import ScriptGenerator
        created += _reg(ScriptGenerator())
    except Exception as e:
        logger.warning(f"[bootstrap] ScriptGenerator: {e}")
    try:
        from agents.districts.content.comfyui_adapter import ComfyUIAdapter
        created += _reg(ComfyUIAdapter())
    except Exception as e:
        logger.warning(f"[bootstrap] ComfyUIAdapter: {e}")

    # ── Skills ────────────────────────────────────────────────────────────────
    try:
        from agents.districts.skills.skill_mapper import SkillMapper
        created += _reg(SkillMapper())
    except Exception as e:
        logger.warning(f"[bootstrap] SkillMapper: {e}")
    try:
        from agents.districts.skills.mastery_tracker import MasteryTracker
        created += _reg(MasteryTracker())
    except Exception as e:
        logger.warning(f"[bootstrap] MasteryTracker: {e}")

    logger.info(f"[VECTOR][bootstrap] {created} agents registered across all districts")
    return created


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


async def run_loop() -> None:
    """Start the autonomous loop. This is intended to run until interrupted."""
    preflight_checks()
    bootstrap_agents()
    from core.loop.autonomous_loop import AutonomousLoop

    await AutonomousLoop().run_forever()


def run_api(host: str, port: int) -> None:
    """Start the local FastAPI server using the modular API over HTTPS."""
    bootstrap_agents()
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger.info(f"[VECTOR][launcher] mode={args.mode}")

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
