"""VECTOR session store."""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any
import json, re, time

from loguru import logger

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

class SessionStore:
    """Persistent session store backed by JSONL files."""

    def __init__(self, sessions_dir: Optional[Path] = None) -> None:
        self._dir = sessions_dir or (Path.home() / ".vector" / "sessions")
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, session_id: str) -> Path:
        if not _SESSION_ID_RE.fullmatch(session_id):
            raise ValueError("Invalid session_id: expected 1-128 URL-safe characters")
        return self._dir / f"{session_id}.json"

    def save(self, session_id: str, data: Dict[str, Any]) -> None:
        p = self._path_for(session_id)
        p.write_text(json.dumps({**data, "_saved_at": time.time()}), encoding="utf-8")

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        p = self._path_for(session_id)
        if not p.exists(): return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.error("[VECTOR][sessions] corrupt session file {}: {}", p, exc)
            raise ValueError(f"Session data is corrupt: {session_id}") from exc

    def delete(self, session_id: str) -> None:
        p = self._path_for(session_id)
        if p.exists(): p.unlink()

    def list_sessions(self) -> list[str]:
        return [p.stem for p in self._dir.glob("*.json")]
