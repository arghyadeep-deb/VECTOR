"""
Closes docs/repo_analysis/_MASTER_TODO.md §3 item 11's remaining code gap:
core/control/node_status.py::ensure_node_awake() has no caller -- the seam
existed but nothing actually checked reachability before sending a WoL
packet. The REAL integration point isn't core/ at all: phone_node/
ambient_server.py is the deployed Termux node that's supposed to do this
("Termux should: send Wake-on-LAN... keep the heavy command queued/
deferred... wait for Legion heartbeat" per the original issue doc) -- and
it cannot import core/control/node_status.py (Termux has no VECTOR core
package installed, confirmed by ambient_server.py's own zero `from core`
imports). Same intentional duplication pattern as its own WoL sender
(_magic_packet) vs core/control/wake_on_lan.py.

This adds a self-contained reachability check (pure stdlib socket probe,
matching ambient_server.py's existing style) so wake_legion() skips
sending a redundant WoL packet when Legion is already awake.
"""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "phone_node"))


def test_legion_reachable_true_when_port_accepts_connection():
    import ambient_server

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        assert ambient_server._check_legion_reachable(host="127.0.0.1", port=port, timeout=1.0) is True
    finally:
        server.close()


def test_legion_reachable_false_when_port_refused():
    import ambient_server

    assert ambient_server._check_legion_reachable(host="127.0.0.1", port=1, timeout=0.5) is False


def test_legion_reachable_false_when_no_host_configured():
    import ambient_server

    assert ambient_server._check_legion_reachable(host="", port=8000) is False


def test_wake_legion_skips_packet_when_already_reachable(monkeypatch):
    import ambient_server

    monkeypatch.setattr(ambient_server, "LEGION_HOST", "127.0.0.1")
    monkeypatch.setattr(ambient_server, "_check_legion_reachable", lambda **kw: True)
    monkeypatch.setattr(ambient_server, "LEGION_WIFI_MAC", "AA:BB:CC:DD:EE:FF")

    sent = {"called": False}
    monkeypatch.setattr(ambient_server, "_magic_packet", lambda mac: sent.__setitem__("called", True) or b"")

    result = ambient_server.wake_legion(prefer="wifi")
    assert result["ok"] is True
    assert result["already_awake"] is True
    assert sent["called"] is False


def test_wake_legion_sends_packet_when_unreachable(monkeypatch):
    import ambient_server

    monkeypatch.setattr(ambient_server, "LEGION_HOST", "127.0.0.1")
    monkeypatch.setattr(ambient_server, "_check_legion_reachable", lambda **kw: False)
    monkeypatch.setattr(ambient_server, "LEGION_WIFI_MAC", "AA:BB:CC:DD:EE:FF")

    class _FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def setsockopt(self, *a):
            pass

        def sendto(self, *a):
            pass

    monkeypatch.setattr(ambient_server.socket, "socket", lambda *a, **kw: _FakeSocket())

    result = ambient_server.wake_legion(prefer="wifi")
    assert result["ok"] is True
    assert result.get("already_awake") is False


def test_wake_legion_works_without_host_configured(monkeypatch):
    """Backward compat: LEGION_HOST unset (not yet configured by the owner)
    must not break the existing fire-and-forget WoL behavior."""
    import ambient_server

    monkeypatch.setattr(ambient_server, "LEGION_HOST", "")
    monkeypatch.setattr(ambient_server, "LEGION_WIFI_MAC", "AA:BB:CC:DD:EE:FF")

    class _FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def setsockopt(self, *a):
            pass

        def sendto(self, *a):
            pass

    monkeypatch.setattr(ambient_server.socket, "socket", lambda *a, **kw: _FakeSocket())

    result = ambient_server.wake_legion(prefer="wifi")
    assert result["ok"] is True


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
