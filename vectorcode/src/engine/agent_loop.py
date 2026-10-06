"""
VectorCode Agent Loop — ported from VectorCode run_agent.py core.

The actual Think→Act→Observe execution loop that makes VectorCode an agent,
not just a chatbot. Without this, tool definitions are never executed.

Key patterns absorbed from VectorCode:
  - IterationBudget (thread-safe, parent/subagent independent)
  - run_conversation() main loop: call model → check tool_calls → execute → repeat
  - _execute_tool_calls_sequential() and _concurrent()
  - _should_parallelize_tool_batch() with _PARALLEL_SAFE_TOOLS
  - _recover_on_error() with credential rotation
  - _handle_max_iterations() graceful budget exhaustion
  - _sanitize_surrogates() for clipboard paste safety
  - _SafeWriter for daemon mode (OSError/ValueError from broken pipes)
"""
from pathlib import Path
import sys
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}


# ── SafeWriter (VectorCode _SafeWriter) ───────────────────────────────────────────

class _SafeWriter:
    """Transparent stdout/stderr wrapper — catches OSError/ValueError from broken pipes.
    Prevents crashes when running as systemd service, Docker container, or daemon."""

    __slots__ = ("_inner",)

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)

    def write(self, data):
        try:
            return self._inner.write(data)
        except (OSError, ValueError):
            return len(data) if isinstance(data, str) else 0

    def flush(self):
        try:
            self._inner.flush()
        except (OSError, ValueError):
            # Logging writes to this same stream and can recurse/deadlock.
            return None

    def fileno(self):
        return self._inner.fileno()

    def isatty(self):
        try:
            return self._inner.isatty()
        except (OSError, ValueError):
            return False

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _install_safe_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and not isinstance(stream, _SafeWriter):
            setattr(sys, stream_name, _SafeWriter(stream))


# ── Surrogate sanitization (VectorCode _sanitize_surrogates) ─────────────────────

_SURROGATE_RE = re.compile(r'[\ud800-\udfff]')


def _sanitize_surrogates(text: str) -> str:
    """Replace lone surrogate code points with U+FFFD. Prevents JSON crash from clipboard paste."""
    if _SURROGATE_RE.search(text):
        return _SURROGATE_RE.sub('�', text)
    return text


# ── Parallel tool execution helpers (VectorCode) ─────────────────────────────────

_NEVER_PARALLEL_TOOLS = frozenset({"clarify", "bash", "terminal"})

_PARALLEL_SAFE_TOOLS = frozenset({
    "read_file", "list_directory", "glob", "grep",
    "web_search", "web_fetch",
    "git_status", "git_diff", "git_log", "git_blame",
    "search_files",
})

_PATH_SCOPED_TOOLS = frozenset({"read_file", "write_file", "edit_file"})

_MAX_TOOL_WORKERS = 8

_DESTRUCTIVE_CMD_RE = re.compile(
    r"""(?:^|\s|&&|\|\||;|`)(?:
        rm\s|rmdir\s|
        cp\s|mv\s|
        sed\s+-i|
        truncate\s|
        dd\s|
        git\s+(?:reset|clean|checkout)\s
    )""",
    re.VERBOSE,
)
_REDIRECT_OVERWRITE_RE = re.compile(r'[^>]>[^>]|^>[^>]')


def _is_destructive_command(cmd: str) -> bool:
    if not cmd:
        return False
    if _DESTRUCTIVE_CMD_RE.search(cmd):
        return True
    if _REDIRECT_OVERWRITE_RE.search(cmd):
        return True
    return False


def _should_parallelize(tool_calls: list) -> bool:
    if len(tool_calls) <= 1:
        return False
    names = [tc.get("name", "") for tc in tool_calls]
    if any(n in _NEVER_PARALLEL_TOOLS for n in names):
        return False
    return all(n in _PARALLEL_SAFE_TOOLS for n in names)


# ── IterationBudget (VectorCode IterationBudget) ──────────────────────────────────

