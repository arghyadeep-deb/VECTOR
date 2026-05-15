"""VECTOR session store."""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any
import json, time

class SessionStore:
    """Persistent session store backed by JSONL files."""

    def __init__(self, sessions_dir: Optional[Path] = None) -> None:
        self._dir = sessions_dir or (Path.home() / ".vector" / "sessions")
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, session_id: str, data: Dict[str, Any]) -> None:
        p = self._dir / f"{session_id}.json"
        p.write_text(json.dumps({**data, "_saved_at": time.time()}), encoding="utf-8")

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        p = self._dir / f"{session_id}.json"
        if not p.exists(): return None
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: return None

    def delete(self, session_id: str) -> None:
        p = self._dir / f"{session_id}.json"
        if p.exists(): p.unlink()

    def list_sessions(self) -> list[str]:
        return [p.stem for p in self._dir.glob("*.json")]
