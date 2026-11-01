# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Manage persistent user profile (USER.md)."""

from __future__ import annotations

from pathlib import Path

from vectorcode.src.vc_core.registry import ToolRegistry
from vectorcode.src.vc_tools._markdown_store import MarkdownStoreTool


@ToolRegistry.register("user_profile_manage")
class UserProfileManageTool(MarkdownStoreTool):
    """Manage persistent user profile (USER.md)."""

    store_name = "user_profile_manage"
    subject = "user profile"
    entry_subject = "profile entry"
    missing_file_msg = "User profile file does not exist."

    def __init__(self, user_path: Path | str = "~/.vector/USER.md") -> None:
        super().__init__(user_path)
