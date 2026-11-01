"""
Disk-backed session persistence with crash recovery.

vectorcode's session.py is in-memory only — state is lost on process exit.
This module adds:
  - JSON session files under ~/.vector_ca/sessions/<id>.json
  - PID registration for crash detection
  - recover_crashed_sessions() — finds sessions whose PID no longer exists
  - Provider session IDs, model snapshots, compaction state per-session

Ported from the high-performance agent harness session.rs.
"""
from __future__ import annotations

__all__ = [
    "PersistedSession",
    "SessionPersistence",
    "StoredCompactionState",
]


import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

_SESSIONS_DIR = Path.home() / ".vector_ca" / "sessions"
_PIDS_DIR = Path.home() / ".vector_ca" / "active_pids"


def _sessions_dir() -> Path:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSIONS_DIR


def _pids_dir() -> Path:
    _PIDS_DIR.mkdir(parents=True, exist_ok=True)
    return _PIDS_DIR


# â”€â”€ Data structures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

COMPACT_WARNING_THRESHOLD = 0.80   # 80% context → warn
COMPACT_FORCE_THRESHOLD = 0.95     # 95% context → force compact


@dataclass
class StoredCompactionState:
    summary: str
    recent_tail: list[dict] = field(default_factory=list)
    compacted_at: str = ""

    def to_dict(self) -> dict:
        return {"summary": self.summary, "recent_tail": self.recent_tail,
                "compacted_at": self.compacted_at}

    @classmethod
    def from_dict(cls, d: dict) -> "StoredCompactionState":
        return cls(summary=d.get("summary", ""), recent_tail=d.get("recent_tail", []),
                   compacted_at=d.get("compacted_at", ""))

    def check_compact_needed(self, context_used: float, context_total: float) -> str:
        """Returns 'none', 'warn', or 'force' based on context usage."""
        if context_total == 0:
            return "none"
        ratio = context_used / context_total
        if ratio >= COMPACT_FORCE_THRESHOLD:
            logger.warning("[VECTOR][jcode] Context at {:.0%} — FORCING compact", ratio)
            return "force"
        elif ratio >= COMPACT_WARNING_THRESHOLD:
            logger.info("[VECTOR][jcode] Context at {:.0%} — suggest compact", ratio)
            return "warn"
        return "none"


@dataclass
class PersistedSession:
    id: str
    created_at: str
    updated_at: str
    messages: list[dict] = field(default_factory=list)

    title: str | None = None
    parent_id: str | None = None
    provider_session_id: str | None = None
    provider_key: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    subagent_model: str | None = None
    compaction: StoredCompactionState | None = None

    is_canary: bool = False
    testing_build: str | None = None
    working_dir: str | None = None
    short_name: str | None = None
    status: str = "active"
    last_pid: int | None = None
    last_active_at: str | None = None
    saved: bool = False
    save_label: str | None = None
    autoreview_enabled: bool | None = None
    token_usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "cache_read": 0})

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": self.messages,
            "status": self.status,
            "is_canary": self.is_canary,
            "saved": self.saved,
            "token_usage": self.token_usage,
        }
        for opt in ("title", "parent_id", "provider_session_id", "provider_key", "model",
                    "reasoning_effort", "subagent_model", "testing_build", "working_dir",
                    "short_name", "last_pid", "last_active_at", "save_label", "autoreview_enabled"):
            val = getattr(self, opt)
            if val is not None:
                d[opt] = val
        if self.compaction:
            d["compaction"] = self.compaction.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PersistedSession":
        comp_d = d.get("compaction")
        return cls(
            id=d["id"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            messages=d.get("messages", []),
            title=d.get("title"),
            parent_id=d.get("parent_id"),
            provider_session_id=d.get("provider_session_id"),
            provider_key=d.get("provider_key"),
            model=d.get("model"),
            reasoning_effort=d.get("reasoning_effort"),
            subagent_model=d.get("subagent_model"),
            compaction=StoredCompactionState.from_dict(comp_d) if comp_d else None,
            is_canary=d.get("is_canary", False),
            testing_build=d.get("testing_build"),
            working_dir=d.get("working_dir"),
            short_name=d.get("short_name"),
            status=d.get("status", "active"),
            last_pid=d.get("last_pid"),
            last_active_at=d.get("last_active_at"),
            saved=d.get("saved", False),
            save_label=d.get("save_label"),
            autoreview_enabled=d.get("autoreview_enabled"),
            token_usage=d.get("token_usage", {"input": 0, "output": 0, "cache_read": 0}),
        )


# â”€â”€ PID tracking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _register_pid(session_id: str) -> None:
    pid_file = _pids_dir() / f"{os.getpid()}.json"
    pid_file.write_text(json.dumps({"session_id": session_id, "pid": os.getpid()}))


def _unregister_pid() -> None:
    pid_file = _pids_dir() / f"{os.getpid()}.json"
    if pid_file.exists():
        pid_file.unlink()


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# â”€â”€ SessionPersistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class SessionPersistence:
    """
    Disk-backed session store with crash detection.

    Usage:
        store = SessionPersistence()
        session = store.create(model="qwen3:14b")
        session.messages.append({"role": "user", "content": "hello"})
        store.save(session)

        # On startup:
        crashed = store.recover_crashed_sessions()
        for s in crashed:
            logger.warning("Crashed session recovered: {}", s.id)
    """

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._dir = sessions_dir or _sessions_dir()
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def create(
        self,
        model: str | None = None,
        provider_key: str | None = None,
        working_dir: str | None = None,
        parent_id: str | None = None,
    ) -> PersistedSession:
        now = datetime.now(timezone.utc).isoformat()
        session = PersistedSession(
            id=str(uuid.uuid4()),
            created_at=now,
            updated_at=now,
            model=model,
            provider_key=provider_key,
            working_dir=working_dir or str(Path.cwd()),
            parent_id=parent_id,
            last_pid=os.getpid(),
            status="active",
        )
        self.save(session)
        _register_pid(session.id)
        logger.info("[VECTOR][session] created {} (model={})", session.id[:8], model)
        return session

    def save(self, session: PersistedSession) -> None:
        session.updated_at = datetime.now(timezone.utc).isoformat()
        session.last_pid = os.getpid()
        self._path(session.id).write_text(
            json.dumps(session.to_dict(), indent=2), encoding="utf-8"
        )

    def load(self, session_id: str) -> PersistedSession | None:
        p = self._path(session_id)
        if not p.exists():
            return None
        try:
            return PersistedSession.from_dict(json.loads(p.read_text()))
        except Exception as e:
            logger.error("[VECTOR][session] load failed {}: {}", session_id[:8], e)
            return None

    def close(self, session: PersistedSession, summary: str = "") -> None:
        session.status = "closed"
        if summary:
            session.title = summary[:80]
        self.save(session)
        _unregister_pid()
        logger.info("[VECTOR][session] closed {}", session.id[:8])

    def list_sessions(self) -> list[PersistedSession]:
        sessions = []
        for p in self._dir.glob("*.json"):
            try:
                s = PersistedSession.from_dict(json.loads(p.read_text()))
                sessions.append(s)
            except Exception as e:
                logger.warning("[VECTOR][session] skipping unreadable session file {}: {}", p.name, e)
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)

    def recover_crashed_sessions(self) -> list[PersistedSession]:
        """
        Find sessions whose last_pid no longer exists — crashed sessions.
        Marks them as 'crashed' and returns them for inspection.
        """
        crashed = []
        for s in self.list_sessions():
            if s.status != "active":
                continue
            pid = s.last_pid
            if pid and not _pid_is_alive(pid):
                logger.warning("[VECTOR][session] crashed session detected: {}", s.id[:8])
                s.status = "crashed"
                self.save(s)
                crashed.append(s)
        return crashed

    def append_message(self, session: PersistedSession, role: str, content: str) -> None:
        session.messages.append({
            "role": role,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    def set_compaction(self, session: PersistedSession, summary: str,
                       recent_tail: list[dict] | None = None) -> None:
        session.compaction = StoredCompactionState(
            summary=summary,
            recent_tail=recent_tail or [],
            compacted_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save(session)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        store = SessionPersistence(sessions_dir=Path(tmpdir))

        s = store.create(model="qwen3:14b", working_dir=tmpdir)
        store.append_message(s, "user", "hello VECTOR")
        store.append_message(s, "assistant", "Hello! How can I help?")
        store.save(s)

        loaded = store.load(s.id)
        assert loaded is not None
        assert len(loaded.messages) == 2
        assert loaded.model == "qwen3:14b"

        store.set_compaction(s, "User greeted VECTOR.")
        loaded2 = store.load(s.id)
        assert loaded2.compaction is not None
        assert "greeted" in loaded2.compaction.summary

        sessions = store.list_sessions()
        assert len(sessions) == 1

        crashed = store.recover_crashed_sessions()
        assert len(crashed) == 0

        store.close(s, summary="quick test session")

    print("OK session_persistence.py")
