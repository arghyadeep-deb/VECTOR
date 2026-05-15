# VECTOR module -- ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb

"""GPU capability detection + Docker container launcher utilities.

Pulled from VectorCode's Pearl mining subsystem for the reusable parts:
hardware capability detection and GPU Docker orchestration. The actual
Pearl mining loop (network-connected distributed compute) is excluded --
this layer is purely for local GPU utility.
"""

from core.mining.stubs import MiningCapabilities
from core.mining.discovery import detect_for_engine_model, check_docker_available
from core.mining.docker import PearlDockerLauncher

__all__ = [
    "MiningCapabilities",
    "detect_for_engine_model",
    "check_docker_available",
    "PearlDockerLauncher",
]
