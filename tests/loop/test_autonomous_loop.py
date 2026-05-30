"""Tests for the autonomous loop — the heart of VECTOR."""


import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestAutonomousLoop:
    """Test critical path methods in isolation."""

    @pytest.mark.asyncio
    async def test_parse_cron_daily_valid(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        result = loop._parse_cron_daily("30 8 * * *")
        assert result == (8, 30)

    @pytest.mark.asyncio
    async def test_parse_cron_daily_non_daily(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        result = loop._parse_cron_daily("30 8 * * 1")
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_cron_daily_invalid(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        result = loop._parse_cron_daily("not a cron")
        assert result is None

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        loop._running = True
        loop.stop()
        assert loop._running is False

    @pytest.mark.asyncio
    async def test_scan_threats_runs_without_error(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        with patch.object(loop, '_get_scheduler') as mock_sched:
            mock_sched.return_value = None
            result = loop._scan_threats("test action", context="act")
            assert result in (True, False)

    @pytest.mark.asyncio
    async def test_dispatch_event_to_agent_timeout(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        agent = AsyncMock()
        agent.handle_event = AsyncMock(side_effect=asyncio.TimeoutError)
        event = MagicMock()
        with pytest.raises(asyncio.TimeoutError):
            await loop._dispatch_event_to_agent(agent, event)
