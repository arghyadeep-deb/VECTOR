"""Regression: the 6 security SIEM-stack classes (alert_manager,
detection_rules, incident_playbook_runner, log_aggregator, network_monitor,
siem_pipeline) had a run() that branches on task["type"] (fixed separately)
but none of them subclassed core.city.agent_base.AgentBase — they're plain
classes. ManifestLoader.register_all() -> AgentRegistry.register(agent)
unconditionally reads agent.id, which only AgentBase instances have,
so registering any of them crashed with AttributeError before this fix.
"""
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
    from core.city.declarative_manifest import ManifestLoader
    from core.city.agent_registry import get_registry

    reg = get_registry()
    before = set(reg._agents.keys())
    try:
        loader = ManifestLoader()
        defs = loader.load()
        sec_defs = [d for d in defs if d["district"] == "security"]
        assert len(sec_defs) == 11  # 5 pre-existing + 6 new
        registered = loader.register_all(sec_defs, reg)
        assert registered == 11
    finally:
        for aid in list(reg._agents.keys()):
            if aid not in before:
                reg._agents.pop(aid, None)
