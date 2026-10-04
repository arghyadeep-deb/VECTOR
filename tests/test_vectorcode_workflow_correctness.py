"""Regression tests for VectorCode workflow result integrity."""

from vectorcode.src.workflow.engine import WorkflowEngine
from vectorcode.src.workflow.graph import WorkflowGraph
from vectorcode.src.workflow.types import NodeType, WorkflowEdge, WorkflowNode


class _ErrorSystem:
    tool_executor = None

    def ask(self, _text, **_kwargs):
        return {"content": "Unknown agent: missing", "error": True}


def _single_node_graph(node: WorkflowNode) -> WorkflowGraph:
    graph = WorkflowGraph("regression")
    graph.add_node(node)
    return graph


def test_agent_error_result_fails_workflow() -> None:
    graph = _single_node_graph(WorkflowNode("agent", NodeType.AGENT))

    result = WorkflowEngine().run(graph, _ErrorSystem())

    assert result.success is False
    assert result.steps[0].success is False


def test_loop_without_system_fails_instead_of_reporting_success() -> None:
    graph = _single_node_graph(WorkflowNode("loop", NodeType.LOOP))

    result = WorkflowEngine().run(graph, system=None)

    assert result.success is False
    assert result.steps[0].success is False


def test_invalid_condition_expression_fails_workflow() -> None:
    graph = _single_node_graph(
        WorkflowNode("condition", NodeType.CONDITION, condition_expr="unknown_name")
    )

    result = WorkflowEngine().run(graph)

    assert result.success is False
    assert "Invalid condition expression" in result.final_output


def test_transform_uses_only_its_predecessor_outputs() -> None:
    graph = WorkflowGraph("branches")
    graph.add_node(WorkflowNode("wanted", NodeType.CONDITION))
    graph.add_node(WorkflowNode("unrelated", NodeType.CONDITION))
    graph.add_node(WorkflowNode("merge", NodeType.TRANSFORM, transform_expr="concatenate"))
    graph.add_edge(WorkflowEdge("wanted", "merge"))

    step = WorkflowEngine()._run_transform_node(
        graph.get_node("merge"),
        {"_input": "input", "wanted": "keep", "unrelated": "drop"},
        graph,
    )

    assert step.output == "keep"
