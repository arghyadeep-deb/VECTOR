# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Sandboxed REPL environment for the RLM agent.

Provides a persistent Python namespace with injected helper functions
(``llm_query``, ``llm_batch``, ``FINAL``, ``FINAL_VAR``) that the RLM
agent's generated code uses to decompose context and make recursive
sub-LM calls.
"""

from __future__ import annotations
from loguru import logger

import io
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable, Dict, List, Optional

# Safe stdlib modules pre-injected into the REPL namespace
_SAFE_MODULES = [
    "json",
    "re",
    "math",
    "collections",
    "itertools",
    "functools",
    "textwrap",
    "string",
    "copy",
    "datetime",
]

# Patterns blocked for security
_BLOCKED_PATTERNS = [
    "os.system",
    "os.popen",
    "subprocess",
    "shutil.rmtree",
    "__import__",
    "open(",
    "ctypes",
    "socket",
    "http.client",
    "urllib",
    # Class-hierarchy traversal (sandbox escape via Python MRO)
    "__subclasses__",
    "__bases__",
    "__mro__",
    "__builtins__",
    "__globals__",
    "__code__",
    "__reduce__",
    "__reduce_ex__",
    "importlib",
]

class RLMRepl:
    """Sandboxed Python REPL with persistent namespace for the RLM agent.

    Parameters
    ----------
    llm_query_fn:
        Callback invoked when REPL code calls ``llm_query(prompt)``.
    llm_batch_fn:
        Callback invoked when REPL code calls ``llm_batch(prompts)``.
    max_output_chars:
        Maximum characters captured from stdout per execution.
    """

    def __init__(
        self,
        llm_query_fn: Optional[Callable[[str], str]] = None,
        llm_batch_fn: Optional[Callable[[List[str]], List[str]]] = None,
        *,
        max_output_chars: int = 10000,
    ) -> None:
        self._max_output_chars = max_output_chars
        self._terminated = False
        self._final_value: Any = None

        # Build namespace
        self._namespace: Dict[str, Any] = {}

        # Inject safe stdlib modules
        for mod_name in _SAFE_MODULES:
            try:
                import importlib

                self._namespace[mod_name] = importlib.import_module(mod_name)
            except ImportError:
                logger.opt(exception=True).debug("[VECTOR] suppressed exception")

        # answer dict — code can set answer["ready"] = True, answer["value"] = ...
        self._namespace["answer"] = {"ready": False, "value": None}

        # Inject FINAL / FINAL_VAR
        self._namespace["FINAL"] = self._final
        self._namespace["FINAL_VAR"] = self._final_var

        # Inject llm_query / llm_batch
        if llm_query_fn is not None:
            self._namespace["llm_query"] = llm_query_fn
        if llm_batch_fn is not None:
            self._namespace["llm_batch"] = llm_batch_fn

    # ------------------------------------------------------------------
    # Termination helpers
    # ------------------------------------------------------------------

    def _final(self, value: Any) -> None:
        """Mark the REPL as terminated with a final answer."""
        self._terminated = True
        self._final_value = value

    def _final_var(self, var_name: str) -> None:
        """Mark the REPL as terminated, using a namespace variable as the answer."""
        value = self._namespace.get(var_name)
        self._terminated = True
        self._final_value = value

    @property
    def is_terminated(self) -> bool:
        """Check if FINAL/FINAL_VAR was called or answer["ready"] is True."""
        if self._terminated:
            return True
        answer = self._namespace.get("answer", {})
        if isinstance(answer, dict) and answer.get("ready"):
            return True
        return False

    @property
    def final_answer(self) -> Any:
        """Return the termination value."""
        if self._terminated:
            return self._final_value
        answer = self._namespace.get("answer", {})
        if isinstance(answer, dict) and answer.get("ready"):
            return answer.get("value")
        return None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def security_check(self, code: str) -> Optional[str]:
        """Check code for dangerous patterns. Returns error message or None."""
        for pattern in _BLOCKED_PATTERNS:
            if pattern in code:
                return f"Blocked: code contains prohibited pattern '{pattern}'"
        return None

    def execute(self, code: str) -> str:
        """Execute code in the REPL namespace."""
        logger.warning("[VECTOR][rlm_repl] code execution: {:.200}", code)

        # Security check
        violation = self.security_check(code)
        if violation is not None:
            return f"Error: {violation}"

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                if "__builtins__" not in self._namespace:
                    self._namespace.setdefault("__builtins__", {k: __builtins__[k] for k in ("print", "range", "len", "list", "dict", "float", "int", "str", "bool", "min", "max", "sum", "abs", "enumerate", "zip", "map", "filter", "any", "all", "sorted", "reversed", "isinstance", "hasattr", "getattr", "type", "True", "False", "None", "Exception", "ValueError", "TypeError", "KeyError", "IndexError", "AttributeError", "StopIteration", "iter", "next") if k in __builtins__})
                exec(code, self._namespace)  # noqa: S102
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            return error_msg

        output = stdout_buf.getvalue()
        err_output = stderr_buf.getvalue()
        if err_output:
            output += ("\n" if output else "") + err_output

        # Truncate if needed
        if len(output) > self._max_output_chars:
            output = output[: self._max_output_chars] + "\n... (output truncated)"

        return output

    # ------------------------------------------------------------------
    # Namespace access
    # ------------------------------------------------------------------

    def set_variable(self, name: str, value: Any) -> None:
        """Set a variable in the REPL namespace."""
        self._namespace[name] = value

    def get_variable(self, name: str) -> Any:
        """Get a variable from the REPL namespace."""
        return self._namespace.get(name)

__all__ = ["RLMRepl"]
