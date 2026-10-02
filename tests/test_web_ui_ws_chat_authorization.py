"""Regression test for core/ui/web_ui.py's missing WebSocket authentication
(same bug class as RR-3.7C / tests/test_notifications_ws_authorization.py --
Starlette's app.middleware("http")-registered auth_middleware never covers
WebSocket upgrade requests, so every websocket endpoint must call
require_auth_handshake() explicitly). voice_ws.py/websocket.py/notifications.py
already do this correctly; web_ui.py's /ui/ws/chat did not, so any network
client could connect with zero authentication, stream real LLM chat
responses (real inference cost, caller_id="web_ui_ws_chat"), and trigger an
episodic-memory write -- regardless of whether VECTOR_API_KEY was configured.

Found during the Phase 3 whole-repo audit's core/ui/ deep-verify slice,
2026-10-02.

Per the same reasoning test_notifications_ws_authorization.py documents, a
live WebSocket-transport test is not the reliable choice here -- a pure
source-level check on ordering is used instead.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_web_chat_ws_calls_require_auth_handshake():
    import core.ui.web_ui as web_ui
    src = inspect.getsource(web_ui.web_chat_ws)
    assert "require_auth_handshake" in src


def test_web_chat_ws_auth_runs_before_any_llm_call_or_memory_write():
    """auth must run after websocket.accept() (a WebSocket handshake ack is
    not a security boundary) but strictly before receive_json()/chat_stream()
    -- either of which would let an unauthenticated client drive a real LLM
    call or read back streamed tokens before being rejected."""
    import core.ui.web_ui as web_ui
    src = inspect.getsource(web_ui.web_chat_ws)
    accept_idx = src.index("websocket.accept()")
    auth_idx = src.index("require_auth_handshake", accept_idx)
    receive_idx = src.index("receive_json", auth_idx)
    assert accept_idx < auth_idx < receive_idx, (
        "auth handshake must run after accept() but strictly before "
        "receive_json()/any LLM call"
    )


def test_web_chat_ws_reuses_canonical_handshake_not_a_new_mechanism():
    """Must import the same require_auth_handshake() voice_ws.py/
    notifications.py already use -- not a web_ui-specific reimplementation."""
    import core.ui.web_ui as web_ui
    import core.api.routers.websocket as websocket_module
    src = inspect.getsource(web_ui)
    assert "from core.api.routers.websocket import require_auth_handshake" in src
    assert callable(websocket_module.require_auth_handshake)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
