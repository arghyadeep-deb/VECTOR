from __future__ import annotations


def test_magic_packet_shape_and_mac_repetition() -> None:
    from core.control.wake_on_lan import build_magic_packet

    packet = build_magic_packet("14-B5-CD-3C-EC-99")

    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    assert packet[6:] == bytes.fromhex("14b5cd3cec99") * 16


def test_normalize_mac_accepts_common_formats() -> None:
    from core.control.wake_on_lan import normalize_mac

    assert normalize_mac("14-B5-CD-3C-EC-99") == "14b5cd3cec99"
    assert normalize_mac("14:b5:cd:3c:ec:99") == "14b5cd3cec99"
    assert normalize_mac("14b5.cd3c.ec99") == "14b5cd3cec99"


def test_invalid_mac_rejected() -> None:
    import pytest
    from core.control.wake_on_lan import normalize_mac

    with pytest.raises(ValueError):
        normalize_mac("not-a-mac")


def test_send_magic_packet_uses_udp_broadcast(monkeypatch) -> None:
    from core.control import wake_on_lan

    calls = {}

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def settimeout(self, timeout):
            calls["timeout"] = timeout

        def setsockopt(self, level, optname, value):
            calls["sockopt"] = (level, optname, value)

        def sendto(self, packet, address):
            calls["packet"] = packet
            calls["address"] = address

    monkeypatch.setattr(wake_on_lan.socket, "socket", lambda *args: FakeSocket())

    result = wake_on_lan.send_magic_packet(
        "14-B5-CD-3C-EC-99",
        broadcast="10.208.79.255",
        port=9,
    )

    assert result.ok is True
    assert calls["address"] == ("10.208.79.255", 9)
    assert calls["packet"] == b"\xff" * 6 + bytes.fromhex("14b5cd3cec99") * 16


def test_legion_wake_reports_missing_config(monkeypatch) -> None:
    from core.config import CONFIG
    from core.control.legion_wake import wake_legion

    monkeypatch.setitem(CONFIG, "wake", {
        "legion_wifi_mac": "",
        "legion_ethernet_mac": "",
        "legion_wake_broadcast": "10.208.79.255",
        "legion_wake_port": 9,
    })

    result = wake_legion()

    assert result.ok is False
    assert "LEGION_WIFI_MAC" in result.error

