# VECTOR module -- ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb

"""GPU capability detection utilities.

Pulled from VectorCode's Pearl mining subsystem for the reusable parts:
hardware capability detection. The Docker orchestration and distributed
Pearl mining loop are excluded — VECTOR runs fully local.
"""

# 2026-09-24 (external review, Phase 1): core.mining.stubs never existed --
# MiningCapabilities actually lives in core.mining._abc.
from core.mining._abc import MiningCapabilities
from core.mining.discovery import detect_for_engine_model, check_docker_available

__all__ = [
    "MiningCapabilities",
    "detect_for_engine_model",
    "check_docker_available",
]
