# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Wire the existing HeuristicRouter into the RouterPolicyRegistry."""

from __future__ import annotations

from vectorcode.src.vc_core.registry import RouterPolicyRegistry
from vectorcode.src.learning.routing.router import HeuristicRouter

def ensure_registered() -> None:
    """Register HeuristicRouter if not already present."""
    if not RouterPolicyRegistry.contains("heuristic"):
        RouterPolicyRegistry.register_value("heuristic", HeuristicRouter)

ensure_registered()
