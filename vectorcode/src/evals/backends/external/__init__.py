# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/evals/backends/external/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""External-framework subprocess backends (Hermes Agent, OpenClaw)."""

from vectorcode.src.evals.backends.external.hermes_agent import HermesBackend
from vectorcode.src.evals.backends.external.openclaw import OpenClawBackend

__all__ = ["HermesBackend", "OpenClawBackend"]
