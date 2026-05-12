import sys
import json
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from core.config import CONFIG

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

_VALID_MODES = {"repl", "auto", "hybrid", "cautious", "standard", "autonomous", "read-only"}

@dataclass
class TokenUsage:
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, prompt: int = 0, completion: int = 0, cache_read: int = 0) -> None:
        self.prompt_tokens     += prompt
        self.completion_tokens += completion
        self.cache_read_tokens += cache_read


@dataclass
class VectorCodeSession:
    """Singleton session state shared across all VectorCode agents."""

    mode: str = "repl"
    task_id: Optional[str] = None
    repo_path: str = str(Path(__file__).parent.parent.parent.parent.parent)
    history: list = field(default_factory=list)
    active_agents: list = field(default_factory=list)
    current_model: str = "vector-fast"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Session tracking (spec §13)
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    files_modified: list = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    tool_calls: list = field(default_factory=list)

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
        self.files_modified = []
        self.token_usage = TokenUsage()
        self.cost_usd = 0.0
        self.tool_calls = []
        logger.info("[VECTOR][session] Session reset — history and active_agents cleared")

    def set_mode(self, mode: str) -> None:
        """Validate and set the session mode."""
        if mode not in _VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of: {_VALID_MODES}")
        self.mode = mode
        logger.info(f"[VECTOR][session] Mode set to '{mode}'")

    def record_token_usage(self, prompt: int = 0, completion: int = 0,
                           cache_read: int = 0, cost_usd: float = 0.0) -> None:
        self.token_usage.add(prompt, completion, cache_read)
        self.cost_usd += cost_usd

    def record_file_modified(self, path: str) -> None:
        if path not in self.files_modified:
            self.files_modified.append(path)

    def to_dict(self) -> dict:
        """Spec §13 session JSON format."""
        return {
            "id":             self.session_id,
            "created_at":     self.started_at.isoformat(),
            "model":          self.current_model,
            "project":        self.repo_path,
            "messages":       self.history,
            "tool_calls":     self.tool_calls,
            "files_modified": self.files_modified,
            "token_usage": {
                "input":      self.token_usage.prompt_tokens,
                "output":     self.token_usage.completion_tokens,
                "cache_read": self.token_usage.cache_read_tokens,
            },
            "cost_usd": round(self.cost_usd, 6),
        }

    def save(self, sessions_dir: Path) -> Path:
        """Persist session to .vector/sessions/<uuid>.json"""
        sessions_dir.mkdir(parents=True, exist_ok=True)
        path = sessions_dir / f"{self.session_id}.json"
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


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
