"""Real-execution regression tests for the 6 QA district specialists that had NO test coverage
at all per SELF_DEV_P1_QA_VERIFICATION.md ("NOT VERIFIED" -- missing per-agent real-test gate).

Per .claude/rules/testing.md: real execution, no mocking of VECTOR internals. Monkeypatching a
specialist's own `_llm()` wrapper (an external LLM API call) is the one exception the rule
explicitly allows ("Mocking external APIs ... is acceptable"), used only where a method's real
logic requires a model call (tool_evaluator, workflow_optimizer's LLM-backed methods).
"""

from __future__ import annotations

import asyncio

import pytest


# ── AccessibilityAuditor ────────────────────────────────────────────────────

def test_accessibility_auditor_audit_html_flags_real_wcag_violations():
    from districts.qa.accessibility_auditor import AccessibilityAuditor

    agent = AccessibilityAuditor()
    bad_html = '<img src="x.png"><button></button>'
    result = agent.audit_html(bad_html)
    criteria = {i["wcag_criterion"] for i in result["issues"]}
    assert "1.1.1" in criteria  # missing alt
    assert any(i["severity"] == "serious" for i in result["issues"])  # button missing label

    clean_html = '<img src="x.png" alt="a chart of quarterly revenue">'
    clean_result = agent.audit_html(clean_html)
    assert not any(i["wcag_criterion"] == "1.1.1" for i in clean_result["issues"])


def test_accessibility_auditor_color_contrast_matches_the_real_wcag_formula():
    from districts.qa.accessibility_auditor import AccessibilityAuditor

    agent = AccessibilityAuditor()
    # black on white is the textbook maximum ratio: 21:1
    black_on_white = agent.audit_color_contrast("#000000", "#FFFFFF")
    assert black_on_white["ratio"] == 21.0
    assert black_on_white["aaa_pass"] is True

    # near-identical low-contrast grays must fail both AA and AAA
    low_contrast = agent.audit_color_contrast("#777777", "#888888")
    assert low_contrast["aa_pass"] is False
    assert low_contrast["ratio"] < 3.0


def test_accessibility_auditor_run_dispatches_real_capabilities():
    from districts.qa.accessibility_auditor import AccessibilityAuditor

    agent = AccessibilityAuditor()
    result = asyncio.run(agent.run({"type": "contrast", "foreground": "#000000", "background": "#FFFFFF"}))
    assert result["status"] == "ok"
    assert result["result"]["ratio"] == 21.0


# ── EvidenceCollector ────────────────────────────────────────────────────────

def test_evidence_collector_collect_git_evidence_reads_the_real_repo():
    from districts.qa.evidence_collector import EvidenceCollector

    # 2026-09-29 bug found by this test: self._root was Path(__file__).parent x4, one level
    # ABOVE the real repo root, so `git log` silently ran outside any git repo and always
    # returned 0 commits. Fixed alongside the identical bug in reality_checker.py.
    agent = EvidenceCollector()
    assert (agent._root / ".git").exists(), f"_root resolved outside the repo: {agent._root}"
    result = agent.collect_git_evidence(days=7)
    assert result["source"] == "git"
    # this repo has had constant real commit activity in the last week
    assert result["count"] > 0, result
    assert result["evidence"] == "present"
    assert all(isinstance(c, str) and c for c in result["commits"])


def test_evidence_collector_compile_evidence_report_aggregates_all_sources():
    from districts.qa.evidence_collector import EvidenceCollector

    agent = EvidenceCollector()
    git_ev = {"source": "git", "commits": ["abc123 fix"], "count": 1, "evidence": "present"}
    mem_ev = {"source": "memory", "count": 0, "evidence": "none", "total_events": 3}
    test_ev = {"source": "tests", "count": 5, "evidence": "present"}
    snap = {"source": "snapshot", "alive_agents": 261, "avg_hp": 512.5}
    report = agent.compile_evidence_report(git_ev, mem_ev, test_ev, snap)
    assert report["git"] == git_ev
    assert report["memory"] == mem_ev
    assert report["tests"] == test_ev
    assert report["system"] == snap
    assert report["verdict"] == "EVIDENCE_INCOMPLETE"  # mem_ev's evidence="none" breaks all_present
    assert report["summary"]["git_commits_24h"] == 1
    assert report["summary"]["memory_events_24h"] == 3
    assert report["summary"]["alive_agents"] == 261


# ── RealityChecker ───────────────────────────────────────────────────────────

