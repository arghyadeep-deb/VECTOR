"""
Module: agents/districts/security/__init__.py
V.E.C.T.O.R. Security District - Security and threat detection agents
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger

from .node_guard import NodeGuard
from .threat_scout import ThreatScout
from .malware_hunter import MalwareHunter

__all__ = [
    "NodeGuard",
    "ThreatScout",
    "MalwareHunter",
]

logger.info("[VECTOR][security] Security district loaded")


def get_agent(name: str):
    """Factory function to get security district agents."""
    agents = {
        "NodeGuard": NodeGuard,
        "ThreatScout": ThreatScout,
        "MalwareHunter": MalwareHunter,
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
