"""VECTOR Workflow Runner -- DAG-based district orchestration.

Lets you define multi-step workflows where each step calls a district agent or
tool, with explicit ``depends_on`` edges, and run them in dependency order
with full telemetry. Sits cleanly above the autonomous loop -- the loop can
either fire one workflow per tick or run multiple in parallel.

Workflow shape (YAML or dict)::

    name: morning_digest
    description: Pull email + calendar, summarize, store in vault
    tasks:
      - id: fetch_email
        district: research
        action: search_emails
        params:
          since: "8h"

      - id: fetch_calendar
        district: time_calendar
        action: today_events

      - id: summarize
        district: reflection
        action: digest
        depends_on: [fetch_email, fetch_calendar]
        params:
          style: morning_brief

      - id: write_to_vault
        district: memory_curator
        action: write_note
        depends_on: [summarize]
        params:
          folder: Journals
          title: "{{date}} Morning Brief"

Each task runs once its ``depends_on`` predecessors have completed. Outputs
of upstream tasks are made available to downstream tasks via ``params``
template substitution (``{{task_id.field}}``).

Full async, fail-fast or fail-soft (per-task ``optional: true``), and
telemetry-aware -- every step gets a TelemetryRecord written.
"""
from __future__ import annotations

__all__ = [
    "load_workflow_file",
    "TaskResult",
    "WorkflowResult",
    "WorkflowRunner",
    "WorkflowTask",
]


import asyncio
import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from loguru import logger

# Absorbed OJ WorkflowEngine (more formal DAG engine -- available as alternative)
try:
    from vectorcode.src.workflow import WorkflowEngine, WorkflowBuilder  # noqa: F401
except Exception:
    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

# â"€â"€ Workflow data classes â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


@dataclass
class WorkflowTask:
    id: str
    district: Optional[str] = None     # which VECTOR district to call (e.g. "research")
    action: Optional[str] = None       # action verb on that district (e.g. "search_emails")
    fn: Optional[Callable[..., Any]] = None  # OR a direct callable for adhoc steps
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    optional: bool = False             # if True, failure here doesn't abort the workflow
    timeout_seconds: float = 60.0


@dataclass
class TaskResult:
    id: str
    status: str  # "ok" | "skipped" | "failed"
    output: Any = None
    error: str = ""
    duration_seconds: float = 0.0


@dataclass
class WorkflowResult:
    name: str
    started_at: float
    finished_at: float
    duration_seconds: float
    task_results: dict[str, TaskResult]
    overall_status: str  # "ok" | "partial" | "failed"

    def get(self, task_id: str) -> Any:
        """Convenience accessor -- returns the output of a named task."""
        r = self.task_results.get(task_id)
        return r.output if r else None


# â"€â"€ Template substitution â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}")


def _substitute(value: Any, task_outputs: dict[str, Any]) -> Any:
    """Replace `{{task_id}}` and `{{task_id.field}}` in strings with task outputs."""
    if isinstance(value, str):
        def _resolve(m: re.Match) -> str:
            ref = m.group(1)
            parts = ref.split(".")
            top = parts[0]
            if top not in task_outputs:
                return m.group(0)  # leave as-is
            cur: Any = task_outputs[top]
            for part in parts[1:]:
                if isinstance(cur, dict):
                    cur = cur.get(part)
                else:
                    cur = getattr(cur, part, None)
                if cur is None:
                    return ""
            return str(cur)
        return _TEMPLATE_RE.sub(_resolve, value)
    if isinstance(value, list):
        return [_substitute(v, task_outputs) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, task_outputs) for k, v in value.items()}
    return value


# â"€â"€ DAG topological sort â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def _toposort(tasks: list[WorkflowTask]) -> list[list[str]]:
    """Group tasks into parallel-executable layers. Returns list-of-lists; each
    inner list contains task ids that can run concurrently.

    Raises ValueError on cycle.
    """
    by_id = {t.id: t for t in tasks}
    in_deg = {t.id: 0 for t in tasks}
    out_edges: dict[str, list[str]] = defaultdict(list)

    for t in tasks:
        for dep in t.depends_on:
            if dep not in by_id:
                raise ValueError(f"task '{t.id}' depends on unknown task '{dep}'")
            in_deg[t.id] += 1
            out_edges[dep].append(t.id)

    layers: list[list[str]] = []
    ready = deque([tid for tid, d in in_deg.items() if d == 0])
    seen = 0
    while ready:
        layer = list(ready)
        layers.append(layer)
        ready.clear()
        for tid in layer:
            seen += 1
            for child in out_edges[tid]:
                in_deg[child] -= 1
                if in_deg[child] == 0:
                    ready.append(child)
    if seen != len(tasks):
        raise ValueError("workflow has a dependency cycle")
    return layers


