"""
SessionManager — cross-platform conversation session state for VectorCode.

Each (platform, chat_id) pair gets its own isolated PlatformSession with
a bounded conversation history.  Sessions expire after SESSION_TTL seconds
of inactivity (default 3600 s / 1 hour).  The manager is thread-safe and
caps total active sessions at MAX_SESSIONS using LRU eviction.
"""
import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

# Maximum conversation turns kept per session (oldest entries are trimmed)
_MAX_HISTORY_PER_SESSION = 200

# ── PlatformSession ───────────────────────────────────────────────────────────

@dataclass
class PlatformSession:
    """
    Conversation state for a single (platform, chat_id) pair.

    Fields:
        session_id   — unique UUID-based identifier
        platform     — originating platform (telegram, discord, slack, …)
        user_id      — platform-specific sender identifier
        chat_id      — platform channel / conversation ID
        history      — list of {role, content, ts} dicts (bounded)
        created_at   — Unix timestamp of session creation
        last_active  — Unix timestamp of most recent activity
        metadata     — arbitrary key-value store for callers
    """
    session_id:  str        = field(default_factory=lambda: str(uuid.uuid4())[:16])
    platform:    str        = ""
    user_id:     str        = ""
    chat_id:     str        = ""
    history:     list       = field(default_factory=list)  # list[dict]
    created_at:  float      = field(default_factory=time.time)
    last_active: float      = field(default_factory=time.time)
    metadata:    dict       = field(default_factory=dict)

    def _touch(self) -> None:
        """Update last_active to now."""
        self.last_active = time.time()

    def to_dict(self) -> dict:
        """Return a metadata-only summary (excludes full history for efficiency)."""
        return {
            "session_id":   self.session_id,
            "platform":     self.platform,
            "user_id":      self.user_id,
            "chat_id":      self.chat_id,
            "history_len":  len(self.history),
            "created_at":   self.created_at,
            "last_active":  self.last_active,
            "metadata":     dict(self.metadata),
        }

# ── SessionManager ────────────────────────────────────────────────────────────

class SessionManager:
    """
    Thread-safe session manager for multi-platform VectorCode deployments.

    Each (platform, chat_id) pair gets its own isolated conversation history.
    Sessions expire after SESSION_TTL seconds of inactivity (default: 3600).
    Total sessions are capped at MAX_SESSIONS; oldest inactive session is
    evicted when the cap is reached (LRU policy).
    """

    SESSION_TTL   = 3600   # seconds of inactivity before expiry
    MAX_SESSIONS  = 1000   # maximum concurrent sessions
    MAX_HISTORY   = _MAX_HISTORY_PER_SESSION

    def __init__(self) -> None:
        # Primary index: session_id -> PlatformSession
        self._sessions:  dict[str, PlatformSession] = {}
        # Lookup: (platform, chat_id) -> session_id
        self._key_index: dict[tuple, str]           = {}
        self._lock = threading.RLock()
        logger.debug("[VECTOR][session_mgr] SessionManager initialised")

    # ── Session retrieval / creation ──────────────────────────────────────────

    def get_or_create(
        self,
        platform: str,
        user_id: str,
        chat_id: str = "",
    ) -> PlatformSession:
        """
        Return the existing active session for (platform, chat_id) or create one.
        Uses chat_id as the primary key; falls back to user_id when chat_id is empty.
        """
        key_chat = chat_id or user_id
        index_key = (platform.lower(), key_chat)

        with self._lock:
            # Return existing if present and not expired
            existing_id = self._key_index.get(index_key)
            if existing_id and existing_id in self._sessions:
                session = self._sessions[existing_id]
                if not self._is_expired(session):
                    session._touch()
                    return session
                else:
                    # Expired — clean it up
                    self._remove_session(existing_id)

            # Enforce session cap with LRU eviction
            if len(self._sessions) >= self.MAX_SESSIONS:
                self._evict_oldest()

            # Create new session
            session = PlatformSession(
                platform=platform.lower(),
                user_id=user_id,
                chat_id=key_chat,
            )
            self._sessions[session.session_id] = session
            self._key_index[index_key] = session.session_id
            logger.debug(
                f"[VECTOR][session_mgr] new session {session.session_id} "
                f"for {platform}/{key_chat}"
            )
            return session

    def get(self, session_id: str) -> Optional[PlatformSession]:
        """Return a session by its ID, or None if not found / expired."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if self._is_expired(session):
                self._remove_session(session_id)
                return None
            return session

    # ── History management ────────────────────────────────────────────────────

    def get_history(self, session_id: str) -> list:
        """Return the conversation history for session_id (may be empty)."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            if self._is_expired(session):
                self._remove_session(session_id)
                return []
            return list(session.history)

    def append_message(self, session_id: str, role: str, content: str) -> None:
        """
        Append a message turn to the session history.
        role: "user" | "assistant" | "system"
        Trims history to MAX_HISTORY entries after appending.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                logger.warning(f"[VECTOR][session_mgr] append to unknown session {session_id}")
                return
            if self._is_expired(session):
                self._remove_session(session_id)
                logger.warning(f"[VECTOR][session_mgr] append to expired session {session_id}")
                return
            session.history.append({"role": role, "content": content, "ts": time.time()})
            # Trim to keep only the most recent MAX_HISTORY turns
            if len(session.history) > self.MAX_HISTORY:
                session.history = session.history[-self.MAX_HISTORY:]
            session._touch()

    def clear(self, session_id: str) -> None:
        """Clear the history for a session (keeps session alive)."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.history = []
                session._touch()
                logger.debug(f"[VECTOR][session_mgr] cleared history for {session_id}")

    # ── Expiry / eviction ─────────────────────────────────────────────────────

    def expire_old(self) -> int:
        """Remove all expired sessions. Returns count of sessions removed."""
        with self._lock:
            expired_ids = [
                sid for sid, sess in self._sessions.items()
                if self._is_expired(sess)
            ]
            for sid in expired_ids:
                self._remove_session(sid)
            if expired_ids:
                logger.info(f"[VECTOR][session_mgr] expired {len(expired_ids)} sessions")
            return len(expired_ids)

    def _is_expired(self, session: PlatformSession) -> bool:
        return (time.time() - session.last_active) > self.SESSION_TTL

    def _evict_oldest(self) -> None:
        """Evict the session with the oldest last_active timestamp."""
        if not self._sessions:
            return
        oldest_id = min(self._sessions, key=lambda sid: self._sessions[sid].last_active)
        logger.debug(f"[VECTOR][session_mgr] evicting oldest session {oldest_id}")
        self._remove_session(oldest_id)

    def _remove_session(self, session_id: str) -> None:
        """Remove a session from both indexes (must be called under lock)."""
        session = self._sessions.pop(session_id, None)
        if session is not None:
            index_key = (session.platform, session.chat_id or session.user_id)
            self._key_index.pop(index_key, None)

    # ── Listing ───────────────────────────────────────────────────────────────

    def list_active(self) -> list:
        """
        Return metadata dicts for all non-expired active sessions.
        Triggers expiry check as a side-effect.
        """
        self.expire_old()
        with self._lock:
            return [sess.to_dict() for sess in self._sessions.values()]

    def count(self) -> int:
        """Return the number of currently tracked sessions (including potentially expired)."""
        with self._lock:
            return len(self._sessions)

    # ── Metadata helpers ──────────────────────────────────────────────────────

    def set_metadata(self, session_id: str, key: str, value: object) -> bool:
        """Set a metadata key on a session. Returns True on success."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            if self._is_expired(session):
                self._remove_session(session_id)
                return False
            session.metadata[key] = value
            session._touch()
            return True

    def get_metadata(self, session_id: str, key: str, default: object = None) -> object:
        """Retrieve a metadata value from a session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return default
            if self._is_expired(session):
                self._remove_session(session_id)
                return default
            return session.metadata.get(key, default)