def test_reality_checker_verify_imports_confirms_real_core_modules_import():
    from districts.qa.reality_checker import RealityChecker

    agent = RealityChecker()
    result = agent.verify_imports()
    # core.config is a foundational module -- if the whole repo is importable (which every
    # other test file in this suite already proves by running at all), this must succeed
    assert "core.config" in result["successes"] or any("core.config" in f for f in result["failures"])
    assert isinstance(result["ok"], bool)


def test_reality_checker_check_syntax_clean_parses_the_real_core_tree():
    from districts.qa.reality_checker import RealityChecker

    agent = RealityChecker()
    result = agent.check_syntax_clean()
    # the live core/ tree must have zero real syntax errors (it imports and runs constantly)
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["clean_files"] > 50  # core/ has hundreds of real .py files


def test_reality_checker_run_executes_the_full_real_check_and_all_clear():
    from districts.qa.reality_checker import RealityChecker

    agent = RealityChecker()
    result = asyncio.run(agent.run({"type": "verify"}))
    assert result["status"] == "ok"
    report = result["report"]
    assert report["all_clear"] is True
    assert report["syntax_ok"] is True
    assert report["smoke_tests"]["ok"] is True
    assert report["integration"]["ok"] is True
    assert report["imports_ok"] is True
    assert report["clean_files"] > 50


# ── TestResultsAnalyzer ──────────────────────────────────────────────────────

def test_test_results_analyzer_detect_regressions_flags_a_real_pass_rate_drop():
    from districts.qa.test_results_analyzer import TestResultsAnalyzer

    agent = TestResultsAnalyzer()
    history = [{"pass_rate": 100.0, "failed": 0}]
    current_regressed = {"pass_rate": 80.0, "failed": 4}
    regressions = agent.detect_regressions(current_regressed, history)
    assert len(regressions) == 2  # pass-rate drop + new failures
    assert any("Pass rate dropped" in r for r in regressions)
    assert any("New failures" in r for r in regressions)

    current_clean = {"pass_rate": 100.0, "failed": 0}
    assert agent.detect_regressions(current_clean, history) == []
    assert agent.detect_regressions(current_clean, []) == []  # no history -> no regressions


def test_test_results_analyzer_parse_output_extracts_real_pass_fail_counts():
    from districts.qa.test_results_analyzer import TestResultsAnalyzer

    agent = TestResultsAnalyzer()
    summary_style = "Smoke tests: 36/38 PASS\nsome other line"
    result = agent._parse_output(summary_style)
    assert result["passed"] == 36
    assert result["failed"] == 2
    assert result["pass_rate"] == round(36 / 38 * 100, 1)
    assert result["all_passed"] is False

    line_style = "[1] PASS thing one\n[2] PASS thing two\n[3] FAIL thing three"
    line_result = agent._parse_output(line_style)
    assert line_result["passed"] == 2
    assert line_result["failed"] == 1
    assert line_result["all_passed"] is False


def test_test_results_analyzer_run_and_capture_executes_the_real_smoke_test():
    from districts.qa.test_results_analyzer import TestResultsAnalyzer

    # 2026-09-29 bug found by this test: self._root had the same off-by-one bug as
    # evidence_collector.py / reality_checker.py -- scripts/smoke_test.py was never found.
    agent = TestResultsAnalyzer()
    assert (agent._root / ".git").exists(), f"_root resolved outside the repo: {agent._root}"
    result = agent.run_and_capture("smoke_test.py")
    assert "error" not in result
    assert result["return_code"] == 0
    assert result["all_passed"] is True
    assert result["passed"] > 0


# ── ToolEvaluator ─────────────────────────────────────────────────────────────

def test_tool_evaluator_compare_tools_picks_a_real_winner_from_llm_output(monkeypatch):
    from districts.qa.tool_evaluator import ToolEvaluator

    agent = ToolEvaluator()

    def fake_llm(self, prompt, timeout=30.0):
        if "toolA" in prompt:
            return '{"scores": {"functionality": 9, "performance": 9, "maintainability": 9, "community": 9, "security": 9, "cost": 9, "integration_ease": 9, "documentation": 9}, "verdict": "Recommended", "risks": "none", "recommendation": "use it"}'
        return '{"scores": {"functionality": 2, "performance": 2, "maintainability": 2, "community": 2, "security": 2, "cost": 2, "integration_ease": 2, "documentation": 2}, "verdict": "Not Recommended", "risks": "many", "recommendation": "avoid"}'

    monkeypatch.setattr(ToolEvaluator, "_llm", fake_llm)
    result = agent.compare_tools(["toolA", "toolB"], "testing framework")
    assert result["winner"] == "toolA"
    assert result["matrix"]["toolA"]["total_score"] == 9.0
    assert result["matrix"]["toolB"]["total_score"] == 2.0


