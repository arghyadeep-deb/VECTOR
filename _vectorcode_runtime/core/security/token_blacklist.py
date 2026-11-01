"""Token blacklist for JWT revocation.

Single-user system — stored in the main VECTOR SQLite DB (vector_memory.db)
alongside episodic memory. Uses a simple table:

    token_blacklist(jti TEXT PRIMARY KEY, revoked_at TEXT, expires_at TEXT)

A revoked refresh token cannot be used to mint new access tokens.
Access tokens are checked against the blacklist on every request.
Expired entries are pruned lazily (every 100 checks).

Design choices:
- SQLite over Redis: single-user local system, no external dependency
- jti (JWT ID) claim used as the key: each token has a unique ID
- Lazy expiration: avoids a background cleanup coroutine
- Thread-safe: uses the same get_db_connection pattern as episodic memory
"""

from __future__ import annotations

import sys

__all__ = [
    "TokenBlacklist",
    "get_blacklist",
]

import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.runtime_paths import data_path


_LOCK = threading.Lock()
_INSTANCE: TokenBlacklist | None = None


def _get_db_path() -> Path:
    """Token blacklist lives in its own DB to avoid coupling with the
    encrypted episodic memory DB (which requires SQLCipher + key setup).
    The blacklist has no sensitive data — just JWT IDs and timestamps."""
    path = data_path("token_blacklist.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class TokenBlacklist:
    """JWT token revocation store.

    Usage:
        bl = get_blacklist()
        bl.revoke(jti="abc123", expires_at=1700000000)
        if bl.is_revoked("abc123"):
            raise AuthError("token revoked")
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or _get_db_path()
        self._check_count = 0
        self._init_db()

    def _init_db(self) -> None:
        """Create the blacklist table if it doesn't exist."""
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_blacklist (
                    jti TEXT PRIMARY KEY,
                    revoked_at TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    token_type TEXT NOT NULL DEFAULT 'refresh',
                    reason TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_blacklist_expires
                ON token_blacklist(expires_at)
            """)
            conn.commit()
            conn.close()
            logger.info("[VECTOR][auth] token blacklist initialized at {}", self._db_path)
        except Exception as e:
            logger.error("[VECTOR][auth] token blacklist init failed: {}", e)
            raise

    def revoke(
        self,
        jti: str,
        expires_at: int,
        token_type: str = "refresh",
        reason: str = "",
    ) -> None:
        """Add a token to the blacklist.

        Args:
            jti: JWT ID (unique token identifier)
            expires_at: Unix timestamp when the token would have expired
            token_type: 'access' or 'refresh'
            reason: Optional reason for revocation (e.g., 'logout', 'compromised')
        """
        if not jti:
            raise ValueError("jti is required")
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                """INSERT OR REPLACE INTO token_blacklist
                   (jti, revoked_at, expires_at, token_type, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (jti, now, expires_at, token_type, reason),
            )
            conn.commit()
            conn.close()
            logger.info(
                "[VECTOR][auth] token revoked: jti={} type={} reason={}",
                jti[:12], token_type, reason or "none",
            )
        except Exception as e:
            logger.error("[VECTOR][auth] revoke failed: {}", e)
            raise

    def is_revoked(self, jti: str) -> bool:
        """Check if a token is revoked. Lazy-prunes expired entries every 100 checks."""
        if not jti:
            return False
        now_ts = int(datetime.now(timezone.utc).timestamp())
        try:
            conn = sqlite3.connect(str(self._db_path))
            row = conn.execute(
                "SELECT 1 FROM token_blacklist WHERE jti = ? AND expires_at > ?",
                (jti, now_ts),
            ).fetchone()
            conn.close()

            # Lazy expiration pruning
            self._check_count += 1
            if self._check_count >= 100:
                self._prune_expired()
                self._check_count = 0

            return row is not None
        except Exception as e:
            logger.warning("[VECTOR][auth] is_revoked check failed: {}", e)
            return False  # fail-open for availability; blacklist is defense-in-depth

    def _prune_expired(self) -> None:
        """Remove expired entries from the blacklist."""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.execute(
                "DELETE FROM token_blacklist WHERE expires_at <= ?", (now_ts,)
            )
            conn.commit()
            if cursor.rowcount > 0:
                logger.debug("[VECTOR][auth] pruned {} expired blacklist entries", cursor.rowcount)
            conn.close()
        except Exception as e:
            logger.warning("[VECTOR][auth] prune failed: {}", e)

    def revoke_all_sessions(self, reason: str = "revoke_all") -> int:
        """Revoke ALL active refresh tokens. Used when the owner wants to
        force-logout all devices. Adds a global revoke marker."""
        now = datetime.now(timezone.utc).isoformat()
        now_ts = int(datetime.now(timezone.utc).timestamp())
        # Far-future expiry ensures the marker outlives all tokens
        far_future = now_ts + (365 * 24 * 3600)
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                """INSERT OR REPLACE INTO token_blacklist
                   (jti, revoked_at, expires_at, token_type, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                ("__REVOKE_ALL__", now, far_future, "global", reason),
            )
            conn.commit()
            conn.close()
            logger.warning("[VECTOR][auth] ALL sessions revoked: {}", reason)
            return 1
        except Exception as e:
            logger.error("[VECTOR][auth] revoke_all failed: {}", e)
            return 0

    def is_globally_revoked(self) -> bool:
        """Check if a global revoke-all has been issued."""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        try:
            conn = sqlite3.connect(str(self._db_path))
            row = conn.execute(
                "SELECT 1 FROM token_blacklist WHERE jti = '__REVOKE_ALL__' AND expires_at > ?",
                (now_ts,),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def count_active(self) -> int:
        """Count non-expired entries in the blacklist."""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        try:
            conn = sqlite3.connect(str(self._db_path))
            row = conn.execute(
                "SELECT COUNT(*) FROM token_blacklist WHERE expires_at > ?",
                (now_ts,),
            ).fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0


def get_blacklist() -> TokenBlacklist:
    """Get or create the singleton blacklist instance."""
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                _INSTANCE = TokenBlacklist()
    return _INSTANCE


def generate_jti() -> str:
    """Generate a unique JWT ID (jti claim)."""
    return secrets.token_urlsafe(24)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    # Self-test with a temp DB
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        bl = TokenBlacklist(db_path=tmp_path)

        # Revoke and check
        bl.revoke("test-jti-1", expires_at=9999999999, token_type="refresh", reason="test")
        assert bl.is_revoked("test-jti-1"), "should be revoked"
        assert not bl.is_revoked("nonexistent-jti"), "should not be revoked"

        # Expired entry should not be found
        bl.revoke("expired-jti", expires_at=1, token_type="access")
        assert not bl.is_revoked("expired-jti"), "expired entry should not be found"

        # Global revoke
        bl.revoke_all_sessions(reason="test-revoke-all")
        assert bl.is_globally_revoked(), "should be globally revoked"

        # Count
        count = bl.count_active()
        assert count >= 2, f"expected at least 2 active entries, got {count}"

        # generate_jti
        jti = generate_jti()
        assert len(jti) > 20, "jti should be sufficiently random"

        print("✅ token_blacklist.py OK")
    finally:
        tmp_path.unlink(missing_ok=True)
