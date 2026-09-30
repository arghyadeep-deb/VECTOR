"""
tests/test_ops_governance_audit_phase3.py

Phase 3 behavioral-correctness audit — ops + governance slice.
Covers 3 fail-open bugs: sre_monitor.py, incident_commander.py, llm_council.py.
No real DB / Ollama / filesystem touched.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _new_agent(cls):
    """Instantiate without calling __init__ to avoid real DB/model setup."""
    agent = object.__new__(cls)
    agent.health_points = 500
    agent.name = cls.__name__
    agent._memory = None
    agent._obsidian = None
    return agent

# ── SREMonitor: error_rate fail-closed ───────────────────────────────────────

class TestSREMonitorErrorRateFailClosed:
    """
    Bug: check_system_health() set error_rate=0.0 on DB exception →
    system falsely reported as healthy when the health check itself failed.
    Fix: error_rate=1.0 (fail-closed) on any DB exception.
    """

    @pytest.mark.asyncio
    async def test_error_rate_1_on_db_failure(self):
        """DB exception during error-rate query → error_rate must be 1.0."""
        from districts.ops.sre_monitor import SREMonitor
        agent = _new_agent(SREMonitor)

        bad_cursor = MagicMock()
        bad_cursor.execute.side_effect = Exception("DB locked")
        bad_conn = MagicMock()
        bad_conn.cursor.return_value = bad_cursor
        mem_mock = MagicMock()
        mem_mock.conn = bad_conn
        mem_mock.store.return_value = None

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        async_client = AsyncMock()
        async_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(SREMonitor, "_get_memory", return_value=mem_mock),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=async_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agent.check_system_health()

        assert result.get("error_rate") == 1.0, (
            f"error_rate should be 1.0 on DB failure; got {result.get('error_rate')}"
        )
        assert result.get("overall_healthy") is False

    @pytest.mark.asyncio
    async def test_clean_db_still_yields_zero_rate(self):
        """A clean DB (no error events) must still yield error_rate=0.0."""
        from districts.ops.sre_monitor import SREMonitor
        agent = _new_agent(SREMonitor)

        rows = [("loop_tick",), ("sre_latency_probe",), ("loop_tick",)]
        good_cursor = MagicMock()
        good_cursor.fetchall.return_value = rows
        good_conn = MagicMock()
        good_conn.cursor.return_value = good_cursor
        mem_mock = MagicMock()
        mem_mock.conn = good_conn
        mem_mock.store.return_value = None

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        async_client = AsyncMock()
        async_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch.object(SREMonitor, "_get_memory", return_value=mem_mock),
            patch("httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=async_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await agent.check_system_health()

        assert result.get("error_rate") == 0.0
        assert result.get("last_100_errors") == 0

# ── IncidentCommander: detect_incidents fail-closed ──────────────────────────

class TestIncidentCommanderDetectFailClosed:
    """
    Bug: detect_incidents() returned [] on DB failure →
    caller awarded HP for 'all clear' when the DB was simply unreachable.
    Fix: return None on DB failure; callers check for None explicitly.
    """

    def test_detect_returns_none_on_db_failure(self):
        """detect_incidents() → None when DB query raises."""
        from districts.ops.incident_commander import IncidentCommander
        agent = _new_agent(IncidentCommander)

        bad_cursor = MagicMock()
        bad_cursor.execute.side_effect = Exception("DB locked")
        bad_conn = MagicMock()
        bad_conn.cursor.return_value = bad_cursor
        mem_mock = MagicMock()
        mem_mock.conn = bad_conn

        with patch.object(IncidentCommander, "_get_memory", return_value=mem_mock):
            result = agent.detect_incidents()

        assert result is None, (
            f"detect_incidents must return None on DB failure, not {result!r}"
        )

    @pytest.mark.asyncio
    async def test_detect_task_type_returns_error_status(self):
        """run({'type': 'detect'}) → status=error when detect_incidents returns None."""
        from districts.ops.incident_commander import IncidentCommander
        agent = _new_agent(IncidentCommander)

        with patch.object(agent, "detect_incidents", return_value=None):
            result = await agent.run({"type": "detect"})

        assert result["status"] == "error"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_full_scan_returns_error_and_deducts_hp_on_none(self):
        """Default full-scan: status=error + HP deduction when detect_incidents → None."""
        from districts.ops.incident_commander import IncidentCommander
        agent = _new_agent(IncidentCommander)

        initial_hp = agent.health_points
        deducted_calls = []

        def _track_deduct(points, reason=""):
            agent.health_points -= points
            deducted_calls.append(points)

        agent.deduct_points = _track_deduct
        agent.award_points = MagicMock()

        with patch.object(agent, "detect_incidents", return_value=None):
            result = await agent.run({"type": "scan"})

        assert result["status"] == "error"
        assert agent.health_points < initial_hp, "HP must be deducted on DB failure"
        assert agent.award_points.call_count == 0, (
            "award_points must NOT be called when detect_incidents fails"
        )

# ── LLMCouncil: HP gate default bypass ───────────────────────────────────────

class TestLLMCouncilHPGateDefault:
    """
    Bug: run() used requester_hp=700 as the fallback default;
    since the gate check is `< 700` (not `<=`), 700 < 700 is False,
    so any Governor dispatch that omits requester_hp bypassed the gate entirely.
    Fix: default to 0 (fail-closed).
    """

    @pytest.mark.asyncio
    async def test_missing_requester_hp_defaults_to_zero(self):
        """run() with no requester_hp in params must pass 0 to convene()."""
        from districts.governance.llm_council import LLMCouncil
        agent = _new_agent(LLMCouncil)

        captured = {}

        async def _fake_convene(question, stakes="medium", requester_hp=500, **kw):
            captured["requester_hp"] = requester_hp
            return {
                "verdict": "gated", "session_id": "x",
                "stage1": [], "stage2": [], "aggregate_rankings": [],
            }

        agent.convene = _fake_convene

        await agent.run({"type": "governance", "params": {"question": "Q?", "stakes": "high"}})

        assert captured.get("requester_hp") == 0, (
            f"Missing requester_hp must default to 0 (fail-closed), got {captured.get('requester_hp')}"
        )

    @pytest.mark.asyncio
    async def test_explicit_requester_hp_passes_through(self):
        """An explicit requester_hp value must pass through to convene() unchanged."""
        from districts.governance.llm_council import LLMCouncil
        agent = _new_agent(LLMCouncil)

        captured = {}

        async def _fake_convene(question, stakes="medium", requester_hp=500, **kw):
            captured["requester_hp"] = requester_hp
            return {
                "verdict": "ok", "session_id": "x",
                "stage1": [], "stage2": [], "aggregate_rankings": [],
            }

        agent.convene = _fake_convene

        await agent.run({"type": "governance", "params": {"question": "Q?", "requester_hp": 750}})

        assert captured.get("requester_hp") == 750
