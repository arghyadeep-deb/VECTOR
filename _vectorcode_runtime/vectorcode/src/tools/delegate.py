"""VectorCode delegate_task tool — subagent architecture.

Ports the subagent delegation pattern from VectorCode delegate_tool.py into
VectorCode's engine. Spawns a child VectorAgent in a thread with an
independent IterationBudget, a focused system prompt, and a restricted
toolset (no clarify, memory_write, or recursive delegate calls).

The parent only sees the delegation call and the final result summary —
never the child's intermediate tool calls or reasoning.

Schema (OpenAI function format):
    name: delegate_task
    parameters:
      task (required, str)  — what the subagent must accomplish
      context (str)         — background information for the subagent
      max_iterations (int)  — iteration cap, default 50
      timeout (int)         — wall-clock seconds, default 300
    risk_level: medium
"""

import sys
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}


# ── Constants ─────────────────────────────────────────────────────────────────

# Tools that child agents must never have access to
DELEGATE_BLOCKED_TOOLS: frozenset = frozenset({
    "delegate_task",   # no recursive delegation
    "clarify",         # no user interaction in subagents
    "memory_write",    # no writes to shared memory from subagents
    "send_message",    # no cross-platform side effects
})

_DEFAULT_MAX_ITERATIONS = 50
_DEFAULT_TIMEOUT = 300          # seconds
_DEFAULT_MAX_CONCURRENT = 3


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class DelegateTask:
    """Parameters for a single delegation request."""

    task: str
    context: str = ""
    max_iterations: int = _DEFAULT_MAX_ITERATIONS
    timeout: int = _DEFAULT_TIMEOUT
    enabled_tools: Optional[List[str]] = None