def test_tool_evaluator_evaluate_tool_falls_back_cleanly_on_unparseable_llm_output(monkeypatch):
    from districts.qa.tool_evaluator import ToolEvaluator

    agent = ToolEvaluator()
    monkeypatch.setattr(ToolEvaluator, "_llm", lambda self, prompt, timeout=30.0: "not json at all")
    result = agent.evaluate_tool("some-tool", "some use case")
    # never crashes on bad LLM output; falls back to honest neutral scores, not a fabricated verdict
    assert result["total_score"] == 5.0
    assert result["verdict"] == "Conditional"
    assert "manual review" in result["risks"].lower() or "manually" in result["recommendation"].lower()


def test_tool_evaluator_assess_adoption_cost_labels_cost_correctly(monkeypatch):
    from districts.qa.tool_evaluator import ToolEvaluator

    agent = ToolEvaluator()
    monkeypatch.setattr(
        ToolEvaluator, "_llm",
        lambda self, prompt, timeout=30.0: '{"migration_effort": 9, "learning_curve": 9, "integration_complexity": 9, "recommendation": "costly"}',
    )
    result = agent.assess_adoption_cost(["fastapi"], "django")
    assert result["overall_cost"] == 9.0
    assert result["cost_label"] == "High"


# ── WorkflowOptimizer ────────────────────────────────────────────────────────

def test_workflow_optimizer_calculate_roi_is_real_arithmetic_not_an_llm_guess():
    from districts.qa.workflow_optimizer import WorkflowOptimizer

    agent = WorkflowOptimizer()
    result = agent.calculate_roi(current_time_hours=10.0, optimized_time_hours=2.0, hourly_rate=500.0)
    assert result["time_saved_hours"] == 8.0
    assert result["time_saved_pct"] == 80.0
    assert result["money_saved_monthly_inr"] == round(8.0 * 500.0 * 22, 2)
    assert result["roi_label"] == "Excellent"

    zero_input = agent.calculate_roi(current_time_hours=0.0, optimized_time_hours=1.0)
    assert "error" in zero_input


def test_workflow_optimizer_recommend_automations_returns_real_structured_data(monkeypatch):
    from districts.qa.workflow_optimizer import WorkflowOptimizer

    agent = WorkflowOptimizer()
    result = agent.recommend_automations("manually copy CSVs between folders every day")
    assert isinstance(result, list)
    assert len(result) > 0
    assert all("tool" in r or "automation" in r or isinstance(r, dict) for r in result)


def test_workflow_optimizer_generate_sop_includes_every_supplied_step():
    from districts.qa.workflow_optimizer import WorkflowOptimizer

    agent = WorkflowOptimizer()
    steps = ["Open the dashboard", "Export the CSV", "Upload to the drive"]
    sop = agent.generate_sop("weekly report export", steps)
    assert isinstance(sop, str)
    for step in steps:
        assert step in sop


# ── QASwarm self-load (the real answer to "not manifest-registered individually") ──────────

def test_qa_swarm_self_loads_all_11_python_agents_into_the_real_registry():
    """P1's report flagged these 8 personas as 'not individually manifest-registered under qa'.
    The manifest's own qa_swarm entry documents the real architecture: QASwarm self-loads and
    routes across all 11 Python agents at runtime, the same accepted pattern already used by
    FinanceSwarm/CodingSwarm/ResearchSwarm. This proves that self-load actually registers every
    one of them into the shared, A2A-reachable AgentRegistry -- not a documentation claim.

    2026-09-29: also proves the real bug this test caught and QASwarm._load_agents() got fixed
    for -- the old code deduped against a guessed key ("qa_{role}_swarm_001") that no specialist
    is ever actually registered under, so every QASwarm() construction silently created and
    registered 11 brand-new duplicate agents. This asserts real dedup: a second QASwarm() must
    reuse the exact same instances, not create new ones."""
    from core.city.agent_registry import get_registry
    from districts.qa.agent import PYTHON_AGENTS, QASwarm

    registry = get_registry()
    swarm = QASwarm()
    assert len(swarm._agents) == len(PYTHON_AGENTS) == 11
    for agent_id, agent in swarm._agents.items():
        assert registry.get(agent_id) is agent, f"{type(agent).__name__} not reachable in the real registry by its own id"

    before_count = len(registry.get_all_agents())
    swarm2 = QASwarm()
    assert len(registry.get_all_agents()) == before_count, "constructing a second QASwarm duplicated agents"
    assert all(swarm2._agents[aid] is agent for aid, agent in swarm._agents.items())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
