# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

from __future__ import annotations

from typing import Any, Optional

class GatewayDaemon:
    """Composes channels, sessions, agents, and scheduler into a daemon."""

    def __init__(
        self,
        config: Any = None,
        session_store: Any = None,
        agent_manager: Any = None,
        agent_scheduler: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._config = config
        self._session_store = session_store
        self._agent_manager = agent_manager
        self._agent_scheduler = agent_scheduler
        self._event_bus = event_bus
        self._running = False

    @staticmethod
    def session_key(
        platform: str,
        chat_type: str,
        chat_id: str,
        thread_id: Optional[str],
    ) -> str:
        # thread_id is optional -- when absent, the key must omit that
        # segment entirely, not embed the literal string "None". Matches
        # the canonical key format already used by the live gateway
        # (vectorcode/src/gateway/session.py's session-key builder).
        if thread_id:
            return f"agent:main:{platform}:{chat_type}:{chat_id}:{thread_id}"
        return f"agent:main:{platform}:{chat_type}:{chat_id}"

    def start(self) -> None:
        """Start the daemon (foreground)."""
        self._running = True

    def stop(self) -> None:
        """Stop the daemon."""
        self._running = False