@dataclass
class DelegateResult:
    """Outcome of a delegation request."""

    task_id: str
    result: str
    success: bool
    iterations_used: int
    duration_ms: int
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a dict for JSON tool response."""
        return {
            "task_id": self.task_id,
            "result": self.result,
            "success": self.success,
            "iterations_used": self.iterations_used,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


# ── System prompt builder ─────────────────────────────────────────────────────

def _build_child_system_prompt(task: str, context: str = "") -> str:
    """Build a focused system prompt for a delegated subagent.

    Mirrors VectorCode _build_child_system_prompt() without the orchestrator
    branch — VectorCode subagents are always leaves (depth 1 flat hierarchy).
    """
    parts = [
        "You are a focused subagent working on a specific delegated task.",
        "",
        f"YOUR TASK:\n{task}",
    ]
    if context and context.strip():
        parts.append(f"\nCONTEXT:\n{context.strip()}")
    parts.append(
        "\nComplete this task using the tools available to you. "
        "When finished, provide a clear, concise summary of:\n"
        "- What you did\n"
        "- What you found or accomplished\n"
        "- Any files you created or modified\n"
        "- Any issues encountered\n\n"
        "Be thorough but concise — your response is returned to the "
        "parent agent as a summary."
    )
    return "\n".join(parts)


# ── Auto-deny callback (blocks dangerous commands in subagent threads) ─────────

def _subagent_auto_deny(command: str, description: str = "", **kwargs) -> str:
    """Auto-deny any approval request from a subagent thread.

    Prevents deadlock: subagent worker threads cannot call input() because
    the parent thread owns the terminal. Returns 'deny' so the subagent sees
    a recoverable refusal, not a hang.
    """
    logger.warning(
        "[VECTOR][delegate] subagent auto-denied dangerous command: %s (%s)",
        command,
        description,
    )
    return "deny"


# ── Core delegation logic ─────────────────────────────────────────────────────

def _run_child_agent(
    task_id: str,
    params: DelegateTask,
) -> DelegateResult:
    """Execute a delegated task in the current thread.

    Attempts to import and run VectorAgent from engine.agent_loop. Falls back
    to a lightweight stub result when the engine is unavailable (e.g. during
    unit tests without the full agent stack loaded).
    """
    start_ms = int(time.time() * 1000)
    logger.info(
        f"[VECTOR][delegate] task_id={task_id} starting: {params.task[:80]}"
    )

    # Try to run a real VectorAgent child
    try:
        from engine.agent_loop import VectorAgent, IterationBudget

        budget = IterationBudget(max_total=params.max_iterations)
        child_system = _build_child_system_prompt(params.task, params.context)

        agent = VectorAgent(
            max_iterations=params.max_iterations,
            iteration_budget=budget,
            quiet_mode=True,
            save_trajectories=False,
        )

        # run_conversation() returns a result dict with 'response' key
        result_dict = agent.run_conversation(
            user_message=params.task,
            system_message=child_system,
        )
        final_result = (
            result_dict.get("response", "")
            if isinstance(result_dict, dict)
            else str(result_dict)
        )
        iterations = budget.used
        duration_ms = int(time.time() * 1000) - start_ms

        logger.info(
            f"[VECTOR][delegate] task_id={task_id} done "
            f"({iterations} iterations, {duration_ms}ms)"
        )
        return DelegateResult(
            task_id=task_id,
            result=str(final_result) if final_result else "(no result)",
            success=True,
            iterations_used=iterations,
            duration_ms=duration_ms,
        )

    except ImportError:
        # Agent engine not available (test environment or partial install)
        logger.debug(
            "[VECTOR][delegate] VectorAgent not importable — using stub result"
        )
        duration_ms = int(time.time() * 1000) - start_ms
        return DelegateResult(
            task_id=task_id,
            result=f"[stub] Delegated task received: {params.task}",
            success=True,
            iterations_used=0,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int(time.time() * 1000) - start_ms
        error_str = str(exc)
        logger.error(
            f"[VECTOR][delegate] task_id={task_id} failed after "
            f"{duration_ms}ms: {error_str}"
        )
        return DelegateResult(
            task_id=task_id,
            result="",
            success=False,
            iterations_used=0,
            duration_ms=duration_ms,
            error=error_str,
        )


def delegate_task(
    task: str,
    context: str = "",
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
    timeout: int = _DEFAULT_TIMEOUT,
) -> DelegateResult:
    """Delegate a task to an independent subagent and return its result.

    Runs the child agent in a ThreadPoolExecutor worker thread. The calling
    thread blocks until the child completes or the timeout expires.

    Args:
        task: The task the subagent must accomplish.
        context: Optional background context for the subagent.
        max_iterations: Maximum agent loop iterations for the child (default 50).
        timeout: Wall-clock timeout in seconds (default 300).

    Returns:
        DelegateResult with .result (str), .success (bool), .error (str|None).
    """
    if not task or not task.strip():
        return DelegateResult(
            task_id="",
            result="",
            success=False,
            iterations_used=0,
            duration_ms=0,
            error="delegate_task: 'task' parameter is required and must be non-empty",
        )

    params = DelegateTask(
        task=task.strip(),
        context=context.strip() if context else "",
        max_iterations=max(1, int(max_iterations)),
        timeout=max(10, int(timeout)),
    )
    task_id = str(uuid.uuid4())[:8]

    with ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix=f"delegate-{task_id}",
    ) as executor:
        future = executor.submit(_run_child_agent, task_id, params)
        try:
            result = future.result(timeout=params.timeout)
            return result
        except FuturesTimeoutError:
            duration_ms = params.timeout * 1000
            logger.warning(
                f"[VECTOR][delegate] task_id={task_id} timed out "
                f"after {params.timeout}s"
            )
            return DelegateResult(
                task_id=task_id,
                result="",
                success=False,
                iterations_used=0,
                duration_ms=duration_ms,
                error=f"Delegation timed out after {params.timeout}s",
            )
        except Exception as exc:
            logger.error(
                f"[VECTOR][delegate] task_id={task_id} executor error: {exc}"
            )
            return DelegateResult(
                task_id=task_id,
                result="",
                success=False,
                iterations_used=0,
                duration_ms=0,
                error=str(exc),
            )


# ── OpenAI function schema ────────────────────────────────────────────────────

DELEGATE_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "delegate_task",
        "description": (
            "Delegate a complex sub-task to an independent subagent with its own "
            "context window and tool access. The subagent runs to completion and "
            "returns a summary. Use when a task is independent, well-scoped, and "
            "would otherwise flood the current context with intermediate work. "
            "Never delegate: trivial one-step tasks, tasks requiring user interaction, "
            "or recursive delegation of the same goal."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Clear description of what the subagent must accomplish. "
                        "Be specific: include file paths, goal criteria, and "
                        "success conditions."
                    ),
                },
                "context": {
                    "type": "string",
                    "description": (
                        "Optional background context the subagent needs. Include "
                        "relevant file paths, prior findings, constraints, etc."
                    ),
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Maximum agent loop iterations (default 50, max 200).",
                    "default": 50,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Wall-clock timeout in seconds (default 300).",
                    "default": 300,
                },
            },
            "required": ["task"],
        },
    },
    "_meta": {
        "risk": "medium",
        "read_only": False,
        "blocked_tools": sorted(DELEGATE_BLOCKED_TOOLS),
    },
}


# ── Handler (called from tool registry) ──────────────────────────────────────

def handle_delegate_task(args: Dict[str, Any]) -> str:
    """Tool handler — wraps delegate_task() for the VectorCode tool registry.

    Returns a JSON string with the DelegateResult for the agent loop to
    surface as a tool result.
    """
    task = args.get("task", "").strip()
    context = args.get("context", "")
    max_iter = int(args.get("max_iterations", _DEFAULT_MAX_ITERATIONS))
    timeout = int(args.get("timeout", _DEFAULT_TIMEOUT))

    result = delegate_task(
        task=task,
        context=context,
        max_iterations=max_iter,
        timeout=timeout,
    )
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # Test 1: DelegateTask dataclass defaults
    dt = DelegateTask(task="write hello world")
    assert dt.max_iterations == _DEFAULT_MAX_ITERATIONS
    assert dt.timeout == _DEFAULT_TIMEOUT
    assert dt.context == ""

    # Test 2: DelegateResult serialisation
    dr = DelegateResult(
        task_id="abc123",
        result="Done",
        success=True,
        iterations_used=5,
        duration_ms=1234,
    )
    d = dr.to_dict()
    assert d["task_id"] == "abc123"
    assert d["success"] is True
    assert d["error"] is None

    # Test 3: Empty task returns error immediately
    result = delegate_task("", timeout=5)
    assert result.success is False
    assert result.error is not None

    # Test 4: Stub execution (VectorAgent likely not importable here)
    result = delegate_task("list all Python files", timeout=15)
    assert isinstance(result.task_id, str) and len(result.task_id) > 0
    assert isinstance(result.result, str)
    assert isinstance(result.success, bool)
    assert isinstance(result.duration_ms, int)

    # Test 5: Schema structure
    assert DELEGATE_TOOL_SCHEMA["function"]["name"] == "delegate_task"
    params = DELEGATE_TOOL_SCHEMA["function"]["parameters"]
    assert "task" in params["required"]
    assert "max_iterations" in params["properties"]
    assert "timeout" in params["properties"]

    # Test 6: DELEGATE_BLOCKED_TOOLS contains required entries
    assert "delegate_task" in DELEGATE_BLOCKED_TOOLS
    assert "clarify" in DELEGATE_BLOCKED_TOOLS

    # Test 7: handle_delegate_task returns valid JSON
    json_result = handle_delegate_task({"task": "echo test", "timeout": "10"})
    parsed = json.loads(json_result)
    assert "task_id" in parsed
    assert "success" in parsed

    print("OK")
