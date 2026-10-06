# Ported from GitHub/VectorCode_vectorcode/repo/run_agent.py
"""Tool execution: sequential, concurrent, and parallel-safety detection."""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from loguru import logger


# Tools that must never run concurrently (interactive / user-facing).
_NEVER_PARALLEL_TOOLS = frozenset({"clarify"})

# Read-only tools with no shared mutable session state.
_PARALLEL_SAFE_TOOLS = frozenset({
    "ha_get_state", "ha_list_entities", "ha_list_services",
    "read_file", "search_files", "session_search",
    "skill_view", "skills_list",
    "vision_analyze", "web_extract", "web_search",
})

# File tools can run concurrently when they target independent paths.
_PATH_SCOPED_TOOLS = frozenset({"read_file", "write_file", "patch"})

_MAX_TOOL_WORKERS = 8


def _extract_parallel_scope_path(tool_name: str, function_args: dict) -> Optional[Path]:
    if tool_name not in _PATH_SCOPED_TOOLS:
        return None
    raw_path = function_args.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    expanded = Path(raw_path).expanduser()
    if expanded.is_absolute():
        return Path(os.path.abspath(str(expanded)))
    return Path(os.path.abspath(str(Path.cwd() / expanded)))


def _paths_overlap(left: Path, right: Path) -> bool:
    left_parts = tuple(os.path.normcase(part) for part in left.parts)
    right_parts = tuple(os.path.normcase(part) for part in right.parts)
    if not left_parts or not right_parts:
        return bool(left_parts) == bool(right_parts) and bool(left_parts)
    common_len = min(len(left_parts), len(right_parts))
    return left_parts[:common_len] == right_parts[:common_len]


def _should_parallelize_tool_batch(tool_calls: list) -> bool:
    """Return True when a tool-call batch is safe to run concurrently."""
    if len(tool_calls) <= 1:
        return False
    tool_names = [tc.get("name") or tc.function.name for tc in tool_calls]
    if any(name in _NEVER_PARALLEL_TOOLS for name in tool_names):
        return False

    reserved_paths: list[Path] = []
    for tool_call in tool_calls:
        tool_name = tool_call.get("name") if isinstance(tool_call, dict) else tool_call.function.name
        try:
            raw_args = tool_call.get("arguments") if isinstance(tool_call, dict) else tool_call.function.arguments
            function_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except Exception:
            return False
        if not isinstance(function_args, dict):
            return False
        if tool_name in _PATH_SCOPED_TOOLS:
            scoped_path = _extract_parallel_scope_path(tool_name, function_args)
            if scoped_path is None:
                return False
            if any(_paths_overlap(scoped_path, existing) for existing in reserved_paths):
                return False
            reserved_paths.append(scoped_path)
            continue
        if tool_name not in _PARALLEL_SAFE_TOOLS:
            return False
    return True


def execute_tool_calls_sequential(
    tool_calls: list,
    dispatch_fn: Callable[[str, dict, Any], Any],
    context: Any,
) -> list:
    """Execute tool calls one at a time, returning list of results."""
    results = []
    for tc in tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else tc.function.name
        raw_args = tc.get("arguments") if isinstance(tc, dict) else tc.function.arguments
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            if not isinstance(args, dict):
                raise TypeError("tool arguments must decode to an object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            results.append({
                "id": tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None),
                "name": name,
                "result": {"error": f"invalid tool arguments: {exc}"},
            })
            continue
        call_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
        try:
            result = dispatch_fn(name, args, context)
        except Exception as e:
            logger.error(f"Tool {name} raised: {e}")
            result = {"error": str(e)}
        results.append({"id": call_id, "name": name, "result": result})
    return results


def execute_tool_calls_concurrent(
    tool_calls: list,
    dispatch_fn: Callable[[str, dict, Any], Any],
    context: Any,
    max_workers: int = _MAX_TOOL_WORKERS,
) -> list:
    """Execute tool calls in parallel (only call when _should_parallelize returns True)."""
    results = [None] * len(tool_calls)

    def _run(idx: int, tc):
        name = tc.get("name") if isinstance(tc, dict) else tc.function.name
        raw_args = tc.get("arguments") if isinstance(tc, dict) else tc.function.arguments
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            if not isinstance(args, dict):
                raise TypeError("tool arguments must decode to an object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            return idx, {
                "id": tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None),
                "name": name,
                "result": {"error": f"invalid tool arguments: {exc}"},
            }
        call_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
        try:
            result = dispatch_fn(name, args, context)
        except Exception as e:
            logger.error(f"Tool {name} raised: {e}")
            result = {"error": str(e)}
        return idx, {"id": call_id, "name": name, "result": result}

    with ThreadPoolExecutor(max_workers=min(max_workers, len(tool_calls))) as pool:
        futures = [pool.submit(_run, i, tc) for i, tc in enumerate(tool_calls)]
        for fut in as_completed(futures):
            idx, res = fut.result()
            results[idx] = res

    return results
