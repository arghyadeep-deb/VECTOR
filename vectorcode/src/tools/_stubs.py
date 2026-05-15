"""VECTOR tool stub types."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class ToolResult:
    success: bool = True
    data: Any = None
    error: str = ""

@dataclass
class ToolSpec:
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)

class BaseTool:
    """Abstract tool base class."""
    name: str = "unknown"
    description: str = ""

    def run(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    async def arun(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError
