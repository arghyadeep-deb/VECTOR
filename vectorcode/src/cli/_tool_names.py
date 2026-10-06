"""CLI shim for _tool_names."""

from loguru import logger
try:
    from vectorcode.src.vector_cli._tool_names import *
except ImportError:
    # The real resolve_tool_names(cli_value, *configured_values) comes from
    # the wildcard import above. A fallback stub here previously redefined
    # resolve_tool_names unconditionally -- even when the import succeeded --
    # with a single-argument passthrough signature. Every real caller
    # (vector_cli/ask.py, vector_cli/chat_cmd.py) calls it with 3 positional
    # arguments, so this crashed with TypeError on every agent-mode
    # ask/chat invocation. Do not reintroduce a stub function below this
    # point.
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")
