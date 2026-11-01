# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Workflow engine — DAG-based multi-agent pipelines."""

from vectorcode.src.workflow.builder import WorkflowBuilder
from vectorcode.src.workflow.engine import WorkflowEngine
from vectorcode.src.workflow.graph import WorkflowGraph
from vectorcode.src.workflow.loader import load_workflow
from vectorcode.src.workflow.types import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowResult,
    WorkflowStepResult,
)

__all__ = [
    "WorkflowBuilder",
    "WorkflowEdge",
    "WorkflowEngine",
    "WorkflowGraph",
    "WorkflowNode",
    "WorkflowResult",
    "WorkflowStepResult",
    "load_workflow",
]
