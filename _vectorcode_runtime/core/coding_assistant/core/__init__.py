from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.coding_assistant.core.programmatic import run_programmatic as run_programmatic


def __getattr__(name: str) -> object:
    if name == "run_programmatic":
        from core.coding_assistant.core.programmatic import run_programmatic

        return run_programmatic

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
