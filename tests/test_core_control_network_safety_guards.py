"""Regression tests for fail-open control/network safety checks.

These exercise the real scanner and OFP verifier paths.  In particular, an
existing target that cannot be hashed must never be labelled clean, and a
future-dated authenticated OFP message must not escape the replay window.
"""

from __future__ import annotations

import asyncio
import sys
import time
from types import SimpleNamespace

import numpy as np

from core.control.security.malware_detector import MalwareDetector
from core.network.ofp_protocol import NONCE_TTL_SECS, OFPMessage, OFPNode
from core.sensing.presence_detector import PresenceDetector


def test_unhashable_existing_target_is_not_reported_clean(tmp_path):
    """A directory exists but cannot be read as a file; the scan must fail closed."""
    scanner = MalwareDetector()

    result = asyncio.run(scanner.scan_file(str(tmp_path)))

    assert result["verdict"] == "unknown"
    assert result["hash"] == ""
    assert "hashed" in result["error"]


def test_future_dated_ofp_message_is_rejected_by_replay_window():
    """Signed messages beyond the allowed clock skew are not indefinitely valid."""
    secret = b"regression-test-shared-secret"
    node = OFPNode(node_id="receiver", secret=secret)
    message = OFPMessage(
        sender="peer",
        timestamp=time.time() + NONCE_TTL_SECS + 1,
    ).sign(secret)

    assert message.is_expired()
    assert node._verify_message(message) is False


def test_non_finite_ofp_timestamp_is_rejected():
    """JSON permits NaN, but it must not bypass the protocol timestamp check."""
    secret = b"regression-test-shared-secret"
    node = OFPNode(node_id="receiver", secret=secret)
    message = OFPMessage(sender="peer", timestamp=float("nan")).sign(secret)

    assert message.is_expired()
    assert node._verify_message(message) is False


def test_presence_detector_handles_multiple_numpy_tracker_ids(monkeypatch):
    """supervision's NumPy tracker IDs must not trigger ambiguous truth testing."""
    class _Tracked:
        tracker_id = np.array([7, 11], dtype=np.int64)

        def __len__(self):
            return len(self.tracker_id)

    tracked = _Tracked()
    tracker = SimpleNamespace(update_with_detections=lambda detections: tracked)
    model = lambda source, verbose=False: [object()]
    fake_supervision = SimpleNamespace(
        Detections=SimpleNamespace(from_ultralytics=lambda prediction: SimpleNamespace(class_id=None))
    )
    monkeypatch.setitem(sys.modules, "supervision", fake_supervision)

    detector = PresenceDetector(enabled=True)
    detector._model = model
    detector._tracker = tracker
    result = detector.detect(frame=np.zeros((2, 2, 3), dtype=np.uint8))

    assert result.status == "multiple"
    assert result.person_count == 2
    assert result.tracked_ids == [7, 11]


if __name__ == "__main__":
    test_future_dated_ofp_message_is_rejected_by_replay_window()
    print("test_core_control_network_safety_guards.py OK")
