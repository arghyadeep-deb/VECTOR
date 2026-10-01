"""
Tests for Phase 2 districts:
- Reflection: DailyReviewer, JournalWriter, GrowthAnalyst
- Health: SleepTracker, FatigueMonitor, ExerciseLogger
- Finance: UPIParser, ExpenseTracker, BudgetAnalyst, TaxCalendar
- Projects: ProjectPlanner, DeadlineWatcher, ProgressTracker, DocWriter
"""
import sys
import asyncio
import datetime
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


# ─── Reflection ───────────────────────────────────────────────────────────────

def test_daily_reviewer_init():
    from districts.reflection.daily_reviewer import DailyReviewer
    bot = DailyReviewer()
    assert bot.health_points == 500
    assert bot.name == "DailyReviewer"
    assert bot.district == "reflection"


def test_daily_reviewer_fetch_today_empty():
    from districts.reflection.daily_reviewer import DailyReviewer
    bot = DailyReviewer()
    events = bot._fetch_today()
    assert isinstance(events, list)


def test_daily_reviewer_extract_policy_rules():
    from districts.reflection.daily_reviewer import DailyReviewer
    bot = DailyReviewer()
    text = (
        "## WINS\nSomething good\n"
        "## POLICY_UPDATES\nIf X then always Y\nNever do Z\n"
        "## GROWTH_SCORE\n8/10\n"
    )
    rules = bot._extract_policy_rules(text)
    assert len(rules) == 2
    assert "If X then always Y" in rules


def test_daily_reviewer_review_llm_unavailable():
    from districts.reflection.daily_reviewer import DailyReviewer
    bot = DailyReviewer()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Reflections").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", side_effect=Exception("offline")), \
             patch("ollama.chat", side_effect=Exception("offline")):
            ok = asyncio.run(bot.review())
    assert ok is True
    assert bot.health_points > 0


def test_journal_writer_init():
    from districts.reflection.journal_writer import JournalWriter
    bot = JournalWriter()
    assert bot.health_points == 500
    assert bot.name == "JournalWriter"


def test_journal_writer_daily_llm_unavailable():
    from districts.reflection.journal_writer import JournalWriter
    bot = JournalWriter()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Journals").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", side_effect=Exception("offline")), \
             patch("ollama.chat", side_effect=Exception("offline")):
            ok = asyncio.run(bot.write_daily())
    assert ok is True


def test_journal_writer_weekly_llm_unavailable():
    from districts.reflection.journal_writer import JournalWriter
    bot = JournalWriter()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Reviews").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", side_effect=Exception("offline")), \
             patch("ollama.chat", side_effect=Exception("offline")):
            ok = asyncio.run(bot.write_weekly())
    assert ok is True


def test_growth_analyst_init():
    from districts.reflection.growth_analyst import GrowthAnalyst
    bot = GrowthAnalyst()
    assert bot.health_points == 500
    assert bot.name == "GrowthAnalyst"


def test_growth_analyst_analyse_llm_unavailable():
    from districts.reflection.growth_analyst import GrowthAnalyst
    bot = GrowthAnalyst()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Reflections").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", side_effect=Exception("offline")), \
             patch("ollama.chat", side_effect=Exception("offline")):
            ok = asyncio.run(bot.analyse())
    assert ok is True


# ─── Health ───────────────────────────────────────────────────────────────────

def test_sleep_tracker_init():
    from districts.health.sleep_tracker import SleepTracker
    bot = SleepTracker()
    assert bot.health_points == 500
    assert bot.name == "SleepTracker"


def test_sleep_tracker_quality_labels():
    from districts.health.sleep_tracker import SleepTracker
    bot = SleepTracker()
    assert bot._quality_label(8.5) == "excellent"
    assert bot._quality_label(7.0) == "good"
    assert bot._quality_label(6.5) == "fair"
    assert bot._quality_label(5.0) == "poor"
    assert bot._quality_label(2.0) == "very poor"


def test_sleep_tracker_track_no_data():
    from districts.health.sleep_tracker import SleepTracker
    bot = SleepTracker()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Health").mkdir()
        bot._obsidian._vault = vault
        ok = asyncio.run(bot.track())
    assert ok is True


def test_fatigue_monitor_init():
    from districts.health.fatigue_monitor import FatigueMonitor
    bot = FatigueMonitor()
    assert bot.health_points == 500
    assert bot.name == "FatigueMonitor"


def test_fatigue_monitor_check_once():
    from districts.health.fatigue_monitor import FatigueMonitor
    bot = FatigueMonitor()
    result = asyncio.run(bot.check_once())
    assert "fatigue" in result
    assert isinstance(result["fatigue"], bool)
    assert "session_minutes" in result


def test_fatigue_monitor_session_tracking():
    from districts.health.fatigue_monitor import FatigueMonitor
    bot = FatigueMonitor()
    assert bot._session_minutes() == 0.0
    bot._session_start = datetime.datetime.now() - datetime.timedelta(minutes=30)
    assert 29.0 <= bot._session_minutes() <= 31.0


