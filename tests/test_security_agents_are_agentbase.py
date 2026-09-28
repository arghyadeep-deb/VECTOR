"""Regression: the 6 security SIEM-stack classes (alert_manager,
detection_rules, incident_playbook_runner, log_aggregator, network_monitor,
siem_pipeline) had a run() that branches on task["type"] (fixed separately)
but none of them subclassed core.city.agent_base.AgentBase — they're plain
classes. ManifestLoader.register_all() -> AgentRegistry.register(agent)
unconditionally reads agent.id, which only AgentBase instances have,
so registering any of them crashed with AttributeError before this fix.
"""
# ruff: noqa: E402

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.city.agent_base import AgentBase
from districts.security.alert_manager import AlertManager
from districts.security.detection_rules import DetectionRules
from districts.security.incident_playbook_runner import IncidentPlaybookRunner
from districts.security.log_aggregator import LogAggregator
from districts.security.network_monitor import NetworkMonitor
from districts.security.siem_pipeline import SIEMPipeline


def test_alert_manager_is_agentbase(tmp_path):
    agent = AlertManager(db_path=str(tmp_path / "a.db"))
    assert isinstance(agent, AgentBase)
    assert agent.id
    assert agent.district == "security"


def test_detection_rules_is_agentbase():
    agent = DetectionRules()
    assert isinstance(agent, AgentBase)
    assert agent.id
    assert agent.district == "security"


def test_incident_playbook_runner_is_agentbase(tmp_path):
    agent = IncidentPlaybookRunner(db_path=str(tmp_path / "i.db"))
    assert isinstance(agent, AgentBase)
    assert agent.id
    assert agent.district == "security"


def test_log_aggregator_is_agentbase(tmp_path):
    agent = LogAggregator(db_path=str(tmp_path / "l.db"))
    assert isinstance(agent, AgentBase)
    assert agent.id
    assert agent.district == "security"


def test_network_monitor_is_agentbase():
    agent = NetworkMonitor()
    assert isinstance(agent, AgentBase)
    assert agent.id
    assert agent.district == "security"


def test_siem_pipeline_is_agentbase(tmp_path):
    agent = SIEMPipeline(db_path=str(tmp_path / "s.db"))
    assert isinstance(agent, AgentBase)
    assert agent.id
    assert agent.district == "security"


def test_full_manifest_instantiates_without_attribute_error():
    """End-to-end: this is the exact call that crashed before the fix."""
    from core.city.agent_registry import get_registry
    from core.city.declarative_manifest import ManifestLoader

    reg = get_registry()
    before = set(reg._agents.keys())
    try:
        loader = ManifestLoader()
        defs = loader.load()
        sec_defs = [d for d in defs if d["district"] == "security"]
        expected_specialists = {
            "patch_proposal_generator",
            "patch_proposal_verifier",
            "scan_inventory_analyst",
            "scan_loader_analyst",
            "scan_researcher",
            "scan_verifier",
            "agentic_identity_trust_analyst",
            "automation_governance_analyst",
        }
        assert len(sec_defs) == 20  # 12 established + 8 deterministic specialists
        assert expected_specialists <= {definition["name"] for definition in sec_defs}
        registered = loader.register_all(sec_defs, reg)
        assert registered == 20
    finally:
        for aid in list(reg._agents.keys()):
            if aid not in before:
                reg._agents.pop(aid, None)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
