"""Compatibility shim for canonical storage context helpers."""

from vectorcode.src.vc_tools.storage.context import (
    ContextConfig,
    format_context,
    inject_context,
)

__all__ = ["ContextConfig", "format_context", "inject_context"]
