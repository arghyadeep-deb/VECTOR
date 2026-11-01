"""
Module: agents/security/__init__.py
V.E.C.T.O.R. Security District - Security and threat detection agents
"""

import sys

from loguru import logger

from .node_guard import NodeGuard
from .threat_scout import ThreatScout
from .malware_hunter import MalwareHunter
from .network_monitor import NetworkMonitor, BlocklistEntry
from .log_aggregator import LogAggregator, LogEvent
from .detection_rules import DetectionRules, DetectionRule, RuleMatch
from .alert_manager import AlertManager, Alert
from .incident_playbook_runner import IncidentPlaybookRunner, Incident, PlaybookStep
from .skill_spector import SkillSpector

__all__ = [
    "NodeGuard",
    "ThreatScout",
    "MalwareHunter",
    "NetworkMonitor",
    "BlocklistEntry",
    "LogAggregator",
    "LogEvent",
    "DetectionRules",
    "DetectionRule",
    "RuleMatch",
    "AlertManager",
    "Alert",
    "IncidentPlaybookRunner",
    "Incident",
    "PlaybookStep",
    "SkillSpector",
]

logger.info("[VECTOR][security] Security district loaded")


def get_agent(name: str):
    """Factory function to get security district agents."""
    agents = {
        "NodeGuard": NodeGuard,
        "ThreatScout": ThreatScout,
        "MalwareHunter": MalwareHunter,
        "NetworkMonitor": NetworkMonitor,
        "LogAggregator": LogAggregator,
        "DetectionRules": DetectionRules,
        "AlertManager": AlertManager,
        "IncidentPlaybookRunner": IncidentPlaybookRunner,
        "SkillSpector": SkillSpector,
    }
    return agents.get(name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    try:
        from .node_guard import NodeGuard
        guard = NodeGuard()
        print(f"NodeGuard: {guard.name}")
    except Exception as e:
        print(f"NodeGuard: {e}")

    try:
        from .threat_scout import ThreatScout
        scout = ThreatScout()
        print(f"ThreatScout: {scout.name}")
    except Exception as e:
        print(f"ThreatScout: {e}")

    hunter = MalwareHunter()
    print(f"MalwareHunter: {hunter.name}")

    print("✅ security/__init__.py OK")
