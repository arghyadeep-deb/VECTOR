# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""External-framework subprocess backends (VECTOR, OpenClaw)."""

from vectorcode.src.evals.backends.external.vector_agent import VectorAgentBackend
from vectorcode.src.evals.backends.external.openclaw import OpenClawBackend

__all__ = ["VectorAgentBackend", "OpenClawBackend"]
