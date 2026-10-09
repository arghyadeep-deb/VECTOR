"""Regression tests for GW-6 WhatsApp bridge process ownership."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vectorcode" / "src"))

from gateway.platforms import whatsapp


def test_identity_validation_rejects_unowned_port_process():
    owned = {"pid": 1200, "create_time": 100.0, "bridge_script": "C:/vector/bridge.js"}
    current = {"pid": 9876, "create_time": 200.0, "cmdline": ["node", "C:/other/server.js"]}

    assert not whatsapp._owned_process_matches(owned, current)


def test_identity_validation_accepts_exact_owned_bridge():
    owned = {"pid": 1200, "create_time": 100.0, "bridge_script": "C:/vector/bridge.js"}
    current = {
        "pid": 1200,
        "create_time": 100.0,
        "cmdline": ["node", "C:/vector/bridge.js", "--port", "3000"],
    }

    assert whatsapp._owned_process_matches(owned, current)


def test_unverified_port_owner_raises_collision_before_termination():
    owned = {"pid": 1200, "create_time": 100.0, "bridge_script": "C:/vector/bridge.js"}
    current = {
        "pid": 9876,
        "create_time": 200.0,
        "cmdline": ["node", "C:/other/server.js"],
    }

    with pytest.raises(whatsapp.WhatsAppPortCollisionError, match="not owned by VECTOR"):
        whatsapp._require_owned_process(3000, owned, current)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