# ── Module-level singleton ────────────────────────────────────────────────────

_manager: Optional[SessionManager] = None
_manager_lock = threading.Lock()

def get_session_manager() -> SessionManager:
    """Return the module-level SessionManager singleton (thread-safe)."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = SessionManager()
    return _manager

if __name__ == "__main__":
    import time as _time

    mgr = SessionManager()

    # get_or_create: new session
    s1 = mgr.get_or_create("telegram", "user123", "chat456")
    assert s1.platform == "telegram"
    assert s1.user_id == "user123"
    assert s1.chat_id == "chat456"
    assert s1.history == []
    print(f"Created session: {s1.session_id}")

    # get_or_create: same (platform, chat_id) returns same session
    s1_again = mgr.get_or_create("telegram", "user123", "chat456")
    assert s1.session_id == s1_again.session_id
    print("get_or_create idempotency OK")

    # append_message
    mgr.append_message(s1.session_id, "user", "hello VECTOR")
    mgr.append_message(s1.session_id, "assistant", "Hello! How can I help?")
    history = mgr.get_history(s1.session_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    print(f"History OK: {len(history)} turns")

    # clear
    mgr.clear(s1.session_id)
    assert mgr.get_history(s1.session_id) == []
    print("clear OK")

    # Different platforms/chats get separate sessions
    s2 = mgr.get_or_create("discord", "user999", "server-chan-1")
    assert s2.session_id != s1.session_id
    assert mgr.count() == 2
    print(f"Separate sessions: {mgr.count()} active")

    # list_active
    active = mgr.list_active()
    assert len(active) == 2
    assert all("session_id" in a for a in active)
    print(f"list_active OK: {len(active)} entries")

    # metadata
    mgr.set_metadata(s1.session_id, "preferred_language", "python")
    val = mgr.get_metadata(s1.session_id, "preferred_language")
    assert val == "python"
    print("metadata OK")

    # expire_old — set TTL to 0 to force expiry of s2
    mgr.SESSION_TTL = 0
    _time.sleep(0.01)
    expired = mgr.expire_old()
    assert expired >= 1
    print(f"expire_old OK: {expired} expired")
    mgr.SESSION_TTL = SessionManager.SESSION_TTL  # restore default

    # singleton
    m1 = get_session_manager()
    m2 = get_session_manager()
    assert m1 is m2
    print("singleton OK")

    # History trim at MAX_HISTORY
    mgr2 = SessionManager()
    s3 = mgr2.get_or_create("slack", "bulk_user", "bulk_chat")
    for i in range(mgr2.MAX_HISTORY + 50):
        mgr2.append_message(s3.session_id, "user", f"message {i}")
    hist = mgr2.get_history(s3.session_id)
    assert len(hist) == mgr2.MAX_HISTORY, f"Expected {mgr2.MAX_HISTORY} got {len(hist)}"
    print(f"history trim OK: {len(hist)} entries kept")

    print("comms/session_manager.py OK — thread-safe, TTL expiry, LRU eviction, singleton")
