"""
Regression tests for the security-district fake-success-stub bug.

AgentBase.run() (core/city/agent_base.py) defines a generic fallback that
returns {"status": "ok", "agent": self.name, "task": task} without doing any
real work. Six security-district classes overrode run() but ignored
task["type"] entirely — always calling the same internal method regardless
of what the governor asked for. These tests assert that run() now branches
on task["type"] and dispatches to the class's real, existing methods.
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.security.alert_manager import AlertManager
from districts.security.detection_rules import DetectionRules
from districts.security.incident_playbook_runner import IncidentPlaybookRunner
from districts.security.log_aggregator import LogAggregator, LogEvent
from districts.security.network_monitor import NetworkMonitor
from districts.security.siem_pipeline import SIEMPipeline


# ---------------------------------------------------------------------------
# AlertManager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_alert_manager_run_list_alerts_routes_to_get_alerts():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        am = AlertManager(db_path=tmp.name)
        result = await am.run({"type": "list_alerts", "params": {"limit": 5}})
        assert result["status"] == "ok"
        assert "alerts" in result
        assert isinstance(result["alerts"], list)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_alert_manager_run_unhandled_type_returns_error_shape():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        am = AlertManager(db_path=tmp.name)
        result = await am.run({"type": "totally_bogus_type"})
        assert result["status"] == "error"
        assert "unhandled type" in result["error"]
        assert "supported" in result
        # Must NOT be the AgentBase stub shape.
        assert "agent" not in result
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_alert_manager_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (core/city/governor.py _dispatch_to_district /
    core/api/routers/commands.py): the governor's classifier invents a task_type per
    request and puts the user's actual free-text message in params["query"]/["content"].
    AlertManager.run() (districts/security/alert_manager.py) has NO query fallback
    after its structured branches — a real "are there any security alerts I should
    know about?" still hits the error stub because the governor's invented task_type
    doesn't exactly match one of {stats, list_alerts, digest, acknowledge, resolve,
    escalate}. LIVE BUG, documented here rather than papered over.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        am = AlertManager(db_path=tmp.name)
        result = await am.run({
            "type": "ask_alert_manager",
            "params": {
                "query": "Are there any security alerts I should know about right now?",
                "content": "Are there any security alerts I should know about right now?",
                "source": "api_command",
            },
        })
        assert result["status"] == "error"
        assert "unhandled type" in result["error"]
        assert "supported" in result
    finally:
        Path(tmp.name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# DetectionRules
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detection_rules_run_match_event_routes_to_evaluate():
    dr = DetectionRules()
    event = {"cpu_percent": 96.0, "source": "system_monitor"}
    result = await dr.run({"type": "match_event", "params": {"event": event}})
    assert result["status"] == "ok"
    assert "matches" in result
    assert isinstance(result["matches"], list)


@pytest.mark.asyncio
async def test_detection_rules_run_unhandled_type_returns_error_shape():
    dr = DetectionRules()
    result = await dr.run({"type": "not_a_real_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_detection_rules_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_alert_manager_run_real_dispatch_shape_with_query
    above for the full explanation). DetectionRules.run() (districts/security/detection_rules.py)
    also has NO query fallback — "what detection rules do you have loaded?" still hits
    the error stub. LIVE BUG, documented here rather than papered over.
    """
    dr = DetectionRules()
    result = await dr.run({
        "type": "ask_detection_rules",
        "params": {
            "query": "What detection rules do you currently have loaded?",
            "content": "What detection rules do you currently have loaded?",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


# ---------------------------------------------------------------------------
# IncidentPlaybookRunner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_incident_playbook_runner_run_list_playbooks_routes_correctly():
    ipr = IncidentPlaybookRunner()
    result = await ipr.run({"type": "list_playbooks"})
    assert result["status"] == "ok"
    assert "playbooks" in result
    assert isinstance(result["playbooks"], list)


@pytest.mark.asyncio
async def test_incident_playbook_runner_run_unhandled_type_returns_error_shape():
    ipr = IncidentPlaybookRunner()
    result = await ipr.run({"type": "nonsense_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_incident_playbook_runner_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_alert_manager_run_real_dispatch_shape_with_query
    above for the full explanation). IncidentPlaybookRunner.run()
    (districts/security/incident_playbook_runner.py) also has NO query fallback —
    "what incident response playbooks are available?" still hits the error stub.
    LIVE BUG, documented here rather than papered over.
    """
    ipr = IncidentPlaybookRunner()
    result = await ipr.run({
        "type": "ask_incident_playbook_runner",
        "params": {
            "query": "What incident response playbooks are available?",
            "content": "What incident response playbooks are available?",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


# ---------------------------------------------------------------------------
# LogAggregator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_aggregator_run_query_routes_to_query_method():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        agg = LogAggregator(db_path=tmp.name)
        agg._store_event(LogEvent(service="test", level="INFO", message="hello"))
        result = await agg.run({"type": "query", "params": {"limit": 10}})
        assert result["status"] == "ok"
        assert "logs" in result
        assert isinstance(result["logs"], list)
        assert len(result["logs"]) == 1
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_log_aggregator_run_unhandled_type_returns_error_shape():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        agg = LogAggregator(db_path=tmp.name)
        result = await agg.run({"type": "garbage_type"})
        assert result["status"] == "error"
        assert "unhandled type" in result["error"]
        assert "supported" in result
        assert "agent" not in result
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_log_aggregator_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_alert_manager_run_real_dispatch_shape_with_query
    above for the full explanation). LogAggregator.run() (districts/security/log_aggregator.py)
    also has NO query fallback — "show me recent error logs" still hits the error stub.
    LIVE BUG, documented here rather than papered over.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        agg = LogAggregator(db_path=tmp.name)
        result = await agg.run({
            "type": "ask_log_aggregator",
            "params": {
                "query": "Show me the recent error logs from the system.",
                "content": "Show me the recent error logs from the system.",
                "source": "api_command",
            },
        })
        assert result["status"] == "error"
        assert "unhandled type" in result["error"]
        assert "supported" in result
    finally:
        Path(tmp.name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# NetworkMonitor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_network_monitor_run_scan_routes_to_scan_connections():
    nm = NetworkMonitor()
    result = await nm.run({"type": "scan"})
    assert result["status"] == "ok"
    assert "connections" in result
    assert isinstance(result["connections"], list)


@pytest.mark.asyncio
async def test_network_monitor_run_unhandled_type_returns_error_shape():
    nm = NetworkMonitor()
    result = await nm.run({"type": "invalid_type_xyz"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_network_monitor_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_alert_manager_run_real_dispatch_shape_with_query
    above for the full explanation). NetworkMonitor.run() (districts/security/network_monitor.py)
    also has NO query fallback — "is my network being scanned right now?" still hits
    the error stub. LIVE BUG, documented here rather than papered over.
    """
    nm = NetworkMonitor()
    result = await nm.run({
        "type": "ask_network_monitor",
        "params": {
            "query": "Is my network being scanned or attacked right now?",
            "content": "Is my network being scanned or attacked right now?",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


# ---------------------------------------------------------------------------
# SIEMPipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_siem_pipeline_run_process_event_routes_to_process_event():
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "logs.db")
    inc_path = str(Path(tmp_dir) / "incidents.db")
    pipeline = SIEMPipeline(db_path=db_path, incidents_db_path=inc_path)
    result = await pipeline.run({
        "type": "process_event",
        "params": {"event": {"source": "test", "level": "WARNING", "message": "wevtutil cl Security"}},
    })
    assert result["status"] == "ok"
    assert "triggered" in result
    assert isinstance(result["triggered"], list)


@pytest.mark.asyncio
async def test_siem_pipeline_run_unhandled_type_returns_error_shape():
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "logs.db")
    inc_path = str(Path(tmp_dir) / "incidents.db")
    pipeline = SIEMPipeline(db_path=db_path, incidents_db_path=inc_path)
    result = await pipeline.run({"type": "made_up_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_siem_pipeline_run_real_dispatch_shape_with_query():
    """Real production dispatch shape (see test_alert_manager_run_real_dispatch_shape_with_query
    above for the full explanation). SIEMPipeline.run() (districts/security/siem_pipeline.py)
    also has NO query fallback — "give me a summary of SIEM activity" still hits the
    error stub. LIVE BUG, documented here rather than papered over.
    """
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "logs.db")
    inc_path = str(Path(tmp_dir) / "incidents.db")
    pipeline = SIEMPipeline(db_path=db_path, incidents_db_path=inc_path)
    result = await pipeline.run({
        "type": "ask_siem_pipeline",
        "params": {
            "query": "Give me a summary of recent SIEM activity and any triggered alerts.",
            "content": "Give me a summary of recent SIEM activity and any triggered alerts.",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
