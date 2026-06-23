"""
docs/repo_analysis/_MASTER_TODO.md §3 item 11 / §4: "Node status model
(online/asleep/offline/unknown)" — was listed as missing entirely (only
the WoL send primitive existed: core/control/wake_on_lan.py,
core/control/legion_wake.py). No host/IP is configured anywhere for
Legion specifically (VECTOR normally runs ON the Legion machine itself —
this status check is for a REMOTE caller, e.g. a future Termux poll or
Cloudflare Worker heartbeat, asking "is the heavy node reachable right
now"), so host/port are caller-supplied parameters, not a hardcoded
config key. real, local TCP probes only — no live deployment needed to
test this; localhost-refused/unreachable-IP are real, observable network
states.
"""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_status_online_when_port_accepts_connection():
    from core.control.node_status import check_node_status, NodeStatus

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        status = check_node_status("127.0.0.1", port, mac="AA:BB:CC:DD:EE:FF", timeout=1.0)
        assert status == NodeStatus.ONLINE
    finally:
        server.close()


def test_status_asleep_when_unreachable_but_mac_known():
    from core.control.node_status import check_node_status, NodeStatus

    # Port 1 on localhost: almost certainly closed/refused immediately —
    # a real, observable "unreachable" without needing a live deployment.
    status = check_node_status("127.0.0.1", 1, mac="AA:BB:CC:DD:EE:FF", timeout=0.5)
    assert status == NodeStatus.ASLEEP


def test_status_offline_when_unreachable_and_no_mac():
    from core.control.node_status import check_node_status, NodeStatus

    status = check_node_status("127.0.0.1", 1, mac="", timeout=0.5)
    assert status == NodeStatus.OFFLINE


def test_status_unknown_when_no_host_configured():
    from core.control.node_status import check_node_status, NodeStatus

    status = check_node_status("", 0, mac="AA:BB:CC:DD:EE:FF")
    assert status == NodeStatus.UNKNOWN


def test_ensure_node_awake_noop_when_already_online():
    from core.control.node_status import ensure_node_awake

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        result = ensure_node_awake("127.0.0.1", port, mac="AA:BB:CC:DD:EE:FF")
        assert result["status"] == "online"
        assert result["wake_sent"] is False
    finally:
        server.close()


def test_ensure_node_awake_sends_wol_when_asleep(monkeypatch):
    from core.control import node_status
    from core.control.wake_on_lan import WakeResult

    called = {}

    def _fake_send(mac, broadcast="255.255.255.255", port=9):
        called["mac"] = mac
        return WakeResult(ok=True, mac=mac, broadcast=broadcast, port=port)

    monkeypatch.setattr(node_status, "send_magic_packet", _fake_send)

    result = node_status.ensure_node_awake("127.0.0.1", 1, mac="AA:BB:CC:DD:EE:FF", timeout=0.5)
    assert result["status"] == "asleep"
    assert result["wake_sent"] is True
    assert called["mac"] == "AA:BB:CC:DD:EE:FF"


def test_ensure_node_awake_errors_cleanly_when_offline_no_mac():
    from core.control.node_status import ensure_node_awake

    result = ensure_node_awake("127.0.0.1", 1, mac="", timeout=0.5)
    assert result["status"] == "offline"
    assert result["wake_sent"] is False
    assert "error" in result


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
