"""Regression tests for the Phase 3 investment/security deep audit."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from loguru import logger

from districts.investment.sentiment_bot import SentimentBot
from districts.security.alert_manager import AlertManager
from districts.security.incident_playbook_runner import IncidentPlaybookRunner
from districts.security.log_aggregator import LogAggregator
from districts.security.node_guard import NodeGuard
from districts.security.threat_scout import ThreatScout


class _RuleMatch:
    rule_name = "persistence-test"
    severity = 9
    evidence = {"target": "host-1"}
    suggested_action = "investigate"


def test_newsapi_key_is_sent_in_header_not_query(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            return SimpleNamespace(status_code=200, json=lambda: {"articles": []})

    monkeypatch.setattr("httpx.Client", FakeClient)
    bot = SentimentBot()
    bot._newsapi_key = "secret-news-key"
    bot._fetch_real_news_sentiment("VECTOR")

    assert captured["headers"] == {"X-Api-Key": "secret-news-key"}
    assert "apiKey" not in captured["params"]
    assert "secret-news-key" not in captured["url"]


def test_alert_persistence_failure_is_not_reported_or_deduplicated(tmp_path, monkeypatch):
    manager = AlertManager(db_path=str(tmp_path / "alerts.db"))
    monkeypatch.setattr(manager, "_store_alert", lambda alert: False)

    assert manager.create_alert(_RuleMatch()) is None
    assert manager._dedup_cache == {}


def test_log_sink_failure_keeps_exception_traceback(tmp_path):
    messages = []
    sink_id = logger.add(messages.append, format="{message}\n{exception}")
    try:
        aggregator = LogAggregator(db_path=str(tmp_path / "logs.db"))
        aggregator.make_sink()(object())
    finally:
        logger.remove(sink_id)

    rendered = "".join(str(message) for message in messages)
    assert "sink rejected log event" in rendered
    assert "AttributeError" in rendered


@pytest.mark.asyncio
async def test_node_guard_does_not_reward_failed_connection_scan(monkeypatch):
    guard = NodeGuard()
    starting_hp = guard.health_points

    def fail_scan():
        guard._connection_scan_ok = False
        return []

    monkeypatch.setattr(guard, "get_active_connections", fail_scan)
    monkeypatch.setattr(guard, "get_network_stats", lambda: {})
    result = await guard.monitor_tick()

    assert result["scan_status"] == "error"
    assert guard.health_points < starting_hp


@pytest.mark.asyncio
async def test_threat_scout_process_scan_failure_is_unknown_not_low(monkeypatch):
    scout = ThreatScout()

    def scanner_offline():
        raise RuntimeError("scanner offline")

    monkeypatch.setattr(
        "districts.security.threat_scout.check_process_anomalies", scanner_offline
    )
    monkeypatch.setattr(scout, "scan_startup_entries", lambda: [])
    result = await scout.run_threat_assessment()

    assert result["threat_level"] == "unknown"
    assert any("failed" in alert.lower() for alert in result["alerts"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "params"),
    [
        ("_action_block_ip", {"ip": "203.0.113.7"}),
        ("_action_unblock_ip", {"ip": "203.0.113.7"}),
        ("_action_kill_process", {"pid": 424242}),
    ],
)
async def test_incident_actions_fail_closed_on_command_failure(
    tmp_path, monkeypatch, handler, params
):
    runner = IncidentPlaybookRunner(
        playbooks_dir=str(tmp_path / "playbooks"),
        db_path=str(tmp_path / "incidents.db"),
    )

    async def approve(*args, **kwargs):
        return None

    async def run_in_thread(func, *args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="command denied")

    monkeypatch.setattr(runner, "_gate_destructive_action", approve)
    monkeypatch.setattr(asyncio, "to_thread", run_in_thread)

    result = await getattr(runner, handler)(params, {}, "incident-1")
    assert result == {"status": "error", "message": "command denied"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
