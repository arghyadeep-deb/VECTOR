# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""EditApplier ABC, registry, and context types for the execute phase.

Each concrete applier implements validate/apply/rollback for a single EditOp.
Appliers are registered in an EditApplierRegistry keyed by EditOp.

See spec §7.1.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from vectorcode.src.learning.distillation.models import Edit, EditOp


_BARE_TOML_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def format_toml_key(value: object) -> str:
    """Format an untrusted key or dotted-key segment without TOML injection."""
    text = str(value)
    return text if _BARE_TOML_KEY.fullmatch(text) else json.dumps(text, ensure_ascii=False)


def format_toml_value(value: object) -> str:
    """Serialize the scalar/list values accepted in model-generated edits."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(format_toml_value(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML value type: {type(value).__name__}")

@dataclass
class ApplyContext:
    """Shared context passed to all appliers."""

    vector_home: Path
    session_id: str

    @property
    def config_path(self) -> Path:
        return self.vector_home / "config.toml"

    @property
    def agents_dir(self) -> Path:
        return self.vector_home / "agents"

    @property
    def tools_dir(self) -> Path:
        return self.vector_home / "tools"

@dataclass
class ValidationResult:
    """Result of EditApplier.validate()."""

    ok: bool
    reason: str = ""

@dataclass
class ApplyResult:
    """Result of EditApplier.apply()."""

    changed_files: list[str] = field(default_factory=list)

class EditApplier(ABC):
    """Abstract base for edit appliers.

    Each subclass handles one EditOp. It validates the edit against
    the current config state, applies the mutation, and can roll back.
    """

    op: ClassVar[EditOp]

    @abstractmethod
    def validate(self, edit: Edit, ctx: ApplyContext) -> ValidationResult:
        """Check if the edit can be applied to the current config."""
        ...

    @abstractmethod
    def apply(self, edit: Edit, ctx: ApplyContext) -> ApplyResult:
        """Mutate the config. Must be idempotent."""
        ...

    @abstractmethod
    def rollback(self, edit: Edit, ctx: ApplyContext) -> None:
        """Restore pre-edit state. Most appliers delegate to git checkout."""
        ...

class EditApplierRegistry:
    """Registry of EditApplier instances keyed by EditOp."""

    def __init__(self) -> None:
        self._appliers: dict[EditOp, EditApplier] = {}

    def register(self, applier: EditApplier) -> None:
        """Register an applier instance."""
        self._appliers[applier.op] = applier

    def get(self, op: EditOp) -> EditApplier:
        """Return the applier for the given op. Raises KeyError if not found."""
        return self._appliers[op]

    def is_supported(self, op: EditOp) -> bool:
        """Return True if an applier is registered for the op."""
        return op in self._appliers
