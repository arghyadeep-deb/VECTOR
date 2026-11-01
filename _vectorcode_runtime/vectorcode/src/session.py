import sys
import hashlib
import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from loguru import logger
from vectorcode.src.utils import atomic_json_write

_VALID_MODES = {"repl", "auto", "hybrid", "cautious", "standard", "autonomous", "read-only"}
MAX_ROLLBACK_BYTES = 1024 * 1024
_scoped_session = ContextVar("vectorcode_session", default=None)


def file_fingerprint(path: Path) -> dict:
    """Return a bounded fingerprint suitable for validating a rollback target."""
    if not path.exists() or not path.is_file():
        return {"exists": False, "sha256": ""}
    if path.stat().st_size > MAX_ROLLBACK_BYTES:
        return {"exists": True, "sha256": "too-large"}
    return {"exists": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

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
    repo_path: str = str(Path(__file__).parent.parent.parent.parent)
    history: list = field(default_factory=list)
    active_agents: list = field(default_factory=list)
    current_model: str = "vector-focus"
    display_title: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Session tracking (spec §13)
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    files_modified: list = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    cost_usd: float = 0.0
    tool_calls: list = field(default_factory=list)
    local_images: bool = False

    _instance: "Optional[VectorCodeSession]" = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def get(cls) -> "VectorCodeSession":
        """Return the singleton instance, creating it on first call."""
        scoped = _scoped_session.get()
        if scoped is not None:
            return scoped
        if not hasattr(cls, "_singleton") or cls._singleton is None:
            cls._singleton = cls()
            logger.info(f"[VECTOR][session] VectorCodeSession created — mode={cls._singleton.mode}")
        return cls._singleton

    @classmethod
    @contextmanager
    def scope(cls, session: "VectorCodeSession"):
        """Use a task-local session, restoring the caller's session on exit."""
        token = _scoped_session.set(session)
        try:
            yield session
        finally:
            _scoped_session.reset(token)

    def reset(self) -> None:
        """Clear history and active_agents, preserve mode and repo_path."""
        self.history = []
        self.active_agents = []
        self.task_id = None
        self.display_title = None
        self.files_modified = []
        self.token_usage = TokenUsage()
        self.cost_usd = 0.0
        self.tool_calls = []
        self.local_images = False
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
            "title":          self.display_title or "",
            "project":        self.repo_path,
            "messages":       self.history,
            "tool_calls":     [
                {key: value for key, value in call.items() if key != "rollback"}
                for call in self.tool_calls
                if isinstance(call, dict)
            ],
            "files_modified": self.files_modified,
            "token_usage": {
                "input":      self.token_usage.prompt_tokens,
                "output":     self.token_usage.completion_tokens,
                "cache_read": self.token_usage.cache_read_tokens,
            },
            "cost_usd": round(self.cost_usd, 6),
            "local_images": self.local_images,
        }

    def save(self, sessions_dir: Path) -> Path:
        """Persist session to .vector/sessions/<uuid>.json"""
        sessions_dir.mkdir(parents=True, exist_ok=True)
        path = sessions_dir / f"{self.session_id}.json"
        atomic_json_write(path, self.to_dict())
        return path


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = VectorCodeSession.get()
    b = VectorCodeSession.get()
    assert a is b, "Singleton broken — two different instances returned"
    assert hasattr(a, "session_id") and len(a.session_id) == 36
    assert hasattr(a, "token_usage")
    assert hasattr(a, "files_modified")
    assert hasattr(a, "cost_usd")
    a.set_mode("auto")
    assert a.mode == "auto"
    a.record_token_usage(prompt=100, completion=50, cost_usd=0.001)
    assert a.token_usage.prompt_tokens == 100
    assert abs(a.cost_usd - 0.001) < 1e-9
    a.record_file_modified("src/main.py")
    assert "src/main.py" in a.files_modified
    d = a.to_dict()
    assert "id" in d and "token_usage" in d and "files_modified" in d
    a.reset()
    assert a.history == [] and a.cost_usd == 0.0
    print("session.py OK")


