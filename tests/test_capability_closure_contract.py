"""Tests for the canonical capability closure vocabulary."""

from __future__ import annotations

import pytest


def test_capability_status_vocabulary_is_closed():
    from core.runtime.capability_contract import CapabilityStatus

    assert {status.value for status in CapabilityStatus} == {
        "LIVE",
        "NEEDS_CONFIG",
        "FAIL_CLOSED",
        "RETIRED",
        "DEFERRED",
        "FIX_QUEUE",
    }


def test_deferred_capability_requires_owner_reason_exit_and_revisit():
    from core.runtime.capability_contract import CapabilityRecord

    record = CapabilityRecord(
        capability_id="growth-software-arm",
        name="autonomous software growth",
        status="DEFERRED",
    )

    with pytest.raises(ValueError, match="owner"):
        record.validate()


def test_valid_live_capability_has_evidence():
    from core.runtime.capability_contract import CapabilityRecord

    record = CapabilityRecord(
        capability_id="launcher-smoke",
        name="launcher smoke spine",
        status="LIVE",
        evidence=("tests/test_run_vector_smoke_isolation.py",),
    )

    assert record.validate() is None
    assert record.to_dict()["status"] == "LIVE"


def test_duplicate_capability_ids_are_rejected():
    from core.runtime.capability_contract import CapabilityRecord, validate_capability_records

    records = [
        CapabilityRecord("same", "first", "FIX_QUEUE"),
        CapabilityRecord("same", "second", "FIX_QUEUE"),
    ]

    with pytest.raises(ValueError, match="duplicate"):
        validate_capability_records(records)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