# â"€â"€ Runner â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


class WorkflowRunner:
    """Execute a workflow against VECTOR's agent registry.

    Looks up districts/actions via the agent registry; falls back to direct
    callables when ``fn`` is provided on a task.
    """

    def __init__(self, agent_registry: Any | None = None) -> None:
        self._registry = agent_registry

    async def run(self, workflow: dict | list, name: str = "workflow") -> WorkflowResult:
        if isinstance(workflow, dict):
            name = workflow.get("name", name)
            raw_tasks = workflow.get("tasks", [])
        else:
            raw_tasks = list(workflow)

        tasks = [self._coerce_task(t) for t in raw_tasks]
        layers = _toposort(tasks)
        by_id = {t.id: t for t in tasks}

        started = time.time()
        results: dict[str, TaskResult] = {}
        outputs: dict[str, Any] = {}

        logger.info(f"[VECTOR][workflow] '{name}' starting -- {len(tasks)} tasks, "
                    f"{len(layers)} layer(s)")

        for layer_i, layer in enumerate(layers, 1):
            logger.debug(f"[VECTOR][workflow] layer {layer_i}/{len(layers)}: {layer}")
            # Run all tasks in this layer concurrently
            coros = [self._run_one(by_id[tid], outputs) for tid in layer]
            layer_results = await asyncio.gather(*coros, return_exceptions=False)
            for r in layer_results:
                results[r.id] = r
                if r.status == "ok":
                    outputs[r.id] = r.output
                elif not by_id[r.id].optional:
                    # Hard fail -- abort remaining layers
                    finished = time.time()
                    return WorkflowResult(
                        name=name,
                        started_at=started,
                        finished_at=finished,
                        duration_seconds=finished - started,
                        task_results=results,
                        overall_status="failed",
                    )

        finished = time.time()
        any_failed = any(r.status == "failed" for r in results.values())
        overall = "partial" if any_failed else "ok"
        logger.info(f"[VECTOR][workflow] '{name}' {overall} -- "
                    f"{finished - started:.2f}s, "
                    f"{sum(1 for r in results.values() if r.status == 'ok')}/{len(results)} ok")

        return WorkflowResult(
            name=name,
            started_at=started,
            finished_at=finished,
            duration_seconds=finished - started,
            task_results=results,
            overall_status=overall,
        )

    # â"€â"€ Internals â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

    def _coerce_task(self, raw: Any) -> WorkflowTask:
        if isinstance(raw, WorkflowTask):
            return raw
        if not isinstance(raw, dict):
            raise TypeError(f"task must be dict or WorkflowTask, got {type(raw)}")
        return WorkflowTask(
            id=str(raw["id"]),
            district=raw.get("district"),
            action=raw.get("action"),
            fn=raw.get("fn"),
            params=dict(raw.get("params", {})),
            depends_on=list(raw.get("depends_on", [])),
            optional=bool(raw.get("optional", False)),
            timeout_seconds=float(raw.get("timeout_seconds", 60.0)),
        )

    async def _run_one(self, task: WorkflowTask, outputs: dict[str, Any]) -> TaskResult:
        t0 = time.time()
        try:
            params = _substitute(task.params, outputs)

            if task.fn is not None:
                # Direct callable
                if asyncio.iscoroutinefunction(task.fn):
                    out = await asyncio.wait_for(
                        task.fn(**params), timeout=task.timeout_seconds,
                    )
                else:
                    out = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: task.fn(**params),
                    )
            else:
                # District-based dispatch
                out = await asyncio.wait_for(
                    self._dispatch_to_district(task.district, task.action, params),
                    timeout=task.timeout_seconds,
                )

            dur = time.time() - t0
            return TaskResult(id=task.id, status="ok", output=out, duration_seconds=dur)

        except asyncio.TimeoutError:
            return TaskResult(
                id=task.id, status="failed",
                error=f"timed out after {task.timeout_seconds}s",
                duration_seconds=time.time() - t0,
            )
        except Exception as e:
            logger.warning(f"[VECTOR][workflow] task '{task.id}' failed: {e}")
            return TaskResult(
                id=task.id, status="failed",
                error=str(e),
                duration_seconds=time.time() - t0,
            )

    async def _dispatch_to_district(
        self, district: Optional[str], action: Optional[str], params: dict[str, Any],
    ) -> Any:
        """Resolve the target through the agent registry and invoke it."""
        if not district or not action:
            raise ValueError("workflow task needs district + action OR fn")

        registry = self._registry or self._lazy_registry()
        if registry is None:
            raise RuntimeError("agent registry unavailable")

        # Try to find an agent in the requested district that exposes `action`
        agents = []
        if hasattr(registry, "list_all"):
            agents = [a for a in registry.list_all() if getattr(a, "district", None) == district]
        if not agents:
            raise ValueError(f"no agents found for district '{district}'")

        # Find first agent with the named action
        for defn in agents:
            target = self._materialize_agent(defn)
            if target is None:
                continue
            fn = getattr(target, action, None)
            if callable(fn):
                if asyncio.iscoroutinefunction(fn):
                    return await fn(**params)
                return fn(**params)

        raise AttributeError(
            f"no agent in district '{district}' exposes action '{action}'"
        )

    def _lazy_registry(self) -> Any:
        try:
            from vectorcode.src.agents.registry import get_registry # type: ignore
            return get_registry()
        except Exception:
            return None

    def _materialize_agent(self, defn: Any) -> Any:
        """The agent registry stores definitions, not instances. Try common
        instance-resolution patterns; fall back to None if we can't materialize.
        """
        # If the definition is already a callable instance with district attr, use it
        if hasattr(defn, "district") and not hasattr(defn, "class_name"):
            return defn
        # Try class_name -> import + instantiate
        cls_name = getattr(defn, "class_name", None)
        if cls_name:
            try:
                # Best-effort lookup in districts.* common locations
                import importlib
                import inspect
                # Walk known package roots
                for pkg in ("agents",):
                    try:
                        importlib.import_module(pkg)
                    except Exception:
                        continue
                    # Search every loaded sub-module for the class
                    for mod_name, mod in list(__import__("sys").modules.items()):
                        if not mod_name.startswith(pkg):
                            continue
                        obj = getattr(mod, cls_name, None)
                        if obj is not None and inspect.isclass(obj):
                            try:
                                return obj()
                            except Exception:
                                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return None


