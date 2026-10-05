# VECTOR module — shared CRUD base for line-oriented Markdown store tools.
# Owner: Arghyadeep Deb
# Extracted to de-duplicate memory_manage.py / user_profile_manage.py (audit #27f).

"""Shared CRUD base for Markdown-backed store tools.

`memory_manage` and `user_profile_manage` were byte-for-byte identical except
for the backing file path and a couple of nouns in their descriptions. Bug
fixes (e.g. the path-traversal/empty-entry guards) only ever landed in one
copy. This base centralizes the read/add/update/remove logic; concrete tools
become thin subclasses that declare their file path and labels.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec


class MarkdownStoreTool(BaseTool):
    """CRUD over a line-oriented Markdown file (one ``- entry`` per line).

    Subclasses declare:
      * ``store_name``        — registered tool name + ``ToolSpec.name``
      * ``subject``           — noun for the action description ("memory")
      * ``entry_subject``     — noun for the entry description ("memory entry")
      * ``missing_file_msg``  — message when the file does not exist
    and pass the backing path to ``__init__``.
    """

    store_name: str = ""
    subject: str = ""
    entry_subject: str = ""
    store_category: str = "memory"
    missing_file_msg: str = "File does not exist."

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path).expanduser()

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.store_name,
            description=(
                f"Read, add, update, or remove entries in {self.subject}."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "add", "update", "remove"],
                        "description": f"Action to perform on {self.subject}.",
                    },
                    "entry": {
                        "type": "string",
                        "description": (
                            f"The {self.entry_subject} content "
                            "(for add/update/remove)."
                        ),
                    },
                    "new_entry": {
                        "type": "string",
                        "description": (
                            "Replacement content (for update action only)."
                        ),
                    },
                },
                "required": ["action"],
            },
            category=self.store_category,
        )

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action", "read")
        entry = params.get("entry", "")
        new_entry = params.get("new_entry", "")
        if action == "read":
            return self._read()
        elif action == "add":
            return self._add(entry)
        elif action == "update":
            return self._update(entry, new_entry)
        elif action == "remove":
            return self._remove(entry)
        return ToolResult(
            tool_name=self.spec.name,
            success=False,
            content=f"Unknown action: {action}",
        )

    def _write_atomic(self, content: str) -> None:
        """Write *content* to ``self._path`` via tempfile + fsync + os.replace.

        Avoids truncating/corrupting the store if the process crashes
        mid-write (plain ``write_text()`` is not crash-safe).
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=f".{self._path.name}."
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, self._path)
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _read(self) -> ToolResult:
        content = ""
        if self._path.exists():
            content = self._path.read_text(encoding="utf-8")
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=content or "(empty)",
        )

    def _add(self, entry: str) -> ToolResult:
        if not entry:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Entry cannot be empty.",
            )
        existing = (
            self._path.read_text(encoding="utf-8") if self._path.exists() else ""
        )
        self._write_atomic(existing.rstrip() + f"\n- {entry}\n")
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Added: {entry}",
        )

    def _update(self, old: str, new: str) -> ToolResult:
        if not old:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Entry cannot be empty.",
            )
        if not self._path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=self.missing_file_msg,
            )
        text = self._path.read_text(encoding="utf-8")
        if old not in text:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Entry not found: {old}",
            )
        self._write_atomic(text.replace(old, new, 1))
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Updated: {old} -> {new}",
        )

    def _remove(self, entry: str) -> ToolResult:
        if not entry:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Entry cannot be empty.",
            )
        if not self._path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=self.missing_file_msg,
            )
        text = self._path.read_text(encoding="utf-8")
        lines = text.split("\n")
        new_lines = [ln for ln in lines if entry not in ln]
        if len(new_lines) == len(lines):
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Entry not found: {entry}",
            )
        self._write_atomic("\n".join(new_lines))
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Removed: {entry}",
        )
