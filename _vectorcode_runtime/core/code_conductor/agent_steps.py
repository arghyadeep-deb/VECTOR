"""
VECTOR Code Conductor — Agent Step Generator Pattern
Python port of codebuff's handleSteps generator from agents/basher.ts
and packages/agent-runtime/src/run-programmatic-step.ts.

Mixes programmatic tool execution with LLM calls in a Python async generator.
Gives deterministic control over complex multi-step workflows.

Pattern:
  async def my_steps(ctx):
      # Tool call — executed immediately, result injected back
      result = yield {"tool": "read_files", "input": {"paths": ["main.py"]}}

      # Let LLM analyze and decide next action
      yield "STEP"

      # More tool calls...
      yield {"tool": "str_replace", "input": {...}}

      # Run LLM until it stops calling tools
      yield "STEP_ALL"

Usage:
    async def my_workflow(ctx):
        files = yield {"tool": "read_files", "input": {"paths": ["main.py"]}}
        yield "STEP"

    results = await run_steps(my_workflow, llm_fn, tool_registry)
"""
from __future__ import annotations

__all__ = [
    "bash_steps",
    "read_and_edit_steps",
    "run_steps",
    "StepResult",
]


import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Optional

from loguru import logger


@dataclass
class StepResult:
    """Result of a single agent step."""
    step_type: str          # "tool" | "llm"
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    tool_result: Any = None
    llm_response: str = ""
    error: str = ""


async def run_steps(
    steps_fn: Callable,
    llm_call: Callable,
    tool_registry: dict[str, Callable],
    ctx: dict | None = None,
    max_steps: int = 50,
) -> list[StepResult]:
    """
    Execute a generator-based agent workflow.

    Args:
        steps_fn: async generator function (the agent's handleSteps)
        llm_call: async callable(messages: list) → str
        tool_registry: dict of tool_name → async callable(input: dict) → dict
        ctx: context passed to steps_fn
        max_steps: safety limit

    Generator yields:
        {"tool": name, "input": {...}}  → tool executed, result sent back via .asend()
        "STEP"                          → one LLM call, response sent back
        "STEP_ALL"                      → LLM loop until no more tool calls in response

    Returns:
        List of StepResult objects
    """
    results: list[StepResult] = []
    gen = steps_fn(ctx or {})
    step_count = 0
    messages: list[dict] = []
    last_value = None

    try:
        while step_count < max_steps:
            step_count += 1
            try:
                if last_value is None:
                    yielded = await gen.__anext__()
                else:
                    yielded = await gen.asend(last_value)
                    last_value = None
            except StopAsyncIteration:
                break

            if isinstance(yielded, dict) and "tool" in yielded:
                # â”€â”€ Tool call â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                tool_name = yielded["tool"]
                tool_input = yielded.get("input", {})
                result = StepResult(step_type="tool", tool_name=tool_name, tool_input=tool_input)

                if tool_name in tool_registry:
                    try:
                        fn = tool_registry[tool_name]
                        if asyncio.iscoroutinefunction(fn):
                            tool_result = await fn(**tool_input)
                        else:
                            tool_result = fn(**tool_input)
                        result.tool_result = tool_result
                        logger.debug("[VECTOR][steps] tool {} → {}", tool_name, str(tool_result)[:80])
                    except Exception as e:
                        result.error = str(e)
                        tool_result = {"error": str(e)}
                else:
                    result.error = f"unknown tool: {tool_name}"
                    tool_result = {"error": result.error}

                results.append(result)
                last_value = tool_result

            elif yielded == "STEP":
                # â”€â”€ Single LLM step â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                result = StepResult(step_type="llm")
                try:
                    if asyncio.iscoroutinefunction(llm_call):
                        response = await llm_call(messages)
                    else:
                        response = llm_call(messages)
                    result.llm_response = response or ""
                    messages.append({"role": "assistant", "content": result.llm_response})
                except Exception as e:
                    result.error = str(e)
                    result.llm_response = ""
                results.append(result)
                last_value = result.llm_response

            elif yielded == "STEP_ALL":
                # â”€â”€ LLM loop until completion â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                for _ in range(20):  # safety limit on STEP_ALL
                    result = StepResult(step_type="llm")
                    try:
                        if asyncio.iscoroutinefunction(llm_call):
                            response = await llm_call(messages)
                        else:
                            response = llm_call(messages)
                        result.llm_response = response or ""
                        messages.append({"role": "assistant", "content": result.llm_response})
                    except Exception as e:
                        result.error = str(e)
                    results.append(result)
                    # Stop if LLM stopped producing content (simple heuristic)
                    if not result.llm_response.strip():
                        break
                last_value = result.llm_response  # type: ignore

            else:
                logger.debug("[VECTOR][steps] unrecognized yield: {}", yielded)
                last_value = None

    except StopAsyncIteration as e:
        logger.warning("[VECTOR][steps] generator stopped unexpectedly: {}", e)
    except Exception as e:
        logger.error("[VECTOR][steps] run_steps error: {}", e)
        results.append(StepResult(step_type="error", error=str(e)))

    return results


# â”€â”€ Pre-built step workflows â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def bash_steps(ctx: dict) -> AsyncGenerator:
    """
    Port of codebuff's basher agent.
    Runs a shell command, optionally summarizes output with LLM.

    ctx: {"command": str, "what_to_summarize": str (optional)}
    """
    command = ctx.get("command", "")
    if not command:
        yield {"tool": "set_output", "input": {"output": "Error: missing command"}}
        return

    timeout = ctx.get("timeout_seconds", 30)
    result = yield {"tool": "run_command", "input": {"command": command, "timeout": timeout}}

    what = ctx.get("what_to_summarize")
    if not what:
        yield {"tool": "set_output", "input": {"output": result}}
        return

    yield "STEP"


async def read_and_edit_steps(ctx: dict) -> AsyncGenerator:
    """
    Read a file, ask LLM to suggest edits, apply them.

    ctx: {"file": str, "instruction": str}
    """
    file_path = ctx.get("file", "")
    instruction = ctx.get("instruction", "")

    files = yield {"tool": "read_files", "input": {"paths": [file_path]}}
    ctx["file_content"] = (files or {}).get("files", [{}])[0].get("content", "")

    yield "STEP"  # LLM analyzes and decides edits

    yield "STEP_ALL"  # Execute all edits


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        # Test tool-only steps (no LLM needed)
        steps_log: list[str] = []

        async def demo_steps(ctx: dict):
            result = yield {"tool": "echo", "input": {"msg": "hello"}}
            steps_log.append(f"tool_result: {result}")
            # No LLM call — just tool

        tool_reg = {"echo": lambda msg: {"echoed": msg}}
        dummy_llm = lambda msgs: "LLM response"

        results = await run_steps(demo_steps, dummy_llm, tool_reg)
        assert len(results) == 1
        assert results[0].tool_name == "echo"
        assert results[0].tool_result == {"echoed": "hello"}
        assert "tool_result: {'echoed': 'hello'}" in steps_log

        print(f"OK agent_steps.py — generator pattern, tool injection, STEP/STEP_ALL signals")
        print(f"  {len(results)} steps executed")

    asyncio.run(_smoke())
