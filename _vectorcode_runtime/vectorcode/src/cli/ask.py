"""Compatibility exports for legacy ``vectorcode.src.cli.ask`` imports."""

from vectorcode.src.vector_cli.ask import _build_tools, _get_memory_backend  # noqa: F401


def ask(prompt: str, **_kw) -> str:
    return input(prompt)


__all__ = ["ask", "_build_tools", "_get_memory_backend"]
