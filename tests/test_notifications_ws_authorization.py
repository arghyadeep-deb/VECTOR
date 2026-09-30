"""Regression test for core/api/routers/notifications.py's missing WebSocket
authentication (same bug class as RR-3.7C, tests/test_rr3_7c_voice_authorization.py
-- see that file's docstring for the full root-cause history: Starlette's
regular HTTP auth_middleware never covers WebSocket upgrade requests, so
every websocket endpoint must call require_auth_handshake() explicitly).
voice_ws.py and websocket.py already do this correctly; notifications.py's
/notifications/ws did not, so any network client could connect with zero
authentication and receive a live feed of VECTOR's internal hypothesis-
engine output (proactive insights about the owner), plus the 3 most recent
pending hypotheses pushed immediately on connect.

Found by a Claude self-fork's deep-verify pass on core/api/routers/ batch 1
(Phase 3 whole-repo audit, 2026-09-30).

Per the same reasoning test_rr3_7c_voice_authorization.py documents, a live
WebSocket-transport test is not the reliable choice here -- a pure
source-level check on ordering is used instead.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_hypothesis_websocket_calls_require_auth_handshake():
    import core.api.routers.notifications as notifications
    src = inspect.getsource(notifications.hypothesis_websocket)
    assert "require_auth_handshake" in src


def test_hypothesis_websocket_auth_runs_before_any_hypothesis_data_sent():
    """auth must run after ws.accept() (a WebSocket handshake ack is not a
    security boundary) but strictly before the event-bus subscription or the
    initial pending-hypotheses push -- either of which would leak real
    hypothesis content to an unauthenticated client."""
    import core.api.routers.notifications as notifications
    src = inspect.getsource(notifications.hypothesis_websocket)
    accept_idx = src.index("ws.accept()")
    # search from accept_idx onward: the docstring above the code also
    # mentions "require_auth_handshake" by name, which would otherwise be
    # found first and falsely satisfy an ordering check against the docstring
    # text rather than the actual call.
    auth_idx = src.index("require_auth_handshake", accept_idx)
    bus_idx = src.index("get_event_bus", auth_idx)
    assert accept_idx < auth_idx < bus_idx, (
        "auth handshake must run after accept() but strictly before the "
        "event bus subscription / initial hypothesis push"
    )


def test_hypothesis_websocket_reuses_canonical_handshake_not_a_new_mechanism():
    """Must import the same require_auth_handshake() /ws/command and
    voice_ws.py already use -- not a notifications-specific reimplementation."""
    import core.api.routers.notifications as notifications
    import core.api.routers.websocket as websocket_module
    src = inspect.getsource(notifications)
    assert "from core.api.routers.websocket import require_auth_handshake" in src
    assert callable(websocket_module.require_auth_handshake)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
