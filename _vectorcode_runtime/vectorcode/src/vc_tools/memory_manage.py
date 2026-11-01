# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Manage persistent agent memory (MEMORY.md)."""

from __future__ import annotations

from pathlib import Path

from vectorcode.src.vc_core.registry import ToolRegistry
from vectorcode.src.vc_tools._markdown_store import MarkdownStoreTool


@ToolRegistry.register("memory_manage")
class MemoryManageTool(MarkdownStoreTool):
    """Manage persistent agent memory (MEMORY.md)."""

    store_name = "memory_manage"
    subject = "persistent agent memory"
    entry_subject = "memory entry"
    missing_file_msg = "Memory file does not exist."

    def __init__(self, memory_path: Path | str = "~/.vector/MEMORY.md") -> None:
        super().__init__(memory_path)
