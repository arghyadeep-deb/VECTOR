# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Operators — persistent, scheduled autonomous agents."""

from vectorcode.src.operators.loader import load_operator
from vectorcode.src.operators.manager import OperatorManager
from vectorcode.src.operators.types import OperatorManifest

__all__ = ["OperatorManifest", "OperatorManager", "load_operator"]
