from pathlib import Path
from core.config import CONFIG

from typing import Any
from uuid import uuid4
from pydantic import BaseModel, field_validator
from loguru import logger


# ── Pydantic tool-call param models ──────────────────────────────────────────

class ReadFileParams(BaseModel):
    path: str

    @field_validator("path")
    @classmethod
    def path_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("path must not be empty")
        return v


class WriteFileParams(BaseModel):
    path: str
    content: str

    @field_validator("path")
    @classmethod
    def path_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("path must not be empty")
        return v


class EditFileParams(BaseModel):
    path: str
    old: str
    new: str

    @field_validator("path")
    @classmethod
    def path_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("path must not be empty")
        return v


class DeleteFileParams(BaseModel):
    path: str

    @field_validator("path")
    @classmethod
    def path_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("path must not be empty")
        return v


class BashRunParams(BaseModel):
    cmd: list
    timeout: int = 30

    @field_validator("cmd")
    @classmethod
    def cmd_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("cmd must not be empty")
        return v


class GrepParams(BaseModel):
    pattern: str
    glob_pattern: str = "**/*.py"

    @field_validator("pattern")
    @classmethod
    def pattern_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("pattern must not be empty")
        return v


# ── Tool registry ─────────────────────────────────────────────────────────────

_TOOL_MODELS: dict = {
    "read_file": ReadFileParams,
    "write_file": WriteFileParams,
    "edit_file": EditFileParams,
    "delete_file": DeleteFileParams,
    "bash_run": BashRunParams,
    "grep": GrepParams,
}


def _value_length(value: Any) -> int:
    """Return a non-sensitive size metric for validation audit logs."""
    try:
        return len(value)
    except TypeError:
        return len(str(value))


# ── PathValidator ─────────────────────────────────────────────────────────────

class PathValidator:
    """Validates that file paths stay within a designated repo root."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root: Path = Path(repo_root).resolve()

    def validate(self, path: str) -> str:
        """
        Resolve path relative to repo_root.
        Returns absolute path string.
        Raises PermissionError on directory traversal.
        """
        resolved = (self.repo_root / path).resolve()
        try:
            resolved.relative_to(self.repo_root)
        except ValueError:
            raise PermissionError(
                f"Path traversal blocked: '{path}' resolves to '{resolved}' "
                f"which is outside repo root '{self.repo_root}'"
            )
        # Use forward slashes so endswith("src/main.py") works cross-platform
        abs_str = resolved.as_posix()
        logger.debug(f"[VECTOR][validator] path validated: {abs_str}")
        return abs_str


# ── InputValidator ────────────────────────────────────────────────────────────

class InputValidator:
    """Validates tool call parameters using Pydantic models."""

    def validate_tool_call(self, tool: str, params: dict) -> dict:
        """
        Validate params for the named tool.
        Returns the validated (and possibly coerced) params dict.
        Raises ValueError on validation failure.
        Raises ValueError for unknown tool names.
        """
        model_cls = _TOOL_MODELS.get(tool)
        if model_cls is None:
            raise ValueError(f"Unknown tool: '{tool}'. Known tools: {list(_TOOL_MODELS.keys())}")
        try:
            validated = model_cls(**params)
        except Exception as exc:
            raise ValueError(f"Invalid params for tool '{tool}': {exc}") from exc
        result = validated.model_dump()
        field_names = sorted(result)
        fields = ",".join(field_names)
        lengths = ",".join(
            f"{field}:{_value_length(result[field])}" for field in field_names
        )
        logger.debug(
            "[VECTOR][validator] tool_call validated: "
            f"tool={tool} fields={fields} lengths={lengths} "
            f"correlation_id={uuid4().hex}"
        )
        return result


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        pv = PathValidator(repo_root=tmp)
        try:
            pv.validate("../secret")
            assert False, "Should have raised PermissionError"
        except PermissionError as _sve:
            logger.warning("[VECTOR][security.validator] suppressed PermissionError: %s", _sve)
        result = pv.validate("src/main.py")
        assert result.endswith("src/main.py"), f"Got: {result}"

    iv = InputValidator()
    result = iv.validate_tool_call("read_file", {"path": "src/main.py"})
    assert result["path"] == "src/main.py"
    try:
        iv.validate_tool_call("read_file", {"path": ""})
        assert False, "Should have raised ValueError"
    except ValueError as _sve:
        logger.debug("[VECTOR][security.validator] suppressed ValueError: %s", _sve)

    print("validator.py OK")


