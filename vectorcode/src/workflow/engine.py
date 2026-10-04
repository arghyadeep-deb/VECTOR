# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""WorkflowEngine — executes a WorkflowGraph against a VectorSystem."""

from __future__ import annotations

import ast
import concurrent.futures
import operator
import time
from typing import Any, Dict, List, Optional


# ── Restricted condition evaluator ──────────────────────────────────────────
# Replaces eval() — even eval(expr, {"__builtins__": {}}) is escapable via
# ().__class__.__bases__[0].__subclasses__()... and would be RCE if a workflow's
# condition_expr were ever attacker-influenced. This AST walker permits only the
# node types a condition legitimately needs (dict access, comparisons, boolean
# logic, membership, constants) and rejects everything else (calls, attribute
# access, names other than `outputs`).
_SAFE_CMP_OPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
}


def _safe_eval_condition(expr: str, outputs: Dict[str, str]) -> bool:
    """Evaluate a workflow condition expression without eval(). Returns bool."""
    def _ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "outputs":
                return outputs
            raise ValueError(f"name not allowed: {node.id}")
        if isinstance(node, ast.Subscript):
            return _ev(node.value)[_ev(node.slice)]
        if isinstance(node, ast.BoolOp):
            vals = [_ev(v) for v in node.values]
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not _ev(node.operand)
        if isinstance(node, ast.Compare):
            left = _ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                fn = _SAFE_CMP_OPS.get(type(op))
                if fn is None:
                    raise ValueError(f"operator not allowed: {type(op).__name__}")
                right = _ev(comp)
                if not fn(left, right):
                    return False
                left = right
            return True
        raise ValueError(f"node not allowed: {type(node).__name__}")

    tree = ast.parse(expr, mode="eval")
    return bool(_ev(tree))
# ────────────────────────────────────────────────────────────────────────────

from vectorcode.src.vc_core.events import EventBus, EventType
from vectorcode.src.workflow.graph import WorkflowGraph
from vectorcode.src.workflow.types import (
    NodeType,
    WorkflowNode,
    WorkflowResult,
    WorkflowStepResult,
)

