"""VECTOR agent stub types."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class AgentContext:
    session_id: str = ""
    model: str = ""
    tools: List[Any] = field(default_factory=list)
    memory: Optional[Any] = None
    config: Optional[Any] = None

@dataclass
class AgentResult:
    success: bool = True
    output: Any = None
    error: str = ""
    tokens_used: int = 0

@dataclass
class AgentDeps:
    config: Any = None
    bus: Any = None
    engine: Any = None
    model: str = ""
    agent_name: str = ""
    tools: List[Any] = field(default_factory=list)
    memory_backend: Optional[Any] = None

class BaseAgent:
    """Abstract agent base."""
    def __init__(self, deps: Optional[AgentDeps] = None) -> None:
        self.deps = deps