class IterationBudget:
    """Thread-safe iteration counter. Parent default=90, subagent default=50."""

    def __init__(self, max_total: int):
        self.max_total = max_total
        self._used = 0
        self._lock = threading.Lock()

    def consume(self) -> bool:
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        with self._lock:
            if self._used > 0:
                self._used -= 1

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.max_total - self._used)


# ── VectorAgent — the actual agent ────────────────────────────────────────────

class VectorAgent:
    """
    VectorCode's agent execution loop — ported from VectorCode AIAgent.

    Core contract:
      1. call model with current messages + tool schemas
      2. if model returns tool_calls → execute each → append results → goto 1
      3. if model returns text (no tool_calls) → done
      4. repeat up to max_iterations

    Callback hooks (all optional):
      tool_start_callback(name, args_preview)  — called before each tool
      tool_complete_callback(name, result_preview, duration_ms) — after each tool
      step_callback(iteration, model, tool_calls_count) — after each model call
      stream_delta_callback(delta: str) — token streaming
      clarify_callback(question, choices) → str — interactive user prompts
      approval_callback(event, tool_name, args) → bool — permission gate
    """

    MAX_ITERATIONS_DEFAULT  = 90
    SUBAGENT_MAX_ITERATIONS = 50

    def __init__(
        self,
        model_id: str = "",
        max_iterations: int = MAX_ITERATIONS_DEFAULT,
        project_dir: Optional[Path] = None,
        session_id: Optional[str] = None,
        iteration_budget: Optional[IterationBudget] = None,
        platform: str = "cli",
        quiet_mode: bool = False,
        save_trajectories: bool = True,
        # Callbacks
        tool_start_callback:    Optional[Callable] = None,
        tool_complete_callback: Optional[Callable] = None,
        step_callback:          Optional[Callable] = None,
        stream_delta_callback:  Optional[Callable] = None,
        clarify_callback:       Optional[Callable] = None,
        approval_callback:      Optional[Callable] = None,
    ):
        _install_safe_stdio()

        from vectorcode.src.session import VectorCodeSession
        self.session = VectorCodeSession.get()
        self.model_id  = model_id or self.session.current_model or "vector-focus"
        self.max_iterations = max_iterations
        self.iteration_budget = iteration_budget or IterationBudget(max_iterations)
        self.project_dir = project_dir or Path.cwd()
        self.session_id  = session_id or self.session.session_id
        self.platform    = platform
        self.quiet_mode  = quiet_mode
        self.save_trajectories = save_trajectories

        self._tool_start_cb    = tool_start_callback
        self._tool_complete_cb = tool_complete_callback
        self._step_cb          = step_callback
        self._stream_delta_cb  = stream_delta_callback
        self._clarify_cb       = clarify_callback
        self._approval_cb      = approval_callback

        # lazy-init tool router
        self._tool_router = None

    # ── Tool router ────────────────────────────────────────────────────────────

    def _get_tool_router(self):
        if self._tool_router is None:
            from vectorcode.src.tools.registry import ToolRouter
            self._tool_router = ToolRouter(
                project_dir=self.project_dir,
                approval_callback=self._approval_cb,
            )
        return self._tool_router

    def get_tool_schemas(self) -> list[dict]:
        return self._get_tool_router().get_schemas()

    # ── Core loop ─────────────────────────────────────────────────────────────

    def run_conversation(
        self,
        user_message: str,
        system_message: str = "",
        conversation_history: Optional[List[Dict]] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the full Think→Act→Observe loop until the model stops calling tools
        or max_iterations is reached.

        Returns:
            {
                "response": str,        # final assistant text
                "messages": list,       # full message history
                "iterations": int,      # tool call iterations used
                "tool_calls": list,     # all tool calls made
                "session_id": str,
            }
        """
        if isinstance(user_message, str):
            user_message = _sanitize_surrogates(user_message)

        effective_task_id = task_id or str(uuid.uuid4())
        self.iteration_budget = IterationBudget(self.max_iterations)

        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": user_message})

        tool_schemas = self.get_tool_schemas()
        all_tool_calls_made: list[dict] = []
        api_call_count = 0
        final_response = ""

        logger.info(
            "[VECTOR][agent_loop] session={} model={} task={} history={}",
            self.session_id, self.model_id, effective_task_id[:8], len(messages)
        )

        while self.iteration_budget.remaining > 0:
            if not self.iteration_budget.consume():
                logger.warning("[VECTOR][agent_loop] iteration budget exhausted at {}", api_call_count)
                final_response = self._handle_max_iterations(messages, api_call_count)
                break

            api_call_count += 1
            if self._step_cb:
                try:
                    self._step_cb(api_call_count, self.model_id, 0)
                except Exception as _sve:
                    logger.debug("[VECTOR][engine.agent_loop] suppressed Exception: {}", _sve)

            # ── Call the model ────────────────────────────────────────────────
            try:
                response = self._call_model(messages, system_message, tool_schemas)
            except Exception as e:
                logger.error("[VECTOR][agent_loop] model call failed: {}", e)
                final_response = f"[VECTOR error: model call failed — {e}]"
                break

            assistant_content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])
            finish_reason = response.get("finish_reason", "stop")

            # Record token usage
            usage = response.get("usage", {})
            if usage:
                self.session.record_token_usage(
                    prompt=usage.get("prompt_tokens", 0),
                    completion=usage.get("completion_tokens", 0),
                    cache_read=usage.get("cached_tokens", 0),
                )

            # ── If no tool calls → agent is done ────────────────────────────
            if not tool_calls:
                final_response = assistant_content or ""
                messages.append({"role": "assistant", "content": final_response})
                break

            # ── Execute tool calls → append results → continue ───────────────
            if self._step_cb:
                try:
                    self._step_cb(api_call_count, self.model_id, len(tool_calls))
                except Exception as _sve:
                    logger.debug("[VECTOR][engine.agent_loop] suppressed Exception: {}", _sve)

            # Append assistant message with tool_calls
            assistant_msg: dict = {"role": "assistant", "content": assistant_content or ""}
            assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            # Execute — parallel if safe, sequential otherwise
            if _should_parallelize(tool_calls):
                tool_results = self._execute_tool_calls_concurrent(tool_calls)
            else:
                tool_results = self._execute_tool_calls_sequential(tool_calls)

            # Append tool results
            for result in tool_results:
                messages.append(result)
                all_tool_calls_made.append({
                    "name": result.get("name", ""),
                    "tool_call_id": result.get("tool_call_id", ""),
                })

            # Context compaction check
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            if total_chars > 40_000:
                messages = self._compact_messages(messages, system_message)

        else:
            # Loop exited because iteration_budget hit zero without a break
            final_response = self._handle_max_iterations(messages, api_call_count)

        # Save trajectory
        if self.save_trajectories:
            self._save_trajectory(messages, user_message, completed=bool(final_response))

        return {
            "response":   final_response,
            "messages":   messages,
            "iterations": api_call_count,
            "tool_calls": all_tool_calls_made,
            "session_id": self.session_id,
        }

    # ── Model call ────────────────────────────────────────────────────────────

    def _call_model(
        self,
        messages: list,
        system_message: str,
        tool_schemas: list,
    ) -> dict:
        """
        Call the model via the VectorCode transport layer.
        Returns {"content", "tool_calls", "finish_reason", "usage"}.
        """
        from core.loop.context_engine import ContextEngine

        hydration = ContextEngine().session_hydration_prompt(
            {"session_id": self.session_id, "model": self.model_id}
        )
        effective_system = (
            f"{hydration}\n\n{system_message}" if hydration and system_message else hydration or system_message
        )
        call_messages = list(messages)
        if effective_system:
            call_messages.insert(0, {"role": "system", "content": effective_system})

        # Bare model names ("vector-focus") are local Ollama models: go straight there. (The router
        # import used to sit OUTSIDE the try below, and `ModelRouter` did not exist, so every call
        # died with an ImportError before the Ollama fallback could run.)
        if "/" not in self.model_id:
            return self._call_ollama_direct(call_messages, tool_schemas)

        try:
            from vectorcode.src.providers.router import ModelRouter
            router = ModelRouter(project_dir=self.project_dir)
            result = router.complete(
                self.model_id,
                call_messages,
                tools=tool_schemas or None,
                stream=not self.quiet_mode,
                max_tokens=8192,
            )
            # result.message.content, result.message.tool_calls, etc.
            msg = result.message
            return {
                "content":      getattr(msg, "content", "") or "",
                "tool_calls":   self._normalize_tool_calls(getattr(msg, "tool_calls", None) or []),
                "finish_reason": getattr(result, "finish_reason", "stop"),
                "usage":        self._extract_usage(result),
            }
        except Exception as e:
            raise

    @staticmethod
    def _to_ollama_messages(messages: list, system_message: str = "") -> list:
        """Convert the loop's message history to Ollama's chat format.

        The loop stores assistant tool calls as {id, name, arguments-json-string}; Ollama expects
        {function: {name, arguments-dict}}, and it never receives the system prompt otherwise.
        """
        out: list = []
        if system_message:
            out.append({"role": "system", "content": system_message})
        for m in messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                calls = []
                for tc in m["tool_calls"]:
                    args = tc.get("arguments", "{}")
                    try:
                        args = json.loads(args) if isinstance(args, str) else (args or {})
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    calls.append({"function": {"name": tc.get("name", ""), "arguments": args}})
                out.append({"role": "assistant", "content": m.get("content", "") or "", "tool_calls": calls})
            elif m.get("role") == "tool":
                out.append({"role": "tool", "content": str(m.get("content", "")), "tool_name": m.get("name", "")})
            else:
                out.append({"role": m.get("role", "user"), "content": str(m.get("content", "") or "")})
        return out

    def _call_ollama_direct(self, messages: list, tool_schemas: list, system_message: str = "") -> dict:
        """Direct Ollama call for bare model names like 'vector-focus'."""
        import ollama
        kwargs: dict = {"model": self.model_id,
                        "messages": self._to_ollama_messages(messages, system_message), "stream": False}
        if tool_schemas:
            kwargs["tools"] = tool_schemas
        resp = ollama.chat(**kwargs)
        msg = resp.get("message", {})
        tool_calls = []
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            tool_calls.append({
                "id":   tc.get("id", str(uuid.uuid4())[:8]),
                "name": fn.get("name", ""),
                "arguments": json.dumps(fn.get("arguments", {}))
                             if isinstance(fn.get("arguments"), dict)
                             else str(fn.get("arguments", "{}")),
            })
        return {
            "content":      msg.get("content", "") or "",
            "tool_calls":   tool_calls,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens":     resp.get("prompt_eval_count", 0),
                "completion_tokens": resp.get("eval_count", 0),
            },
        }

    def _normalize_tool_calls(self, raw: list) -> list[dict]:
        """Normalize tool_calls from transport layer to {id, name, arguments} dicts."""
        result = []
        for tc in (raw or []):
            if hasattr(tc, "id"):
                # ToolCall dataclass from transports/types.py
                result.append({
                    "id":        tc.id or str(uuid.uuid4())[:8],
                    "name":      tc.name,
                    "arguments": tc.arguments,
                })
            elif isinstance(tc, dict):
                fn = tc.get("function", {})
                result.append({
                    "id":        tc.get("id", str(uuid.uuid4())[:8]),
                    "name":      fn.get("name", tc.get("name", "")),
                    "arguments": fn.get("arguments", tc.get("arguments", "{}")),
                })
        return result

    def _extract_usage(self, result) -> dict:
        usage = getattr(result, "usage", None)
        if usage is None:
            return {}
        if hasattr(usage, "prompt_tokens"):
            return {
                "prompt_tokens":     usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cached_tokens":     getattr(usage, "cached_tokens", 0),
            }
        return {}

    # ── Tool execution ────────────────────────────────────────────────────────

    def _execute_tool_calls_sequential(self, tool_calls: list) -> list[dict]:
        results = []
        for tc in tool_calls:
            result = self._execute_one_tool(tc)
            results.append(result)
        return results

    def _execute_tool_calls_concurrent(self, tool_calls: list) -> list[dict]:
        results: list[dict | None] = [None] * len(tool_calls)
        with ThreadPoolExecutor(max_workers=min(_MAX_TOOL_WORKERS, len(tool_calls))) as pool:
            futures = {pool.submit(self._execute_one_tool, tc): i
                       for i, tc in enumerate(tool_calls)}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    tc = tool_calls[idx]
                    results[idx] = self._make_tool_result(
                        tc.get("id", ""), tc.get("name", ""),
                        f"[tool execution error: {e}]",
                    )
        return [r for r in results if r is not None]

    def _execute_one_tool(self, tc: dict) -> dict:
        tool_id   = tc.get("id", str(uuid.uuid4())[:8])
        tool_name = tc.get("name", "")
        raw_args  = tc.get("arguments", "{}")

        # Parse args
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            if not isinstance(args, dict):
                raise TypeError("tool arguments must decode to an object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            return self._make_tool_result(
                tool_id,
                tool_name,
                f"[BLOCKED: invalid tool arguments for {tool_name}: {exc}]",
            )

        # Approval gate for destructive tools
        if self._approval_cb:
            try:
                allowed = self._approval_cb("pre_tool_call", tool_name, args)
                if not allowed:
                    return self._make_tool_result(
                        tool_id, tool_name,
                        f"[BLOCKED: user denied {tool_name}]",
                    )
            except Exception as _sve:
                logger.error(
                    "[VECTOR][engine.agent_loop] approval callback failed closed for {}: {}",
                    tool_name,
                    _sve,
                )
                return self._make_tool_result(
                    tool_id, tool_name,
                    f"[BLOCKED: approval check failed for {tool_name}]",
                )

        # Notify start
        if self._tool_start_cb:
            try:
                preview = json.dumps(args)[:80]
                self._tool_start_cb(tool_name, preview)
            except Exception as _sve:
                logger.debug("[VECTOR][engine.agent_loop] suppressed Exception: {}", _sve)

        t0 = time.perf_counter()

        # Execute
        try:
            router = self._get_tool_router()
            output = router.execute(tool_name, args)
        except Exception as e:
            output = f"[{tool_name} error: {e}]"
            logger.error("[VECTOR][agent_loop] tool {} failed: {}", tool_name, e)

        duration_ms = int((time.perf_counter() - t0) * 1000)

        # Notify complete
        if self._tool_complete_cb:
            try:
                self._tool_complete_cb(tool_name, str(output)[:100], duration_ms)
            except Exception as _sve:
                logger.debug("[VECTOR][engine.agent_loop] suppressed Exception: {}", _sve)

        self.session.tool_calls.append({
            "name": tool_name, "args": args, "duration_ms": duration_ms,
        })

        return self._make_tool_result(tool_id, tool_name, str(output))

    def _make_tool_result(self, tool_id: str, tool_name: str, content: str) -> dict:
        return {
            "role":         "tool",
            "tool_call_id": tool_id,
            "name":         tool_name,
            "content":      content,
        }

    # ── Context compaction ────────────────────────────────────────────────────

    def _compact_messages(self, messages: list, system_message: str) -> list:
        try:
            from vectorcode.src.context.compactor import ContextCompactor
            compactor = ContextCompactor(
                model=self.model_id,
                project_dir=self.project_dir,
            )
            return compactor.compact(messages)
        except Exception as e:
            logger.warning("[VECTOR][agent_loop] compaction failed: {}", e)
            return messages

    # ── Max iterations handler ────────────────────────────────────────────────

    def _handle_max_iterations(self, messages: list, iteration_count: int) -> str:
        warn = (
            f"⚠️ Iteration budget exhausted ({iteration_count}/{self.max_iterations}). "
            "Generating summary of work completed so far."
        )
        logger.warning("[VECTOR][agent_loop] {}", warn)

        # Ask model to summarize what was done
        summary_prompt = (
            "You have reached the maximum number of tool-calling iterations. "
            "Summarize:\n1. What was accomplished\n2. What remains\n3. How to continue\n\n"
            "Be concise and actionable."
        )
        try:
            summary_messages = messages + [{"role": "user", "content": summary_prompt}]
            resp = self._call_model(summary_messages, "", [])
            return resp.get("content", warn)
        except Exception:
            return warn

    # ── Trajectory saving ─────────────────────────────────────────────────────

    def _save_trajectory(self, messages: list, user_message: str, completed: bool) -> None:
        try:
            traj_dir = Path.home() / ".vector"
            traj_dir.mkdir(parents=True, exist_ok=True)
            filename = "trajectory_samples.jsonl" if completed else "failed_trajectories.jsonl"
            traj_path = traj_dir / filename

            turns = []
            for m in messages:
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "system":
                    continue
                from_role = "human" if role == "user" else "gpt"
                if isinstance(content, str) and content.strip():
                    # Convert REASONING_SCRATCHPAD → <think> (VectorCode pattern)
                    content = content.replace(
                        "<REASONING_SCRATCHPAD>", "<think>"
                    ).replace("</REASONING_SCRATCHPAD>", "</think>")
                    turns.append({"from": from_role, "value": content})

            if not turns:
                return

            import json as _json
            record = {
                "conversations": turns,
                "model":         self.model_id,
                "session_id":    self.session_id,
                "completed":     completed,
                "ts":            int(time.time()),
            }
            with traj_path.open("a", encoding="utf-8") as f:
                f.write(_json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("[VECTOR][agent_loop] trajectory save failed: {}", e)


# ── Convenience factory ───────────────────────────────────────────────────────

def make_agent(
    model_id: str = "",
    project_dir: Optional[Path] = None,
    max_iterations: int = VectorAgent.MAX_ITERATIONS_DEFAULT,
    quiet_mode: bool = False,
    **kwargs,
) -> VectorAgent:
    """Factory — creates a VectorAgent with sensible defaults."""
    from vectorcode.src.session import VectorCodeSession
    sess = VectorCodeSession.get()
    return VectorAgent(
        model_id=model_id or sess.current_model or "vector-focus",
        project_dir=project_dir or Path.cwd(),
        max_iterations=max_iterations,
        session_id=sess.session_id,
        quiet_mode=quiet_mode,
        **kwargs,
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # Smoke test: IterationBudget
    budget = IterationBudget(5)
    assert budget.consume()
    assert budget.used == 1
    assert budget.remaining == 4
    for _ in range(4):
        budget.consume()
    assert not budget.consume()  # budget exhausted
    budget.refund()
    assert budget.remaining == 1
    print("IterationBudget OK")

    # Smoke test: _should_parallelize
    safe_batch = [
        {"name": "read_file", "arguments": '{"path": "a.py"}'},
        {"name": "web_search", "arguments": '{"query": "test"}'},
    ]
    unsafe_batch = [
        {"name": "bash", "arguments": '{"command": "ls"}'},
        {"name": "read_file", "arguments": '{"path": "a.py"}'},
    ]
    assert _should_parallelize(safe_batch)
    assert not _should_parallelize(unsafe_batch)
    assert not _should_parallelize([safe_batch[0]])  # single → no parallel
    print("_should_parallelize OK")

    # Smoke test: VectorAgent instantiates
    agent = make_agent(max_iterations=3, quiet_mode=True)
    assert agent.max_iterations == 3
    assert agent.iteration_budget.remaining == 3
    assert agent.project_dir is not None
    print("VectorAgent instantiation OK")

    # _sanitize_surrogates
    dirty = "hello\ud800world"
    clean = _sanitize_surrogates(dirty)
    assert "\ud800" not in clean and "�" in clean
    print("_sanitize_surrogates OK")

    print("core/agent_loop.py OK")