class WorkflowEngine:
    """Execute DAG-based workflows.

    Sequential nodes run in topological order. Parallel-eligible nodes
    (same execution stage, no inter-dependencies) run via ThreadPoolExecutor.
    Condition nodes evaluate expressions against prior step outputs.
    Loop nodes use LoopGuard from Phase 14.3.
    """

    def __init__(
        self,
        *,
        bus: Optional[EventBus] = None,
        max_parallel: int = 4,
        default_node_timeout: int = 300,
    ) -> None:
        self._bus = bus
        self._max_parallel = max_parallel
        self._default_node_timeout = default_node_timeout

    def run(
        self,
        graph: WorkflowGraph,
        system: Any = None,  # VectorSystem
        *,
        initial_input: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowResult:
        """Execute a workflow graph end-to-end."""
        valid, msg = graph.validate()
        if not valid:
            return WorkflowResult(
                workflow_name=graph.name,
                success=False,
                final_output=f"Invalid workflow: {msg}",
            )

        t0 = time.time()
        if self._bus:
            self._bus.publish(
                EventType.WORKFLOW_START,
                {"workflow": graph.name},
            )

        # State: outputs keyed by node_id
        outputs: Dict[str, str] = {"_input": initial_input}
        ctx = dict(context or {})
        all_steps: List[WorkflowStepResult] = []
        success = True

        stages = graph.execution_stages()
        for stage in stages:
            if len(stage) == 1:
                # Sequential execution
                step = self._execute_node(
                    graph.get_node(stage[0]),  # type: ignore[arg-type]
                    outputs,
                    ctx,
                    system,
                    graph,
                )
                all_steps.append(step)
                outputs[stage[0]] = step.output
                if not step.success:
                    success = False
                    break
            else:
                # Parallel execution
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(len(stage), self._max_parallel),
                ) as pool:
                    futures = {
                        pool.submit(
                            self._execute_node,
                            graph.get_node(nid),
                            dict(outputs),
                            dict(ctx),
                            system,
                            graph,
                        ): nid
                        for nid in stage
                    }
                    for future in concurrent.futures.as_completed(futures):
                        nid = futures[future]
                        try:
                            step = future.result(
                                timeout=self._default_node_timeout,
                            )
                        except Exception as exc:
                            step = WorkflowStepResult(
                                node_id=nid,
                                success=False,
                                output=f"Node execution error: {exc}",
                            )
                        all_steps.append(step)
                        outputs[nid] = step.output
                        if not step.success:
                            success = False

            if not success:
                break

        total = time.time() - t0
        # Final output is the output of the last executed node
        final_output = all_steps[-1].output if all_steps else ""

        if self._bus:
            self._bus.publish(
                EventType.WORKFLOW_END,
                {"workflow": graph.name, "success": success, "duration": total},
            )

        return WorkflowResult(
            workflow_name=graph.name,
            success=success,
            steps=all_steps,
            final_output=final_output,
            total_duration_seconds=total,
        )

    def _execute_node(
        self,
        node: WorkflowNode,
        outputs: Dict[str, str],
        ctx: Dict[str, Any],
        system: Any,
        graph: WorkflowGraph,
    ) -> WorkflowStepResult:
        """Execute a single workflow node."""
        if self._bus:
            self._bus.publish(
                EventType.WORKFLOW_NODE_START,
                {"node": node.id, "type": node.node_type.value},
            )

        t0 = time.time()
        try:
            if node.node_type == NodeType.AGENT:
                result = self._run_agent_node(node, outputs, system, graph)
            elif node.node_type == NodeType.TOOL:
                result = self._run_tool_node(node, outputs, system)
            elif node.node_type == NodeType.CONDITION:
                result = self._run_condition_node(node, outputs)
            elif node.node_type == NodeType.TRANSFORM:
                result = self._run_transform_node(node, outputs, graph)
            elif node.node_type == NodeType.LOOP:
                result = self._run_loop_node(node, outputs, system, graph)
            else:
                result = WorkflowStepResult(
                    node_id=node.id,
                    success=False,
                    output=f"Unknown node type: {node.node_type}",
                )
        except Exception as exc:
            result = WorkflowStepResult(
                node_id=node.id,
                success=False,
                output=f"Node error: {exc}",
            )

        result.duration_seconds = time.time() - t0

        if self._bus:
            self._bus.publish(
                EventType.WORKFLOW_NODE_END,
                {
                    "node": node.id,
                    "success": result.success,
                    "duration": result.duration_seconds,
                },
            )

        return result

    def _get_node_input(
        self,
        node: WorkflowNode,
        outputs: Dict[str, str],
        graph: WorkflowGraph,
    ) -> str:
        """Get input for a node from predecessor outputs."""
        preds = graph.predecessors(node.id)
        if preds:
            parts = [outputs.get(p, "") for p in preds if outputs.get(p)]
            return "\n\n".join(parts) if parts else outputs.get("_input", "")
        return outputs.get("_input", "")

    def _run_agent_node(
        self,
        node: WorkflowNode,
        outputs: Dict[str, str],
        system: Any,
        graph: WorkflowGraph,
    ) -> WorkflowStepResult:
        """Execute an agent node."""
        input_text = self._get_node_input(node, outputs, graph)
        if system is None:
            return WorkflowStepResult(
                node_id=node.id,
                success=False,
                output="No system available for agent execution.",
            )
        try:
            result = system.ask(
                input_text,
                agent=node.agent or None,
                tools=node.tools or None,
            )
            if result.get("error"):
                return WorkflowStepResult(
                    node_id=node.id,
                    success=False,
                    output=result.get("content", "Agent execution failed."),
                )
            return WorkflowStepResult(
                node_id=node.id,
                success=True,
                output=result.get("content", ""),
            )
        except Exception as exc:
            return WorkflowStepResult(
                node_id=node.id,
                success=False,
                output=f"Agent error: {exc}",
            )

    def _run_tool_node(
        self,
        node: WorkflowNode,
        outputs: Dict[str, str],
        system: Any,
    ) -> WorkflowStepResult:
        """Execute a tool node."""
        tool_name = node.config.get("tool_name", "")
        tool_args = node.config.get("tool_args", "{}")
        if system and system.tool_executor:
            from vectorcode.src.vc_core.types import ToolCall

            tc = ToolCall(id=f"wf_{node.id}", name=tool_name, arguments=tool_args)
            tr = system.tool_executor.execute(tc)
            return WorkflowStepResult(
                node_id=node.id,
                success=tr.success,
                output=tr.content,
            )
        return WorkflowStepResult(
            node_id=node.id,
            success=False,
            output="No tool executor available.",
        )

    def _run_condition_node(
        self,
        node: WorkflowNode,
        outputs: Dict[str, str],
    ) -> WorkflowStepResult:
        """Evaluate a condition expression against outputs."""
        expr = node.condition_expr
        if not expr:
            return WorkflowStepResult(
                node_id=node.id,
                success=True,
                output="true",
            )
        # Safe expression evaluation — restricted AST walker, never eval().
        # Supports dict access, comparisons, boolean logic, membership.
        try:
            result = str(_safe_eval_condition(expr, outputs))
            return WorkflowStepResult(
                node_id=node.id,
                success=True,
                output=result,
            )
        except Exception as exc:
            return WorkflowStepResult(
                node_id=node.id,
                success=False,
                output=f"Invalid condition expression: {exc}",
            )

    def _run_transform_node(
        self,
        node: WorkflowNode,
        outputs: Dict[str, str],
        graph: WorkflowGraph,
    ) -> WorkflowStepResult:
        """Apply a text transformation."""
        expr = node.transform_expr
        preds = [outputs.get(p, "") for p in graph.predecessors(node.id)]
        combined = "\n\n".join(preds) if preds else ""
        if expr == "concatenate":
            return WorkflowStepResult(node_id=node.id, output=combined)
        if expr == "first_line":
            return WorkflowStepResult(
                node_id=node.id,
                output=combined.split("\n")[0] if combined else "",
            )
        return WorkflowStepResult(node_id=node.id, output=combined)

    def _run_loop_node(
        self,
        node: WorkflowNode,
        outputs: Dict[str, str],
        system: Any,
        graph: WorkflowGraph,
    ) -> WorkflowStepResult:
        """Execute a loop node (re-runs agent until condition or max iterations)."""
        input_text = self._get_node_input(node, outputs, graph)
        max_iter = node.max_iterations
        if system is None:
            return WorkflowStepResult(
                node_id=node.id,
                success=False,
                output="No system available for loop execution.",
            )
        if max_iter <= 0:
            return WorkflowStepResult(
                node_id=node.id,
                success=False,
                output="Loop max_iterations must be greater than zero.",
            )
        last_output = input_text
        for i in range(max_iter):
            result = system.ask(last_output, agent=node.agent or None)
            if result.get("error"):
                return WorkflowStepResult(
                    node_id=node.id,
                    success=False,
                    output=result.get("content", "Loop agent execution failed."),
                    metadata={"iterations": i + 1},
                )
            last_output = result.get("content", "")
            # Check if loop should terminate
            if (
                node.condition_expr
                and node.condition_expr.lower() in last_output.lower()
            ):
                break
        return WorkflowStepResult(
            node_id=node.id,
            success=True,
            output=last_output,
            metadata={"iterations": i + 1},
        )

__all__ = ["WorkflowEngine"]
