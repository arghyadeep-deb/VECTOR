
import datetime
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from districts.security.alert_manager import AlertManager, Alert


@dataclass
class FakeRuleMatch:
    rule_name: str
    severity: int
    evidence: dict
    suggested_action: str = ""


@pytest.fixture
def manager(tmp_path):
    db = tmp_path / "test_alerts.db"
    return AlertManager(db_path=str(db))


class TestCreateAlert:
    def test_create_returns_alert(self, manager):
        m = FakeRuleMatch(rule_name="test", severity=5, evidence={})
        a = manager.create_alert(m)
        assert a is not None
        assert a.rule_name == "test"
        assert a.severity == 5
        assert a.status == "NEW"
        assert a.id is not None

    def test_dedup_same_rule_target(self, manager):
        m = FakeRuleMatch(rule_name="dup", severity=5, evidence={"target": "1.2.3.4"})
        a1 = manager.create_alert(m)
        a2 = manager.create_alert(m)
        assert a1 is not None
        assert a2 is None

    def test_dedup_different_target(self, manager):
        m1 = FakeRuleMatch(rule_name="r1", severity=5, evidence={"target": "1.1.1.1"})
        m2 = FakeRuleMatch(rule_name="r1", severity=5, evidence={"target": "2.2.2.2"})
        a1 = manager.create_alert(m1)
        a2 = manager.create_alert(m2)
        assert a1 is not None
        assert a2 is not None


class TestLifecycle:
    def test_acknowledge(self, manager):
        m = FakeRuleMatch(rule_name="t", severity=1, evidence={})
        a = manager.create_alert(m)
        assert manager.acknowledge(a.id)

    def test_resolve(self, manager):
        m = FakeRuleMatch(rule_name="t", severity=1, evidence={})
        a = manager.create_alert(m)
        assert manager.resolve(a.id)

    def test_escalate(self, manager):
        m = FakeRuleMatch(rule_name="t", severity=1, evidence={})
        a = manager.create_alert(m)
        assert manager.escalate(a.id)

    def test_update_nonexistent(self, manager):
        assert not manager.acknowledge("fake-id")

    def test_invalid_status(self, manager):
        m = FakeRuleMatch(rule_name="t", severity=1, evidence={})
        a = manager.create_alert(m)
        assert not manager._update_status(a.id, "INVALID")


class TestPushover:
    @patch("districts.security.alert_manager.httpx.AsyncClient")
    def test_pushover_called_for_high_severity(self, mock_client, manager):
        manager._pushover_token = "tok"
        manager._pushover_user = "user"
        m = FakeRuleMatch(rule_name="critical", severity=9, evidence={"target": "1.2.3.4"})
        a = manager.create_alert(m)
        assert a is not None

    @patch("districts.security.alert_manager.httpx.AsyncClient")
    def test_pushover_skipped_low_severity(self, mock_client, manager):
        manager._pushover_token = "tok"
        manager._pushover_user = "user"
        m = FakeRuleMatch(rule_name="low", severity=3, evidence={})
        a = manager.create_alert(m)
        assert a is not None

    def test_pushover_not_configured(self, manager):
        m = FakeRuleMatch(rule_name="test", severity=9, evidence={})
        a = manager.create_alert(m)
        assert a is not None


class TestQuery:
    def test_get_alerts_empty(self, manager):
        assert manager.get_alerts() == []

    def test_get_alerts_by_status(self, manager):
        m = FakeRuleMatch(rule_name="t", severity=1, evidence={})
        a = manager.create_alert(m)
        results = manager.get_alerts(status="NEW")
        assert len(results) >= 1

    def test_get_alerts_by_severity(self, manager):
        m = FakeRuleMatch(rule_name="t", severity=8, evidence={})
        manager.create_alert(m)
        results = manager.get_alerts(severity_ge=7)
        assert len(results) >= 1

    def test_get_alerts_below_severity(self, manager):
        m = FakeRuleMatch(rule_name="t", severity=3, evidence={})
        manager.create_alert(m)
        results = manager.get_alerts(severity_ge=7)
        assert len(results) == 0


class TestStats:
    def test_get_stats_empty(self, manager):
        stats = manager.get_stats()
        assert stats["total"] == 0

    def test_get_stats_with_data(self, manager):
        manager.create_alert(FakeRuleMatch(rule_name="r1", severity=5, evidence={}))
        manager.create_alert(FakeRuleMatch(rule_name="r2", severity=8, evidence={}))
        stats = manager.get_stats()
        assert stats["total"] >= 2


class TestDigest:
    def test_get_digest_empty(self, manager):
        digest = manager.get_digest(hours=24)
        assert digest["total_alerts"] == 0

    def test_get_digest_with_data(self, manager):
        manager.create_alert(FakeRuleMatch(rule_name="r1", severity=5, evidence={}))
        digest = manager.get_digest(hours=24)
        assert digest["total_alerts"] >= 1
