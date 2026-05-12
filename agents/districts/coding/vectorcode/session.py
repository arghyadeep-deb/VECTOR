import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from core.config import CONFIG

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from loguru import logger

_VALID_MODES = {"repl", "auto", "hybrid"}

@dataclass
class VectorCodeSession:
    """Singleton session state shared across all VectorCode agents."""

    mode: str = "repl"
    task_id: Optional[str] = None
    repo_path: str = str(Path(__file__).parent.parent.parent.parent.parent)
    history: list = field(default_factory=list)
    active_agents: list = field(default_factory=list)
    current_model: str = "vector-fast"
    started_at: datetime = field(default_factory=datetime.now)

    _instance: "Optional[VectorCodeSession]" = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def get(cls) -> "VectorCodeSession":
        """Return the singleton instance, creating it on first call."""
        if not hasattr(cls, "_singleton") or cls._singleton is None:
            cls._singleton = cls()
            logger.info(f"[VECTOR][session] VectorCodeSession created — mode={cls._singleton.mode}")
        return cls._singleton

    def reset(self) -> None:
        """Clear history and active_agents, preserve mode and repo_path."""
        self.history = []
        self.active_agents = []
        self.task_id = None
        logger.info("[VECTOR][session] Session reset — history and active_agents cleared")

    def set_mode(self, mode: str) -> None:
        """Validate and set the session mode."""
        if mode not in _VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of: {_VALID_MODES}")
        self.mode = mode
        logger.info(f"[VECTOR][session] Mode set to '{mode}'")


if __name__ == "__main__":
    a = VectorCodeSession.get()
    b = VectorCodeSession.get()
    assert a is b, "Singleton broken — two different instances returned"
    assert hasattr(a, "mode")
    assert hasattr(a, "task_id")
    assert hasattr(a, "repo_path")
    assert hasattr(a, "history")
    assert hasattr(a, "active_agents")
    assert hasattr(a, "current_model")
    a.set_mode("auto")
    assert a.mode == "auto"
    a.reset()
    assert a.history == []
    print("session.py OK")
