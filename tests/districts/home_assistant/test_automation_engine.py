import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from districts.home_assistant.automation_engine import AutomationRule, SceneManager, AutomationEngine
from districts.home_assistant.connector import HAConfig


class TestAutomationRule:
    def test_create_rule(self):
        rule = AutomationRule(name="test", trigger="time", conditions={"hour": 23}, cooldown_seconds=60)
        assert rule.name == "test"
        assert rule.trigger == "time"


class TestSceneManager:
    @pytest.mark.asyncio
    async def test_list_scenes(self):
        conn = AsyncMock()
        mgr = SceneManager(conn)
        scenes = mgr.list_scenes()
        assert "morning" in scenes
        assert "night" in scenes
        assert "away" in scenes
        assert "movie" in scenes

    @pytest.mark.asyncio
    async def test_activate_unknown(self):
        conn = AsyncMock()
        mgr = SceneManager(conn)
        result = await mgr.activate("nonexistent")
        assert result is False


class TestAutomationEngine:
    @pytest.mark.asyncio
    async def test_builtin_rules_present(self):
        conn = AsyncMock()
        mgr = MagicMock()
        engine = AutomationEngine(conn, mgr)
        rules = engine.get_rules()
        assert "nighttime_auto_off" in rules
        assert "morning_wakeup" in rules
        assert "away_mode" in rules
        assert "arrival_mode" in rules
        assert "movie_mode" in rules
        assert "security_breach" in rules
        assert "going_to_bed" in rules

    @pytest.mark.asyncio
    async def test_cooldown_respects(self):
        conn = AsyncMock()
        mgr = MagicMock()
        engine = AutomationEngine(conn, mgr)
        context = {"hour": 23, "minute": 0}
        first = await engine.evaluate_triggers(context)
        assert "nighttime_auto_off" in first
        second = await engine.evaluate_triggers(context)
        assert "nighttime_auto_off" not in second

    @pytest.mark.asyncio
    async def test_add_and_remove_rule(self):
        conn = AsyncMock()
        mgr = MagicMock()
        engine = AutomationEngine(conn, mgr)
        rule = AutomationRule(name="custom_test", trigger="event", conditions={"event_type": "custom"}, actions=[])
        engine.add_rule(rule)
        assert "custom_test" in engine.get_rules()
        engine.remove_rule("custom_test")
        assert "custom_test" not in engine.get_rules()
