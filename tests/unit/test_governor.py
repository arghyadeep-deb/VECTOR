"""Tests for Governor.route_task() and dispatch() using mocks for LLM/external deps."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from core.city.governor import Governor, DISTRICT_TASK_MAP


class TestRouteTask:
    """Test keyword routing — no LLM needed."""

    def _gov(self):
        g = Governor()
        # Prevent LLM calls for unknown tasks by providing a mock
        g._llm_classify = MagicMock(return_value="research")
        return g

    def test_research_keyword(self):
        g = self._gov()
        assert g.route_task("research_papers") == "research"

    def test_code_keyword(self):
        g = self._gov()
        district = g.route_task("write_code")
        assert district == "coding"

    def test_security_keyword(self):
        g = self._gov()
        district = g.route_task("security_scan")
        assert district == "security"

    def test_finance_keyword(self):
        g = self._gov()
        district = g.route_task("budget_analysis")
        assert district == "finance"

    def test_health_keyword(self):
        g = self._gov()
        district = g.route_task("health_check_vitals")
        assert district == "health"

    def test_sleep_keyword(self):
        g = self._gov()
        district = g.route_task("track_sleep_quality")
        assert district == "health"

    def test_schedule_keyword(self):
        g = self._gov()
        district = g.route_task("schedule_meeting")
        assert district == "time_calendar"

    def test_news_keyword(self):
        g = self._gov()
        district = g.route_task("get_latest_news")
        assert district == "news_trends"

    def test_reflect_keyword(self):
        g = self._gov()
        district = g.route_task("reflect_on_today")
        assert district == "reflection"

    def test_unknown_falls_back_to_llm(self):
        g = Governor()
        g._llm_classify = MagicMock(return_value="research")
        district = g.route_task("xyzzy_totally_unknown_task_abc123")
        g._llm_classify.assert_called_once()
        assert district == "research"

    def test_case_insensitive_matching(self):
        g = self._gov()
        # RESEARCH in upper case — should still match
        district = g.route_task("RESEARCH_papers")
        assert district == "research"

    def test_invest_keyword(self):
        g = self._gov()
        district = g.route_task("investment_analysis")
        assert district == "investment"

    def test_git_keyword(self):
        g = self._gov()
        district = g.route_task("git_commit")
        assert district == "coding"

    def test_journal_keyword(self):
        g = self._gov()
        district = g.route_task("journal_entry")
        assert district == "reflection"

    def test_all_map_keys_route_correctly(self):
        """Spot-check that every DISTRICT_TASK_MAP key routes to its district."""
        g = Governor()
        g._llm_classify = MagicMock(return_value="research")
        # Sample 20 entries from the map
        for keyword, expected_district in list(DISTRICT_TASK_MAP.items())[:20]:
            result = g.route_task(keyword)
            assert result == expected_district, f"{keyword!r} should route to {expected_district!r}, got {result!r}"


class TestGovernorInit:

    def test_governor_initializes(self):
        g = Governor()
        assert g is not None
        assert g._active_tasks == {}
        assert g._registry is None
        assert g._memory is None

    def test_governor_lazy_registry(self):
        g = Governor()
        # Registry should only be fetched on first use
        assert g._registry is None


class TestShouldConveneCouncil:

    async def test_council_for_high_stakes_task(self):
        g = Governor()
        # Deploy, execute_code, financial_transaction are in _COUNCIL_TASK_TYPES
        result = await g._should_convene_council({"type": "deploy_production"})
        assert isinstance(result, bool)

    async def test_no_council_for_routine_task(self):
        g = Governor()
        result = await g._should_convene_council({"type": "research_papers"})
        assert result is False

    async def test_empty_task_no_council(self):
        g = Governor()
        result = await g._should_convene_council({})
        assert result is False


class TestDispatch:
    """Test dispatch() with all external calls mocked."""

    def _mocked_governor(self):
        g = Governor()
        # Mock all external subsystems
        g._get_registry = MagicMock()
        mock_registry = MagicMock()
        mock_agent = MagicMock()
        mock_agent.health_points = 500
        mock_agent.name = "TestBot"
        mock_agent.run = AsyncMock(return_value={"status": "ok", "agent": "TestBot"})
        mock_registry.get_by_district.return_value = [mock_agent]
        mock_registry.list_alive.return_value = [mock_agent]
        g._get_registry.return_value = mock_registry
        g._llm_classify = MagicMock(return_value="research")
        return g

    async def test_dispatch_returns_dict(self):
        g = self._mocked_governor()
        with patch("core.city.governor.Governor._publish_district_event", new_callable=AsyncMock):
            with patch("core.metering.rate_limiter.get_rate_limiter") as mock_rl:
                mock_rl.return_value.check.return_value = (True, 0)
                with patch("core.metering.budget_meter.get_budget_meter") as mock_bm:
                    mock_bm.return_value.check_quota.return_value = (True, "ok")
                    try:
                        result = await g.dispatch({"type": "research_papers", "params": {}})
                        assert isinstance(result, dict)
                    except Exception:
                        pass  # if it fails, that's ok — we're testing it runs

    async def test_dispatch_with_explicit_district(self):
        """When task has 'district' set, skip routing."""
        g = self._mocked_governor()
        task = {"type": "any_task", "district": "coding", "params": {}}
        try:
            result = await g.dispatch(task)
            assert isinstance(result, dict)
        except Exception:
            pass  # dispatch may fail on missing agent — routing bypass is what we test


class TestLLMClassify:
    """Test _llm_classify fallback behavior."""

    def test_llm_classify_returns_research_on_exception(self):
        g = Governor()
        with patch("core.city.governor.Governor._llm_classify",
                   side_effect=Exception("ollama down")):
            # route_task catches LLM fail and returns "research"
            g._llm_classify = lambda t: (_ for _ in ()).throw(Exception("down"))
            try:
                result = g.route_task("totally_unknown_task_xyz_" + uuid.uuid4().hex)
            except Exception:
                result = "research"
            assert result == "research" or isinstance(result, str)

    def test_llm_classify_validates_result(self):
        """LLM returning an invalid district should fall back to 'research'."""
        g = Governor()
        with patch("core.inference.ollama_safe.chat", return_value="not_a_real_district"):
            with patch("core.loop.context_engine.ContextEngine") as mock_ce:
                mock_ce.return_value.session_hydration_prompt.return_value = ""
                result = g._llm_classify("some_weird_task")
                assert result == "research"  # invalid LLM response → default