def test_exercise_logger_init():
    from districts.health.exercise_logger import ExerciseLogger
    bot = ExerciseLogger()
    assert bot.health_points == 500
    assert bot.name == "ExerciseLogger"


def test_exercise_logger_log_session():
    from districts.health.exercise_logger import ExerciseLogger
    bot = ExerciseLogger()
    ok = bot.log_session("Running", 30, "Morning jog")
    assert ok is True
    assert bot.health_points > 500  # HP awarded


def test_exercise_logger_weekly_report():
    from districts.health.exercise_logger import ExerciseLogger
    bot = ExerciseLogger()
    bot.log_session("Yoga", 20)
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Health").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", side_effect=Exception("offline")), \
             patch("ollama.chat", side_effect=Exception("offline")):
            ok = asyncio.run(bot.weekly_report())
    assert ok is True


# ─── Finance ──────────────────────────────────────────────────────────────────

def test_upi_parser_init():
    from districts.finance.upi_parser import UPIParser
    bot = UPIParser()
    assert bot.health_points == 500
    assert bot.name == "UPIParser"


def test_upi_parser_debit():
    from districts.finance.upi_parser import UPIParser
    bot = UPIParser()
    txn = bot.ingest("Rs.250 debited from A/C XX1234 to Zomato on 07-05-2026. UPI Ref: 123456")
    assert txn is not None
    assert txn["amount"] == 250.0
    assert txn["direction"] == "debit"
    assert txn["category"] == "food"


def test_upi_parser_credit():
    from districts.finance.upi_parser import UPIParser
    bot = UPIParser()
    txn = bot.ingest("Rs.1000 credited to A/C XX1234 from PhonePe on 07-05-2026.")
    assert txn is not None
    assert txn["direction"] == "credit"


def test_upi_parser_non_financial():
    from districts.finance.upi_parser import UPIParser
    bot = UPIParser()
    txn = bot.ingest("Your OTP is 123456. Do not share with anyone.")
    assert txn is None


def test_upi_parser_categories():
    from districts.finance.upi_parser import parse_sms
    food_txn = parse_sms("Rs.150 debited to Swiggy Order")
    assert food_txn["category"] == "food"

    transport_txn = parse_sms("Rs.80 debited to Ola Cabs UPI")
    assert transport_txn["category"] == "transport"


def test_expense_tracker_init():
    from districts.finance.expense_tracker import ExpenseTracker
    bot = ExpenseTracker()
    assert bot.health_points == 500
    assert bot.name == "ExpenseTracker"


def test_expense_tracker_summarise_empty():
    from districts.finance.expense_tracker import ExpenseTracker
    bot = ExpenseTracker()
    summary = bot.summarise(days=30)
    assert "total_debit" in summary
    assert "by_category" in summary
    assert summary["total_debit"] >= 0


def test_expense_tracker_monthly_report():
    from districts.finance.expense_tracker import ExpenseTracker
    bot = ExpenseTracker()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Finance").mkdir()
        bot._obsidian._vault = vault
        ok = asyncio.run(bot.write_monthly_report())
    assert ok is True


def test_budget_analyst_init():
    from districts.finance.budget_analyst import BudgetAnalyst
    bot = BudgetAnalyst()
    assert bot.health_points == 500
    assert bot.name == "BudgetAnalyst"


def test_budget_analyst_over_budget_detection():
    from districts.finance.budget_analyst import BudgetAnalyst
    bot = BudgetAnalyst()
    # Inject spend above food budget
    spend = {"food": 5000.0, "transport": 500.0}
    over = bot._over_budget_categories(spend)
    assert any(o["category"] == "food" for o in over)
    food_over = next(o for o in over if o["category"] == "food")
    assert food_over["overage"] == 2000.0  # 5000 - 3000 default


def test_budget_analyst_within_budget():
    from districts.finance.budget_analyst import BudgetAnalyst
    bot = BudgetAnalyst()
    spend = {"food": 100.0}
    over = bot._over_budget_categories(spend)
    assert len(over) == 0


def test_budget_analyst_analyse():
    from districts.finance.budget_analyst import BudgetAnalyst
    bot = BudgetAnalyst()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Finance").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", side_effect=Exception("offline")), \
             patch("ollama.chat", side_effect=Exception("offline")):
            ok = asyncio.run(bot.analyse())
    # analyse() returns the report text (str) on success, None on failure —
    # deliberately changed 2026-07-22 so run() could surface real content
    # instead of a bare stub; it never returned a bool (unlike the sibling
    # review()/write_daily()/write_weekly() methods above, which still do).
    assert ok is not None
    assert "Budget Analysis" in ok


def test_tax_calendar_init():
    from districts.finance.tax_calendar import TaxCalendar
    bot = TaxCalendar()
    assert bot.health_points == 500
    assert bot.name == "TaxCalendar"


