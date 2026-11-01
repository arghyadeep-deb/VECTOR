import sys

__all__ = [
    "ConversationManager",
    "ConversationState",
]

import time

from loguru import logger

from core.config import CONFIG


_IDLE = "IDLE"
_LISTENING = "LISTENING"
_USER_SPEAKING = "USER_SPEAKING"
_PROCESSING = "PROCESSING"
_VECTOR_SPEAKING = "VECTOR_SPEAKING"
_INTERRUPTED = "INTERRUPTED"

_VALID_TRANSITIONS = {
    _IDLE: {_LISTENING},
    _LISTENING: {_USER_SPEAKING, _INTERRUPTED, _IDLE},
    _USER_SPEAKING: {_PROCESSING, _LISTENING, _INTERRUPTED, _IDLE},
    _PROCESSING: {_LISTENING, _VECTOR_SPEAKING, _INTERRUPTED, _IDLE},
    _VECTOR_SPEAKING: {_LISTENING, _INTERRUPTED, _IDLE},
    _INTERRUPTED: {_LISTENING, _IDLE},
}


class ConversationState:
    def __init__(self, state: str):
        self.state = state

    def __eq__(self, other):
        if isinstance(other, ConversationState):
            return self.state == other.state
        return self.state == other

    def __str__(self):
        return self.state

    def __repr__(self):
        return f"ConversationState({self.state})"


class ConversationManager:
    def __init__(self):
        voice_cfg = CONFIG.get("voice", {})
        self._timeout_sec = voice_cfg.get("conversation_timeout_sec", 30)
        self._state = ConversationState(_IDLE)
        self._callbacks: list[callable] = []
        self._session_id: str | None = None
        self._user_id: str | None = None
        self._session_start: float | None = None
        self._last_activity: float = time.monotonic()

    @property
    def current_state(self) -> ConversationState:
        return self._state

    @property
    def session_active(self) -> bool:
        return self._session_id is not None

    def transition(self, new_state: str) -> bool:
        current = self._state.state
        if new_state not in _VALID_TRANSITIONS.get(current, set()):
            logger.warning(f"[VECTOR][conversation] invalid transition: {current} -> {new_state}")
            return False
        old = self._state.state
        self._state = ConversationState(new_state)
        self._last_activity = time.monotonic()
        logger.info(f"[VECTOR][conversation] {old} -> {new_state}")
        self._notify(old, new_state)
        return True

    def on_transition(self, callback: callable) -> None:
        self._callbacks.append(callback)

    def _notify(self, old_state: str, new_state: str) -> None:
        for cb in self._callbacks:
            try:
                cb(old_state, new_state)
            except Exception as e:
                logger.debug(f"[VECTOR][conversation] callback error: {e}")

    def start_session(self, user_id: str) -> bool:
        if self.session_active:
            logger.warning("[VECTOR][conversation] session already active")
            return False
        self._session_id = f"session_{int(time.time())}"
        self._user_id = user_id
        self._session_start = time.monotonic()
        self._last_activity = time.monotonic()
        self._state = ConversationState(_IDLE)
        logger.info(f"[VECTOR][conversation] session started: {self._session_id} (user={user_id})")
        return True

    def end_session(self) -> None:
        if self._session_id:
            dur = time.monotonic() - (self._session_start or time.monotonic())
            logger.info(f"[VECTOR][conversation] session ended (duration={dur:.1f}s)")
            # Persist session metadata so future sessions know context was active
            try:
                from core.memory.episodic import EpisodicMemory
                EpisodicMemory().store(
                    event_type="conversation_session",
                    content=f"session={self._session_id} user={self._user_id} duration={dur:.0f}s",
                    tags=["session", "conversation"],
                    source="conversation_manager",
                )
            except Exception as _e:
                logger.debug("[VECTOR][conversation] session persist failed: {}", _e)
        self._session_id = None
        self._user_id = None
        self._session_start = None
        self._state = ConversationState(_IDLE)

    def last_session_id(self) -> str | None:
        """Return the session_id of the most recent completed session from episodic memory."""
        try:
            from core.memory.episodic import EpisodicMemory
            events = EpisodicMemory().recall(
                query="conversation_session", event_type="conversation_session", limit=1
            )
            if events:
                content = events[0].get("content", "")
                for part in content.split():
                    if part.startswith("session="):
                        return part.split("=", 1)[1]
        except Exception:
            logger.warning("[VECTOR] silent swallow")
            pass
        return None

    def interrupt(self) -> None:
        if self._state.state == _VECTOR_SPEAKING:
            self.transition(_INTERRUPTED)
            logger.info("[VECTOR][conversation] VECTOR_SPEAKING interrupted")
        else:
            logger.debug(f"[VECTOR][conversation] interrupt ignored in state {self._state}")

    def has_timed_out(self) -> bool:
        if not self.session_active:
            return False
        return (time.monotonic() - self._last_activity) > self._timeout_sec

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def user_id(self) -> str | None:
        return self._user_id

    def session_elapsed(self) -> float:
        if self._session_start is None:
            return 0.0
        return time.monotonic() - self._session_start


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    mgr = ConversationManager()
    mgr.start_session("test_user")
    mgr.transition("LISTENING")
    mgr.transition("USER_SPEAKING")
    mgr.transition("PROCESSING")
    mgr.transition("VECTOR_SPEAKING")
    mgr.interrupt()
    mgr.transition("IDLE")
    mgr.end_session()
    print(f"\u2705 conversation_manager OK (state={mgr.current_state})")
