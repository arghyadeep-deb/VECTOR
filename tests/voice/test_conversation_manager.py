import time
import pytest
from core.voice.conversation_manager import ConversationManager


def test_initial_state():
    mgr = ConversationManager()
    assert mgr.current_state == "IDLE"
    assert not mgr.session_active


def test_start_session():
    mgr = ConversationManager()
    assert mgr.start_session("test_user")
    assert mgr.session_active
    assert mgr.user_id == "test_user"
    assert mgr.session_id is not None


def test_end_session():
    mgr = ConversationManager()
    mgr.start_session("test_user")
    mgr.end_session()
    assert not mgr.session_active
    assert mgr.current_state == "IDLE"


def test_valid_transition_chain():
    mgr = ConversationManager()
    mgr.start_session("test_user")
    assert mgr.transition("LISTENING")
    assert mgr.transition("USER_SPEAKING")
    assert mgr.transition("PROCESSING")
    assert mgr.transition("VECTOR_SPEAKING")
    assert mgr.transition("LISTENING")
    assert mgr.current_state == "LISTENING"


def test_invalid_transition():
    mgr = ConversationManager()
    mgr.start_session("test_user")
    assert not mgr.transition("PROCESSING")
    assert mgr.current_state == "IDLE"


def test_invalid_from_idle():
    mgr = ConversationManager()
    assert not mgr.transition("VECTOR_SPEAKING")
    assert mgr.current_state == "IDLE"


def test_interrupt_during_vector_speaking():
    mgr = ConversationManager()
    mgr.start_session("test_user")
    mgr.transition("LISTENING")
    mgr.transition("USER_SPEAKING")
    mgr.transition("PROCESSING")
    mgr.transition("VECTOR_SPEAKING")
    mgr.interrupt()
    assert mgr.current_state == "INTERRUPTED"


def test_interrupt_ignored_in_idle():
    mgr = ConversationManager()
    mgr.interrupt()
    assert mgr.current_state == "IDLE"


def test_timeout():
    mgr = ConversationManager()
    mgr._timeout_sec = 0.01
    mgr.start_session("test_user")
    time.sleep(0.02)
    assert mgr.has_timed_out()


def test_no_timeout_within_period():
    mgr = ConversationManager()
    mgr._timeout_sec = 30
    mgr.start_session("test_user")
    assert not mgr.has_timed_out()


def test_on_transition_callback():
    mgr = ConversationManager()
    mgr.start_session("test_user")
    events = []
    mgr.on_transition(lambda old, new: events.append((old, new)))
    mgr.transition("LISTENING")
    assert len(events) == 1
    assert events[0] == ("IDLE", "LISTENING")


def test_duplicate_session_start():
    mgr = ConversationManager()
    assert mgr.start_session("test_user")
    assert not mgr.start_session("another_user")


def test_session_elapsed():
    mgr = ConversationManager()
    mgr.start_session("test_user")
    elapsed = mgr.session_elapsed()
    assert elapsed >= 0.0