def test_tax_calendar_upcoming_deadlines():
    from districts.finance.tax_calendar import TaxCalendar
    bot = TaxCalendar()
    deadlines = bot.upcoming_deadlines(within_days=365)
    assert len(deadlines) > 0
    assert all("date" in d for d in deadlines)
    assert all("label" in d for d in deadlines)
    assert all("days_away" in d for d in deadlines)


def test_tax_calendar_sorted_by_days():
    from districts.finance.tax_calendar import TaxCalendar
    bot = TaxCalendar()
    deadlines = bot.upcoming_deadlines(within_days=365)
    days = [d["days_away"] for d in deadlines]
    assert days == sorted(days)


def test_tax_calendar_write_note():
    from districts.finance.tax_calendar import TaxCalendar
    bot = TaxCalendar()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Finance").mkdir()
        bot._obsidian._vault = vault
        ok = asyncio.run(bot.write_calendar_note())
    assert ok is True


# ─── Projects ─────────────────────────────────────────────────────────────────

def test_project_planner_init():
    from districts.projects.project_planner import ProjectPlanner
    bot = ProjectPlanner()
    assert bot.health_points == 500
    assert bot.name == "ProjectPlanner"


def test_project_planner_create_project():
    from districts.projects.project_planner import ProjectPlanner
    bot = ProjectPlanner()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Projects").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", side_effect=Exception("offline")), \
             patch("ollama.chat", side_effect=Exception("offline")):
            proj = bot.create_project("Test Project", "Build something useful", "2026-12-31")
    assert proj["id"]
    assert proj["name"] == "Test Project"
    assert proj["deadline"] == "2026-12-31"


def test_project_planner_list_active():
    from districts.projects.project_planner import ProjectPlanner
    bot = ProjectPlanner()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Projects").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", side_effect=Exception("offline")), \
             patch("ollama.chat", side_effect=Exception("offline")):
            bot.create_project("P1", "Goal 1", "2026-06-01")
            bot.create_project("P2", "Goal 2", "2026-07-01")
    projects = bot.list_active_projects()
    assert len(projects) >= 2


def test_deadline_watcher_init():
    from districts.projects.deadline_watcher import DeadlineWatcher
    bot = DeadlineWatcher()
    assert bot.health_points == 500
    assert bot.name == "DeadlineWatcher"


def test_deadline_watcher_add_and_check():
    from districts.projects.deadline_watcher import DeadlineWatcher
    bot = DeadlineWatcher()
    future = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    bot.add_deadline("Sprint Review", future, urgency="high")
    fired = asyncio.run(bot.check())
    assert any(d["name"] == "Sprint Review" for d in fired)


def test_deadline_watcher_no_duplicates():
    from districts.projects.deadline_watcher import DeadlineWatcher
    bot = DeadlineWatcher()
    future = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    bot.add_deadline("Unique Task", future)
    fired1 = asyncio.run(bot.check())
    fired2 = asyncio.run(bot.check())  # same day — should not fire again
    assert len(fired2) == 0


def test_progress_tracker_init():
    from districts.projects.progress_tracker import ProgressTracker
    bot = ProgressTracker()
    assert bot.health_points == 500
    assert bot.name == "ProgressTracker"


def test_progress_tracker_log():
    from districts.projects.progress_tracker import ProgressTracker
    bot = ProgressTracker()
    initial_hp = bot.health_points
    bot.log_progress("vec001", "Milestone 1 done", "shipped on time")
    assert bot.health_points > initial_hp


def test_progress_tracker_weekly_report():
    from districts.projects.progress_tracker import ProgressTracker
    bot = ProgressTracker()
    bot.log_progress("vec001", "Phase 2 complete")
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Projects").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", side_effect=Exception("offline")), \
             patch("ollama.chat", side_effect=Exception("offline")):
            ok = asyncio.run(bot.weekly_report())
    assert ok is True


def test_doc_writer_init():
    from districts.projects.doc_writer import DocWriter
    bot = DocWriter()
    assert bot.health_points == 500
    assert bot.name == "DocWriter"


def test_doc_writer_invalid_type():
    from districts.projects.doc_writer import DocWriter
    bot = DocWriter()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Projects").mkdir()
        bot._obsidian._vault = vault
        ok = bot.write_doc("Project", "invalid_type")
    assert ok is False


def test_doc_writer_readme():
    from districts.projects.doc_writer import DocWriter
    bot = DocWriter()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Projects").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", return_value="## Overview\nreal doc"):
            ok = bot.write_doc("VECTOR", "readme", context="Autonomous AI agent")
    assert ok is True


def test_doc_writer_all_types():
    from districts.projects.doc_writer import DocWriter
    bot = DocWriter()
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Projects").mkdir()
        bot._obsidian._vault = vault
        with patch("core.inference.vectorcode_llm.chat", return_value="## Overview\nreal doc"):
            for doc_type in DocWriter.DOC_TYPES:
                ok = bot.write_doc("TestProj", doc_type)
                assert ok is True, f"Failed for doc_type={doc_type}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
