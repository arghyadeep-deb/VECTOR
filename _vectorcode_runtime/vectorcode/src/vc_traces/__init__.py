# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Trace system — full interaction-level recording and analysis.

The trace system captures the complete sequence of steps an agent takes to
handle a query.  Unlike telemetry (which records per-inference metrics), traces
record the *decision-making process*: which model was selected, what memory was
retrieved, which tools were called, and the final response.

Traces are the primary input to the learning system.
"""

from vectorcode.src.vc_traces.analyzer import TraceAnalyzer
from vectorcode.src.vc_traces.collector import TraceCollector
from vectorcode.src.vc_traces.store import TraceStore

__all__ = ["TraceAnalyzer", "TraceCollector", "TraceStore"]
