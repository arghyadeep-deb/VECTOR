# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""SkillManageTool — create, list, load, or delete agent-authored skills."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, List, Optional

from vectorcode.src.vc_core.registry import ToolRegistry
from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec

def _toml_string(value: object) -> str:
    """Serialize *value* as an escaped TOML basic string (double-quoted)."""
    return json.dumps(str(value), ensure_ascii=False)

@ToolRegistry.register("skill_manage")
class SkillManageTool(BaseTool):
    """Manage agent-authored procedural skills."""

    def __init__(self, skills_dir: Path | str = "~/.vector/skills/") -> None:
        self._skills_dir = Path(skills_dir).expanduser()

    def _resolve_skill_path(self, name: str) -> Optional[Path]:
        """Resolve *name* to a `.toml` path confined to the skills dir.

        Returns ``None`` if *name* is empty or the resolved path would
        escape ``self._skills_dir`` (path traversal via ``..``, an
        embedded path separator, or an absolute override).
        """
        if not name:
            return None
        root = self._skills_dir.resolve()
        candidate = (self._skills_dir / f"{name}.toml").resolve()
        if candidate.parent != root:
            return None
        return candidate

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="skill_manage",
            description="Create, list, load, or delete agent-authored skills.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list", "load", "delete"],
                        "description": "Action to perform.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Skill name (for create/load/delete).",
                    },
                    "description": {
                        "type": "string",
                        "description": "Skill description (for create).",
                    },
                    "steps": {
                        "type": "array",
                        "description": (
                            "List of step dicts with tool_name and optional"
                            " arguments_template (for create)."
                        ),
                    },
                },
                "required": ["action"],
            },
            category="skill",
        )

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action", "list")
        name = params.get("name", "")
        if action == "create":
            return self._create(
                name, params.get("description", ""), params.get("steps", [])
            )
        elif action == "list":
            return self._list()
        elif action == "load":
            return self._load(name)
        elif action == "delete":
            return self._delete(name)
        return ToolResult(
            tool_name=self.spec.name,
            success=False,
            content=f"Unknown action: {action}",
        )

    def _create(self, name: str, description: str, steps: List[dict]) -> ToolResult:
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        path = self._resolve_skill_path(name)
        if path is None:
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content="Skill name is required and must not contain path separators.",
            )
        lines = [
            "[skill]",
            f"name = {_toml_string(name)}",
            f"description = {_toml_string(description)}",
            "",
        ]
        for step in steps:
            lines.append("[[skill.steps]]")
            lines.append(f"tool_name = {_toml_string(step.get('tool_name', ''))}")
            if "arguments_template" in step:
                lines.append(
                    f"arguments_template = {_toml_string(step['arguments_template'])}"
                )
            if "output_key" in step:
                lines.append(f"output_key = {_toml_string(step['output_key'])}")
            lines.append("")
        content = "\n".join(lines)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Created skill: {name}",
        )

    def _list(self) -> ToolResult:
        if not self._skills_dir.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="No skills directory found.",
            )
        skills = []
        for f in sorted(self._skills_dir.glob("*.toml")):
            skills.append(f.stem)
        if not skills:
            return ToolResult(
                tool_name=self.spec.name,
                success=True,
                content="No skills found.",
            )
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content="Available skills:\n" + "\n".join(f"- {s}" for s in skills),
        )

    def _load(self, name: str) -> ToolResult:
        path = self._resolve_skill_path(name)
        if path is None or not path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Skill not found: {name}",
            )
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=path.read_text(encoding="utf-8"),
        )

    def _delete(self, name: str) -> ToolResult:
        path = self._resolve_skill_path(name)
        if path is None or not path.exists():
            return ToolResult(
                tool_name=self.spec.name,
                success=False,
                content=f"Skill not found: {name}",
            )
        path.unlink()
        return ToolResult(
            tool_name=self.spec.name,
            success=True,
            content=f"Deleted skill: {name}",
        )
