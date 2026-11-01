"""Policy gates for runtime Python code execution."""

from __future__ import annotations

import os


class DynamicExecutionDisabled(RuntimeError):
    """Raised when a feature tries to execute Python code without opt-in."""


def dynamic_strategy_execution_enabled() -> bool:
    return os.environ.get("VECTOR_ALLOW_DYNAMIC_STRATEGIES", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def require_dynamic_strategy_execution(feature: str) -> None:
    if not dynamic_strategy_execution_enabled():
        raise DynamicExecutionDisabled(
            f"{feature} requires VECTOR_ALLOW_DYNAMIC_STRATEGIES=1. "
            "Leave it disabled in production unless strategy code is trusted or sandboxed."
        )