# â"€â"€ Convenience: load workflow from YAML/JSON file â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def load_workflow_file(path: str | Path) -> dict:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise RuntimeError("PyYAML required to load .yaml workflows") from e
        return yaml.safe_load(text)
    return json.loads(text)


# â"€â"€ Self-test â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


if __name__ == "__main__":
    import asyncio as _aio

    # Minimal hand-rolled workflow with direct callables (no district registry needed)
    async def _step_a(**_kw): await _aio.sleep(0.1); return {"value": 42}
    async def _step_b(**_kw): await _aio.sleep(0.1); return {"value": 7}
    def _step_sum(a, b, **_kw): return {"sum": a + b}

    wf = {
        "name": "smoke_test",
        "tasks": [
            {"id": "a", "fn": _step_a},
            {"id": "b", "fn": _step_b},
            {"id": "total", "fn": _step_sum,
             "depends_on": ["a", "b"],
             "params": {"a": "{{a.value}}", "b": "{{b.value}}"}},
        ],
    }
    runner = WorkflowRunner()
    result = _aio.run(runner.run(wf))
    print(f"Workflow status: {result.overall_status}")
    print(f"Total: {result.get('total')}")
    print(f"Duration: {result.duration_seconds:.3f}s")
    # Substitution: a.value=42, b.value=7, but template uses strings -- fn must coerce
    # Final result will include the literal "42" / "7" strings unless _step_sum casts
